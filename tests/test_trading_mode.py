import unittest.mock
import pytest
import os
from src.main import TradingBot
from src.config.settings import settings

@pytest.mark.asyncio
async def test_live_trading_mode_rejected():
    bot = TradingBot()
    settings.TRADING_MODE = "live"
    with pytest.raises(ValueError, match="Live trading is not implemented/enabled in v1."):
        await bot.initialize()

@pytest.mark.asyncio
async def test_paper_trading_mode_accepted():
    bot = TradingBot()
    settings.TRADING_MODE = "paper"

    bot.market_adapter.fetch_historical_candles = unittest.mock.AsyncMock(return_value=[
        {"timestamp": 1000, "close": 50000, "is_closed": True}
    ])
    try:
        await bot.initialize()
    except ValueError:
        pytest.fail("Should not raise ValueError on paper mode")
