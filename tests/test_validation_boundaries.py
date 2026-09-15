import pytest
from src.risk.validation import DecisionValidator
from src.agent.schemas import TradeDecision
from src.features.market_context import MarketContext, PositionState, TimeframeContext

def test_full_zone_tp_sl_boundaries():
    validator = DecisionValidator()
    ctx = MarketContext(
        symbol="BTCUSDT", position_state=PositionState(has_position=False),
        tf_1h=TimeframeContext(timeframe="1H", trend="UP", current_price=50000),
        tf_15m=TimeframeContext(timeframe="15M", trend="UP", current_price=50000),
        tf_5m=TimeframeContext(timeframe="5M", trend="UP", current_price=50000),
    )

    # Valid LONG
    dec = TradeDecision(action="LONG", reasoning_summary="t", stop_loss=48000, take_profit_targets=[52000], entry_zone={"low": 49000, "high": 50000}, first_obstacle=51000)
    is_v, _ = validator.validate(dec, ctx)
    assert is_v

    # Invalid LONG: SL is inside the zone
    dec = TradeDecision(action="LONG", reasoning_summary="t", stop_loss=49500, take_profit_targets=[52000], entry_zone={"low": 49000, "high": 50000}, first_obstacle=51000)
    is_v, msg = validator.validate(dec, ctx)
    assert not is_v
    assert "LONG requires Stop Loss" in msg

    # Invalid LONG: First obstacle is below the high of the entry zone
    dec = TradeDecision(action="LONG", reasoning_summary="t", stop_loss=48000, take_profit_targets=[52000], entry_zone={"low": 49000, "high": 50000}, first_obstacle=49500)
    is_v, msg = validator.validate(dec, ctx)
    assert not is_v
    assert "LONG requires first obstacle" in msg

    # Valid SHORT
    dec = TradeDecision(action="SHORT", reasoning_summary="t", stop_loss=52000, take_profit_targets=[48000], entry_zone={"low": 49000, "high": 50000}, first_obstacle=48500)
    is_v, _ = validator.validate(dec, ctx)
    assert is_v

    # Invalid SHORT: TP inside the zone
    dec = TradeDecision(action="SHORT", reasoning_summary="t", stop_loss=52000, take_profit_targets=[49500], entry_zone={"low": 49000, "high": 50000}, first_obstacle=48500)
    is_v, msg = validator.validate(dec, ctx)
    assert not is_v
    assert "SHORT requires Take Profit" in msg
