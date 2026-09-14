import pytest
from src.execution.executor import LocalPaperExecutor

def test_paper_executor_lifecycle():
    exec = LocalPaperExecutor(initial_balance=10000)

    # Execute a LONG
    params = {
        "symbol": "BTCUSDT",
        "side": "LONG",
        "quantity": 0.1,  # ~5000 value
        "leverage": 1,
        "entry_zone": {"low": 50000, "high": 50000},
        "stop_loss": 49000,
        "take_profit": 52000
    }
    exec.execute_params(params)
    exec.update_price(50000)

    pos = exec.get_position()
    assert pos is not None
    assert pos["side"] == "LONG"
    assert exec.available_balance < 10000 # margin locked

    # Tick price up, check unrealized pnl
    exec.update_price(51000)
    # Entry fee was 2.0. So unrealized PnL is 100 - 2.0 = 98.0.
    assert exec.position["unrealized_pnl"] == 98.0

    # Tick price to TP, should automatically close
    exec.update_price(52000)
    assert exec.get_position() is None # closed

    # Balance should be higher (original + pnl - fees)
    # The actual implementation sets balance in open and closes.
    # We just want to check it successfully went up.
    assert exec.balance > 10050
    assert exec.available_balance == exec.balance

def test_paper_executor_stop_loss():
    from src.storage.database import engine
    from src.storage.models import Base
    exec = LocalPaperExecutor(initial_balance=10000)

    params = {
        "symbol": "BTCUSDT",
        "side": "SHORT",
        "quantity": 0.1,
        "leverage": 1,
        "entry_zone": {"low": 50000, "high": 50000},
        "stop_loss": 51000,
        "take_profit": 48000
    }
    exec.execute_params(params)
    exec.update_price(50000)

    # Hit Stop Loss
    exec.update_price(51500)
    assert exec.get_position() is None

    # Balance should be lower
    assert exec.balance < 10000
