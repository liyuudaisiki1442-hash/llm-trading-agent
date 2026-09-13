from src.agent.schemas import TradeDecision
from src.features.market_context import MarketContext
from src.config.settings import settings
from typing import Dict, Any, Tuple

class RiskManager:
    def __init__(self, config=settings):
        self.max_leverage = config.MAX_LEVERAGE
        self.risk_per_trade = config.RISK_PER_TRADE
        self.max_positions = config.MAX_POSITIONS

    def calculate_position(self, decision: TradeDecision, context: MarketContext, account_balance: float) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Deterministically calculates risk, reward, size, and leverage.
        Returns (is_approved, reason, execution_params)
        """
        if decision.action not in ["LONG", "SHORT"]:
            return True, "", {}

        current_price = context.tf_5m.current_price
        entry_price = current_price # simplifying entry to market for now
        stop_loss = decision.stop_loss
        take_profit = decision.take_profit_targets[0] # primary target

        # Risk per unit
        risk_per_unit = abs(entry_price - stop_loss)
        if risk_per_unit == 0:
            return False, "Stop loss equals entry price", {}

        risk_pct = risk_per_unit / entry_price

        # Reward per unit
        reward_per_unit = abs(take_profit - entry_price)

        # Deterministic Risk/Reward
        rr_ratio = reward_per_unit / risk_per_unit if risk_per_unit > 0 else 0

        if rr_ratio < 1.0:
            return False, f"Risk/Reward ratio {rr_ratio:.2f} is below 1.0", {}

        # Position Sizing
        risk_amount = account_balance * self.risk_per_trade
        quantity = risk_amount / risk_per_unit

        position_value = quantity * entry_price

        # Required leverage
        required_leverage = position_value / account_balance
        if required_leverage > self.max_leverage:
             # Reduce position size to fit max leverage
             position_value = account_balance * self.max_leverage
             quantity = position_value / entry_price

             # Re-check risk amount
             new_risk_amount = quantity * risk_per_unit
             if new_risk_amount > risk_amount:
                 return False, f"Cannot satisfy both risk limits and leverage limits.", {}

        execution_params = {
            "symbol": context.symbol,
            "side": decision.action,
            "quantity": quantity,
            "leverage": min(required_leverage, self.max_leverage),
            "entry_price": entry_price,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "risk_reward": rr_ratio,
            "risk_amount": risk_amount
        }

        return True, "Approved", execution_params
