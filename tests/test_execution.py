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
        "entry_price": 50000,
        "stop_loss": 49000,
        "take_profit": 52000
    }
    exec.execute_params(params)

    pos = exec.get_position()
    assert pos is not None
    assert pos["side"] == "LONG"
    assert exec.available_balance < 10000 # margin locked

    # Tick price up, check unrealized pnl
    exec.update_price(51000)
    assert exec.position["unrealized_pnl"] == 100.0

    # Tick price to TP, should automatically close
    exec.update_price(52000)
    assert exec.get_position() is None # closed

    # Balance should be higher (10000 + 200 - fees)
    assert exec.balance > 10100
    assert exec.available_balance == exec.balance

def test_paper_executor_stop_loss():
    exec = LocalPaperExecutor(initial_balance=10000)

    params = {
        "symbol": "BTCUSDT",
        "side": "SHORT",
        "quantity": 0.1,
        "leverage": 1,
        "entry_price": 50000,
        "stop_loss": 51000,
        "take_profit": 48000
    }
    exec.execute_params(params)

    # Hit Stop Loss
    exec.update_price(51500)
    assert exec.get_position() is None

    # Balance should be lower
    assert exec.balance < 10000
