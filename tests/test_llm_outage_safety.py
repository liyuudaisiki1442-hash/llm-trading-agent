import pytest
import asyncio
from unittest.mock import AsyncMock
from src.main import TradingBot
from src.execution.executor import LocalPaperExecutor
from src.storage.database import engine
from src.storage.models import Base

@pytest.mark.asyncio
async def test_llm_outage_safety_path():

    bot = TradingBot()
    # Mock LLM out
    bot.llm_client.get_decision = AsyncMock(return_value=None)

    # Pre-configure an open position in the executor manually
    # to simulate that a position was previously opened.
    params = {
        "symbol": "BTCUSDT",
        "side": "LONG",
        "quantity": 0.1,
        "leverage": 1.0,
        "entry_zone": {"low": 50000, "high": 50000},
        "stop_loss": 49000,
        "take_profit": 52000
    }
    bot.executor.execute_params(params)
    bot.executor.update_price(50000)
    assert bot.executor.position is not None

    # Run the decision cycle (it will hit the LLM outage and return)
    await bot.run_decision_cycle()

    # The position should STILL be open
    assert bot.executor.position is not None

    # Now simulate a mark price update that hits the stop loss.
    # The real-time safety layer should trigger independently of the LLM.
    await bot.on_market_update({"type": "mark_price", "symbol": "BTCUSDT", "price": 48500, "timestamp": 12345})

    # The position should be CLOSED
    assert bot.executor.position is None
