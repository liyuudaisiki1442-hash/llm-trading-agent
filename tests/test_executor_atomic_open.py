import pytest
from unittest.mock import patch
from src.execution.executor import LocalPaperExecutor
from src.storage.models import Trade, Position, ActiveTradePlan

def test_atomic_open_position_failure(isolated_test_db):
    import src.execution.executor as exec_mod
    db = exec_mod.SessionLocal()
    exec = LocalPaperExecutor(initial_balance=10000.0)

    params = {
        "symbol": "BTCUSDT",
        "side": "LONG",
        "quantity": 0.1,
        "leverage": 1,
        "entry_zone": {"low": 50000, "high": 50000},
        "stop_loss": 49000,
        "take_profit": 55000,
        "setup_type": "Breakout",
    }

    exec.execute_params(params)

    # Mock commit to fail
    with patch("sqlalchemy.orm.Session.commit") as mock_commit:
        mock_commit.side_effect = Exception("DB Disk Full")
        exec.update_price(50000) # Open position triggers here

    assert exec.position is None
    assert exec.active_trade_plan is None
    assert exec.balance == 10000.0

    assert db.query(Trade).count() == 0
    assert db.query(Position).count() == 0
    assert db.query(ActiveTradePlan).count() == 0

    assert exec.pending_setup is not None
    db.close()

def test_atomic_open_position_success(isolated_test_db):
    import src.execution.executor as exec_mod
    db = exec_mod.SessionLocal()
    exec = LocalPaperExecutor(initial_balance=10000.0)

    params = {
        "symbol": "BTCUSDT",
        "side": "LONG",
        "quantity": 0.1,
        "leverage": 1,
        "entry_zone": {"low": 50000, "high": 50000},
        "stop_loss": 49000,
        "take_profit": 55000,
        "setup_type": "Breakout",
    }

    exec.execute_params(params)
    exec.update_price(50000)

    assert exec.position is not None
    assert exec.active_trade_plan is not None
    assert exec.balance < 10000.0

    assert db.query(Trade).count() == 1
    assert db.query(Position).count() == 1
    assert db.query(ActiveTradePlan).count() == 1
    db.close()
