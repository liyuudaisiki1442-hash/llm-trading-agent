import pytest
from src.market.candles import MultiTimeframeState

def test_multi_timeframe_state():
    state = MultiTimeframeState("BTCUSDT", limit=2)

    # Initialize with 3 candles (should keep only last 2)
    candles = [
        {"timestamp": 1000, "close": 10, "is_closed": True},
        {"timestamp": 2000, "close": 20, "is_closed": True},
        {"timestamp": 3000, "close": 30, "is_closed": True},
    ]
    state.initialize_history("5M", candles)

    assert len(state.history_5m) == 2
    assert state.history_5m[0]["close"] == 20
    assert state.history_5m[1]["close"] == 30

    # Update forming candle
    state.update_candle("5M", {"timestamp": 4000, "close": 40, "is_closed": False})
    assert state.current_5m is not None
    assert state.current_5m["close"] == 40
    assert len(state.history_5m) == 2 # History unchanged

    # Update closed candle
    state.update_candle("5M", {"timestamp": 4000, "close": 45, "is_closed": True})
    assert state.current_5m is None
    assert len(state.history_5m) == 2
    assert state.history_5m[1]["close"] == 45 # Newest closed
    assert state.history_5m[0]["close"] == 30 # Previous closed
