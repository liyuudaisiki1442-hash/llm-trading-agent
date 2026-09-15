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

            z_low = decision.entry_zone.low
            z_high = decision.entry_zone.high

            if decision.action == "LONG":
                if not (sl < z_low and z_high < tp):
                    return False, f"LONG requires Stop Loss ({sl}) < entire Entry Zone ({z_low}-{z_high}) < Take Profit ({tp})."
            elif decision.action == "SHORT":
                if not (tp < z_low and z_high < sl):
                    return False, f"SHORT requires Take Profit ({tp}) < entire Entry Zone ({z_low}-{z_high}) < Stop Loss ({sl})."

            # Additional First Obstacle logical direction validation
            if decision.first_obstacle is not None:
                if decision.action == "LONG" and decision.first_obstacle <= z_high:
                    return False, f"LONG requires first obstacle ({decision.first_obstacle}) > Entry Zone High ({z_high})."
                if decision.action == "SHORT" and decision.first_obstacle >= z_low:
                    return False, f"SHORT requires first obstacle ({decision.first_obstacle}) < Entry Zone Low ({z_low})."

        return True, ""
