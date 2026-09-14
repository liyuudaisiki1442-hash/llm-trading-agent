import pytest
from src.risk.validation import DecisionValidator
from src.risk.manager import RiskManager
from src.agent.schemas import TradeDecision
from src.features.market_context import MarketContext, PositionState, TimeframeContext

def test_validation_strict_semantics():
    validator = DecisionValidator()

    # Mock context - no position
    ctx_no_pos = MarketContext(
        symbol="BTCUSDT",
        position_state=PositionState(has_position=False),
        tf_1h=TimeframeContext(timeframe="1H", trend="UP", current_price=50000),
        tf_15m=TimeframeContext(timeframe="15M", trend="UP", current_price=50000),
        tf_5m=TimeframeContext(timeframe="5M", trend="UP", current_price=50000),
    )

    # Valid WAIT
    dec = TradeDecision(action="WAIT", reasoning_summary="test")
    is_valid, _ = validator.validate(dec, ctx_no_pos)
    assert is_valid

    # Invalid HOLD when no position
    dec = TradeDecision(action="HOLD", reasoning_summary="test")
    is_valid, reason = validator.validate(dec, ctx_no_pos)
    assert not is_valid
    assert "must be LONG, SHORT, or WAIT" in reason

    # Mock context - has position
    ctx_has_pos = MarketContext(
        symbol="BTCUSDT",
        position_state=PositionState(has_position=True, side="LONG"),
        tf_1h=TimeframeContext(timeframe="1H", trend="UP", current_price=50000),
        tf_15m=TimeframeContext(timeframe="15M", trend="UP", current_price=50000),
        tf_5m=TimeframeContext(timeframe="5M", trend="UP", current_price=50000),
    )

    # Valid HOLD
    dec = TradeDecision(action="HOLD", reasoning_summary="test")
    is_valid, _ = validator.validate(dec, ctx_has_pos)
    assert is_valid

    # Invalid SHORT when LONG position exists
    dec = TradeDecision(action="SHORT", reasoning_summary="test")
    is_valid, reason = validator.validate(dec, ctx_has_pos)
    assert not is_valid
    assert "must be HOLD or CLOSE" in reason

def test_risk_manager_deterministic_rr():
    rm = RiskManager()

    ctx = MarketContext(
        symbol="BTCUSDT",
        position_state=PositionState(has_position=False),
        tf_1h=TimeframeContext(timeframe="1H", trend="UP", current_price=50000),
        tf_15m=TimeframeContext(timeframe="15M", trend="UP", current_price=50000),
        tf_5m=TimeframeContext(timeframe="5M", trend="UP", current_price=50000), # Current Price = 50000
    )

    # R/R Long based on worst case entry (high of zone)
    # Zone high: 50000, SL: 49000 -> Price Risk: 1000
    # TP: 52000 -> Reward: 2000
    # But R/R is calculated using effective risk and reward including fees.
    dec_good = TradeDecision(
        action="LONG",
        reasoning_summary="test",
        stop_loss=49000,
        take_profit_targets=[52000],
        entry_zone={"low": 49500, "high": 50000}
    )

    is_approved, _, params = rm.calculate_position(dec_good, ctx, 10000)
    assert is_approved
    assert params["risk_reward"] > 1.8 # Due to fees it will be slightly less than 2.0, e.g. ~1.88

    # R/R Long (Risk 1000, Reward 500) - Should reject (< 1.0)
    dec_bad = TradeDecision(
        action="LONG",
        reasoning_summary="test",
        stop_loss=49000,
        take_profit_targets=[50500],
        entry_zone={"low": 49500, "high": 50000}
    )

    is_approved, reason, _ = rm.calculate_position(dec_bad, ctx, 10000)
    assert not is_approved
    assert "below 1.0" in reason
