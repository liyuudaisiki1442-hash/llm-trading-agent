from src.agent.schemas import TradeDecision
from src.features.market_context import MarketContext
from src.config.settings import settings
from typing import Dict, Any, Tuple

from datetime import datetime
from src.storage.database import SessionLocal
from src.storage.models import Trade

class RiskManager:
    def __init__(self, config=settings):
        self.max_leverage = max(1, config.MAX_LEVERAGE) # Leverage must never be less than 1
        self.risk_per_trade = config.RISK_PER_TRADE
        self.max_positions = 1 # explicitly enforce single position for v1
        self.max_daily_loss_pct = config.MAX_DAILY_LOSS
        self.min_first_obstacle_r = 1.0 # configurable threshold

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

            # Simple assumption: balance at start of day was roughly (account_balance - daily_pnl)
            # A more robust system would save daily equity snapshots.
            start_of_day_equity = account_balance - daily_pnl
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

        # The entry logic will use the entry_zone. The executor will wait for the price to hit this zone.
        # We calculate risk assuming an entry at the worst-case edge of the zone to be conservative,
        # or the mid-point. Let's use mid-point for sizing.
        entry_price = (decision.entry_zone.low + decision.entry_zone.high) / 2.0

        stop_loss = decision.stop_loss
        take_profit = decision.take_profit_targets[0] # primary target
        first_obstacle = decision.first_obstacle

        # Risk per unit
        risk_per_unit = abs(entry_price - stop_loss)
        if risk_per_unit == 0:
            return False, "Stop loss equals entry price", {}

        # Reward per unit
        reward_per_unit = abs(take_profit - entry_price)

        # Deterministic Risk/Reward
        rr_ratio = reward_per_unit / risk_per_unit if risk_per_unit > 0 else 0
        if rr_ratio < 1.0:
            return False, f"Risk/Reward ratio {rr_ratio:.2f} is below 1.0", {}

        # First Obstacle check
        if first_obstacle is not None:
            if decision.action == "LONG" and first_obstacle > entry_price:
                obstacle_reward = first_obstacle - entry_price
                obstacle_r = obstacle_reward / risk_per_unit
                if obstacle_r < self.min_first_obstacle_r:
                    return False, f"First obstacle R ({obstacle_r:.2f}) < minimum ({self.min_first_obstacle_r})", {}
            elif decision.action == "SHORT" and first_obstacle < entry_price:
                obstacle_reward = entry_price - first_obstacle
                obstacle_r = obstacle_reward / risk_per_unit
                if obstacle_r < self.min_first_obstacle_r:
                    return False, f"First obstacle R ({obstacle_r:.2f}) < minimum ({self.min_first_obstacle_r})", {}

        # Position Sizing
        risk_amount = account_balance * self.risk_per_trade
        quantity = risk_amount / risk_per_unit

        if quantity <= 0:
            return False, "Calculated quantity is zero or negative", {}

        position_value = quantity * entry_price

        # Max Notional Exposure bounding
        max_notional = account_balance * self.max_leverage

        if position_value > max_notional:
            position_value = max_notional
            quantity = position_value / entry_price

            # Recalculate risk to ensure we didn't increase it (we shouldn't have)
            new_risk_amount = quantity * risk_per_unit
            if new_risk_amount > risk_amount:
                return False, "Cannot satisfy both max leverage and max risk limits.", {}

        # Required leverage for THIS position to satisfy margin requirement
        # If position_value <= account_balance, we use 1x leverage.
        # Otherwise we use the minimum leverage needed (up to max_leverage).
        required_leverage = position_value / account_balance
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
