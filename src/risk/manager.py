from src.agent.schemas import TradeDecision
from src.features.market_context import MarketContext
from src.config.settings import settings
from typing import Dict, Any, Tuple

from datetime import datetime
from src.storage.database import SessionLocal
from src.storage.models import Trade, AccountSnapshot

class RiskManager:
    def __init__(self, config=settings):
        self.max_leverage = max(1, config.MAX_LEVERAGE) # Leverage must never be less than 1
        self.risk_per_trade = config.RISK_PER_TRADE
        self.max_positions = 1 # explicitly enforce single position for v1
        self.max_daily_loss_pct = config.MAX_DAILY_LOSS
        self.min_first_obstacle_r = getattr(config, "MIN_FIRST_OBSTACLE_R", 1.0)

    def _check_daily_loss(self, account_balance: float) -> Tuple[bool, str]:
        """Check if max daily loss is reached based on UTC day."""
        db = SessionLocal()
        try:
            today = datetime.utcnow().date()
            # Fetch closed trades for today
            trades = db.query(Trade).filter(
                Trade.exit_timestamp != None,
                Trade.realized_pnl != None
            ).all()

            daily_pnl = sum(t.realized_pnl for t in trades if t.exit_timestamp and t.exit_timestamp.date() == today)

            # Use the explicitly saved start-of-day equity snapshot
            today_dt = datetime(today.year, today.month, today.day)
            snapshot = db.query(AccountSnapshot).filter(AccountSnapshot.date == today_dt).first()

            start_of_day_equity = snapshot.equity if snapshot else account_balance
            if start_of_day_equity <= 0:
                start_of_day_equity = account_balance # fallback

            loss_pct = -daily_pnl / start_of_day_equity if daily_pnl < 0 else 0
            if loss_pct >= self.max_daily_loss_pct:
                return False, f"Max daily loss reached ({loss_pct*100:.2f}% >= {self.max_daily_loss_pct*100:.2f}%)"
            return True, ""
        except Exception as e:
            return False, f"Error checking daily loss: {e}"
        finally:
            db.close()

    def calculate_position(self, decision: TradeDecision, context: MarketContext, account_balance: float) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Deterministically calculates risk, reward, size, and leverage.
        Returns (is_approved, reason, execution_params)
        """
        if decision.action not in ["LONG", "SHORT"]:
            return True, "", {}

        # Max positions check
        if context.position_state.has_position:
            return False, "Max positions (1) already reached.", {}

        can_trade, loss_reason = self._check_daily_loss(account_balance)
        if not can_trade:
            return False, loss_reason, {}

        # Risk sizing must use the worst-case executable fill price from the entry zone
        # LONG worst case entry = highest price in zone
        # SHORT worst case entry = lowest price in zone
        if decision.action == "LONG":
            entry_price = decision.entry_zone.high
        else:
            entry_price = decision.entry_zone.low

        stop_loss = decision.stop_loss
        take_profit = decision.take_profit_targets[0] # primary target
        first_obstacle = decision.first_obstacle

        # Assume a worst-case combined entry+exit fee rate
        # Typically 0.0004 for taker. Double it to cover both open and close.
        assumed_fee_rate = 0.0008

        # Risk per unit including estimated fees
        # We lose the price difference + we pay fees on the entry value and the exit (SL) value
        price_risk = abs(entry_price - stop_loss)
        fee_risk = (entry_price * assumed_fee_rate / 2) + (stop_loss * assumed_fee_rate / 2)
        effective_risk_per_unit = price_risk + fee_risk

        if effective_risk_per_unit == 0:
            return False, "Stop loss equals entry price", {}

        # Reward per unit (similarly penalize reward by fees)
        price_reward = abs(take_profit - entry_price)
        fee_reward = (entry_price * assumed_fee_rate / 2) + (take_profit * assumed_fee_rate / 2)
        effective_reward_per_unit = price_reward - fee_reward

        # Deterministic Risk/Reward
        rr_ratio = effective_reward_per_unit / effective_risk_per_unit if effective_risk_per_unit > 0 else 0
        if rr_ratio < 1.0:
            return False, f"Risk/Reward ratio {rr_ratio:.2f} is below 1.0", {}

        # First Obstacle check
        if first_obstacle is not None:
            if decision.action == "LONG" and first_obstacle > entry_price:
                obstacle_reward = (first_obstacle - entry_price) - ((entry_price + first_obstacle) * assumed_fee_rate / 2)
                obstacle_r = obstacle_reward / effective_risk_per_unit
                if obstacle_r < self.min_first_obstacle_r:
                    return False, f"First obstacle R ({obstacle_r:.2f}) < minimum ({self.min_first_obstacle_r})", {}
            elif decision.action == "SHORT" and first_obstacle < entry_price:
                obstacle_reward = (entry_price - first_obstacle) - ((entry_price + first_obstacle) * assumed_fee_rate / 2)
                obstacle_r = obstacle_reward / effective_risk_per_unit
                if obstacle_r < self.min_first_obstacle_r:
                    return False, f"First obstacle R ({obstacle_r:.2f}) < minimum ({self.min_first_obstacle_r})", {}

        # Position Sizing based on effective risk to honor max risk cap
        risk_amount = account_balance * self.risk_per_trade
        quantity = risk_amount / effective_risk_per_unit

        if quantity <= 0:
            return False, "Calculated quantity is zero or negative", {}

        position_value = quantity * entry_price

        # Approximate the fee buffer so the executor doesn't reject it due to entry fee + margin exceeding balance.
        # Taker fee is typically 0.0004, so 0.04% for entry and 0.04% for exit (worst case approx).
        # We'll leave a 0.5% margin buffer overall.
        buffer_ratio = 1.005
        effective_balance_for_margin = account_balance / buffer_ratio

        # Max Notional Exposure bounding
        max_notional = effective_balance_for_margin * self.max_leverage

        if position_value > max_notional:
            position_value = max_notional
            quantity = position_value / entry_price

            # Recalculate risk to ensure we didn't increase it
            new_risk_amount = quantity * effective_risk_per_unit
            if new_risk_amount > risk_amount:
                return False, "Cannot satisfy both max leverage and max risk limits.", {}

        # Required leverage for THIS position to satisfy margin requirement
        required_leverage = position_value / effective_balance_for_margin
        actual_leverage = max(1.0, min(required_leverage, float(self.max_leverage)))

        execution_params = {
            "symbol": context.symbol,
            "side": decision.action,
            "quantity": quantity,
            "leverage": actual_leverage,
            "entry_zone": {"low": decision.entry_zone.low, "high": decision.entry_zone.high},
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "risk_reward": rr_ratio,
            "risk_amount": risk_amount
        }

        return True, "Approved", execution_params
