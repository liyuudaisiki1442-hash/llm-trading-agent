import pytest
import asyncio
from src.execution.executor import LocalPaperExecutor
from src.storage.database import engine
from src.storage.models import Base
from src.config.settings import settings

# Setup clean DB for tests
Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)

def test_entry_zone_behavior():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    executor = LocalPaperExecutor(initial_balance=10000)

    # Register LONG setup but price is outside zone
    params = {
        "symbol": "BTCUSDT",
        "side": "LONG",
        "quantity": 0.1,
        "leverage": 1,
        "entry_zone": {"low": 49000, "high": 49500},
        "stop_loss": 48000,
        "take_profit": 52000
    }
    executor.execute_params(params)

    # Tick at 50000 (above zone)
    executor.update_price(50000)
    assert executor.position is None
    assert executor.pending_setup is not None

    # Tick at 49300 (inside zone)
    executor.update_price(49300)
    assert executor.position is not None
    assert executor.position["entry_price"] == 49300
    assert executor.pending_setup is None

def test_entry_zone_expiry():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    executor = LocalPaperExecutor(initial_balance=10000)
    params = {
        "symbol": "BTCUSDT",
        "side": "LONG",
        "quantity": 0.1,
        "leverage": 1,
        "entry_zone": {"low": 49000, "high": 49500},
        "stop_loss": 48000,
        "take_profit": 52000
    }
    executor.execute_params(params)

    # Simulate 3 candles passing
    executor.increment_candle_age()
    executor.increment_candle_age()
    executor.increment_candle_age()

    # Setup should be expired
    assert executor.pending_setup is None
    executor.update_price(49300)
    assert executor.position is None

def test_no_fake_liquidation():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    executor = LocalPaperExecutor(initial_balance=10000)
    params = {
        "symbol": "BTCUSDT",
        "side": "LONG",
        "quantity": 1.0,
        "leverage": 10,
        "entry_zone": {"low": 50000, "high": 50000},
        "stop_loss": 40000, # Very wide stop loss just for test
        "take_profit": 60000
    }
    executor.execute_params(params)
    executor.update_price(50000) # Open position
    assert executor.position is not None

    # Move price down to trigger the old 90% margin liquidation threshold
    # Margin is 5000. 90% is 4500.
    # PnL = (45400 - 50000) * 1.0 = -4600
    executor.update_price(45400)

    # Should STILL be open because we removed fake liquidation
    assert executor.position is not None
    assert executor.position["unrealized_pnl"] < -4500

def test_state_persistence_across_restarts():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    executor1 = LocalPaperExecutor(initial_balance=10000)
    params = {
        "symbol": "BTCUSDT",
        "side": "LONG",
        "quantity": 0.1,  # Lower quantity so margin fits 10000 balance
        "leverage": 2,
        "entry_zone": {"low": 50000, "high": 50000},
        "stop_loss": 49000,
        "take_profit": 52000
    }
    executor1.execute_params(params)
    executor1.update_price(50000) # Open

    # Simulate restart
    executor2 = LocalPaperExecutor(initial_balance=10000)
    assert executor2.position is not None
    assert executor2.position["quantity"] == 0.1
    assert executor2.position["leverage"] == 2
    assert executor2.available_balance == executor1.available_balance
