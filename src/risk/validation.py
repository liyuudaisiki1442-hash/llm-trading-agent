from src.agent.schemas import TradeDecision
from src.features.market_context import MarketContext
from typing import Tuple

class DecisionValidator:
    def validate(self, decision: TradeDecision, context: MarketContext) -> Tuple[bool, str]:
        """
        Validates the strict semantics and structural integrity of the decision.
        Returns (is_valid, rejection_reason)
        """
        pos = context.position_state

        # 1. Strict Semantics
        if pos.has_position:
            if decision.action not in ["HOLD", "CLOSE"]:
                return False, f"Position exists. Action {decision.action} is invalid (must be HOLD or CLOSE)."
        else:
            if decision.action not in ["LONG", "SHORT", "WAIT"]:
                return False, f"No position. Action {decision.action} is invalid (must be LONG, SHORT, or WAIT)."

        # 2. Structural Requirements for Entries
        if decision.action in ["LONG", "SHORT"]:
            if not decision.stop_loss:
                return False, "Stop loss is required for LONG/SHORT."
            if not decision.take_profit_targets or len(decision.take_profit_targets) == 0:
                return False, "At least one take profit target is required for LONG/SHORT."
            if not decision.entry_zone:
                return False, "Entry zone is required for LONG/SHORT."

            # Stop loss logic checks
            current_price = context.tf_5m.current_price
            if decision.action == "LONG" and decision.stop_loss >= current_price:
                return False, f"LONG stop loss ({decision.stop_loss}) must be below current price ({current_price})."
            if decision.action == "SHORT" and decision.stop_loss <= current_price:
                return False, f"SHORT stop loss ({decision.stop_loss}) must be above current price ({current_price})."

        return True, ""
