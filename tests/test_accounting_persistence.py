import pytest
from src.execution.executor import LocalPaperExecutor
from src.storage.database import SessionLocal, engine
from src.storage.models import Base

@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

def test_single_trade_exact_balance_restore():
    executor1 = LocalPaperExecutor(initial_balance=10000.0)

    # Open LONG
    params = {
        "symbol": "BTCUSDT",
        "side": "LONG",
        "quantity": 0.1, # So margin fits 10000
        "leverage": 2,
        "entry_zone": {"low": 50000, "high": 50000},
        "stop_loss": 49000,
        "take_profit": 52000
    }
    executor1.execute_params(params)
    executor1.update_price(50000) # Open position

    # Close LONG at 51000
    # Entry fee: (50000 * 0.1) * 0.0004 = 2
    # Raw PnL = (51000 - 50000) * 0.1 = 100
    # Exit fee: (51000 * 0.1) * 0.0004 = 2.04
    # Expected net PnL = 100 - 2 - 2.04 = 95.96
    # Expected final balance = 10000 + 95.96 = 10095.96
    executor1.update_price(51000)
    executor1.close_position(51000, reason="MANUAL")

    expected_balance = 10095.96
    assert abs(executor1.balance - expected_balance) < 1e-6

    # Recreate executor and ensure balance is perfectly restored
    executor2 = LocalPaperExecutor(initial_balance=10000.0)
    assert abs(executor2.balance - expected_balance) < 1e-6
    assert executor2.position is None

def test_multi_trade_exact_balance_restore():
    executor1 = LocalPaperExecutor(initial_balance=10000.0)

    # Trade 1: SHORT at 50000, hit TP at 49000
    params1 = {
        "symbol": "BTCUSDT",
        "side": "SHORT",
        "quantity": 0.5,
        "leverage": 5,
        "entry_zone": {"low": 50000, "high": 50000},
        "stop_loss": 51000,
        "take_profit": 49000
    }
    executor1.execute_params(params1)
    executor1.update_price(50000) # Open position
    executor1.update_price(49000) # Hit TP

    # Trade 2: LONG at 49000, manual close at 49500
    params2 = {
        "symbol": "BTCUSDT",
        "side": "LONG",
        "quantity": 0.3,
        "leverage": 3,
        "entry_zone": {"low": 49000, "high": 49000},
        "stop_loss": 48000,
        "take_profit": 51000
    }
    executor1.execute_params(params2)
    executor1.update_price(49000) # Open
    executor1.update_price(49500)
    executor1.close_position(49500, reason="MANUAL")

    final_balance_before_restart = executor1.balance

    # Recreate
    executor2 = LocalPaperExecutor(initial_balance=10000.0)
    assert abs(executor2.balance - final_balance_before_restart) < 1e-6
