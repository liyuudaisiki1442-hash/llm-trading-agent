import pytest
import pandas as pd
import numpy as np
from src.features.market_context import MarketContextBuilder
from src.market.candles import MultiTimeframeState

def test_market_context_builder():
    builder = MarketContextBuilder(llm_candle_context=5)
    state = MultiTimeframeState("BTCUSDT", limit=100)

    # Generate mock 1H data (100 candles)
    np.random.seed(42)
    base_price = 50000
    prices = base_price + np.cumsum(np.random.randn(100) * 100)

    candles_1h = []
    for i in range(100):
        candles_1h.append({
            "timestamp": i * 3600000,
            "open": float(prices[i-1]) if i > 0 else float(prices[i]),
            "high": float(prices[i]) + 50,
            "low": float(prices[i]) - 50,
            "close": float(prices[i]),
            "volume": 10.0,
            "is_closed": True
        })

    state.initialize_history("1H", candles_1h)
    state.initialize_history("15M", candles_1h) # use same for test
    state.initialize_history("5M", candles_1h) # use same for test
    state.update_mark_price(prices[-1])

    ctx = builder.build_context(state)

    assert ctx.symbol == "BTCUSDT"
    assert not ctx.position_state.has_position
    assert ctx.tf_1h.timeframe == "1H"
    assert len(ctx.tf_1h.recent_closed_candles) == 5
    assert ctx.tf_1h.ema_20 is not None
    assert ctx.tf_1h.rsi is not None
