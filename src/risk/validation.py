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

            # TP/SL direction checks
            # entry zone should be checked in executor, but let's check SL and TP vs entry zone
            entry_mid = (decision.entry_zone.low + decision.entry_zone.high) / 2.0
            tp = decision.take_profit_targets[0]
            sl = decision.stop_loss

            if decision.entry_zone.low > decision.entry_zone.high:
                return False, "Entry zone low must be <= entry zone high."

            if decision.action == "LONG":
                if not (sl < entry_mid < tp):
                    return False, f"LONG requires Stop Loss ({sl}) < Entry Zone < Take Profit ({tp})."
            elif decision.action == "SHORT":
                if not (tp < entry_mid < sl):
                    return False, f"SHORT requires Take Profit ({tp}) < Entry Zone < Stop Loss ({sl})."

        return True, ""
