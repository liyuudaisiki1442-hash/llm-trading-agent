import unittest.mock
import pytest
import asyncio
from src.main import TradingBot

@pytest.mark.asyncio
async def test_bot_initialization():
    bot = TradingBot()
    # Mock network calls
    bot.market_adapter.fetch_historical_candles = unittest.mock.AsyncMock(return_value=[
        {"timestamp": 1000, "close": 50000, "is_closed": True}
    ])

    await bot.initialize()

    assert bot.mtf_state.history_1h[0]["close"] == 50000
    assert bot.mtf_state.history_15m[0]["close"] == 50000
    assert bot.mtf_state.history_5m[0]["close"] == 50000
