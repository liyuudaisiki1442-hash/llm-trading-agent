import pytest
from src.features.market_context import MarketContextBuilder
from src.market.candles import MultiTimeframeState

def test_context_json_active_plan():
    builder = MarketContextBuilder()
    state = MultiTimeframeState("BTCUSDT", limit=1)

    # Flat state
    ctx_flat = builder.build_context(state)
    assert ctx_flat.active_trade_plan is None
    json_flat = ctx_flat.model_dump_json()
    assert '"active_trade_plan":null' in json_flat

    # Active plan state
    active_plan_mock = {
        "side": "LONG",
        "setup_type": "Breakout",
        "entry_reason": "test",
        "entry_zone_low": 50000,
        "entry_zone_high": 50000,
        "invalidation_price": 49000,
        "original_stop_loss": 49500,
        "original_take_profit": 55000,
        "original_first_obstacle": 51000,
        "market_regime": "Uptrend",
        "created_at": "2026-01-01T00:00:00"
    }

    ctx_open = builder.build_context(state, position={"side": "LONG"}, active_trade_plan=active_plan_mock)
    assert ctx_open.active_trade_plan is not None
    assert ctx_open.active_trade_plan.setup_type == "Breakout"
    json_open = ctx_open.model_dump_json()
    assert '"active_trade_plan":{"side":"LONG","setup_type":"Breakout"' in json_open
