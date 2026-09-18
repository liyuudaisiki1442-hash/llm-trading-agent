import pytest
from src.execution.executor import LocalPaperExecutor
from src.storage.database import SessionLocal
from src.storage.models import Position

def test_stop_loss_tightening_long(isolated_test_db):
    exec = LocalPaperExecutor(initial_balance=10000)
    params = {
        "symbol": "BTCUSDT",
        "side": "LONG",
        "quantity": 0.1,
        "leverage": 1,
        "entry_zone": {"low": 50000, "high": 50000},
        "stop_loss": 49000,
        "take_profit": 55000
    }
    exec.execute_params(params)
    exec.update_price(50000) # Open position

    assert exec.position["stop_loss"] == 49000

    # Valid tightening: SL raised to 49500, price is 51000
    exec.update_stop_loss(49500, 51000)
    assert exec.position["stop_loss"] == 49500

    # DB persistence check
    import src.execution.executor as executor_module
    db = executor_module.SessionLocal()
    db_pos = db.query(Position).first()
    assert db_pos.stop_loss == 49500
    db.close()

    # Invalid widening: Try lowering SL to 48000
    exec.update_stop_loss(48000, 51000)
    assert exec.position["stop_loss"] == 49500 # Unchanged

    # Invalid crossing: Try raising SL above current price
    exec.update_stop_loss(52000, 51000)
    assert exec.position["stop_loss"] == 49500 # Unchanged


def test_stop_loss_tightening_short(isolated_test_db):
    exec = LocalPaperExecutor(initial_balance=10000)
    params = {
        "symbol": "BTCUSDT",
        "side": "SHORT",
        "quantity": 0.1,
        "leverage": 1,
        "entry_zone": {"low": 50000, "high": 50000},
        "stop_loss": 51000,
        "take_profit": 45000
    }
    exec.execute_params(params)
    exec.update_price(50000) # Open

    assert exec.position["stop_loss"] == 51000

    # Valid tightening: SL lowered to 50500, price is 49000
    exec.update_stop_loss(50500, 49000)
    assert exec.position["stop_loss"] == 50500

    # DB persistence check
    import src.execution.executor as executor_module
    db = executor_module.SessionLocal()
    db_pos = db.query(Position).first()
    assert db_pos.stop_loss == 50500
    db.close()

    # Invalid widening: Try raising SL back to 52000
    exec.update_stop_loss(52000, 49000)
    assert exec.position["stop_loss"] == 50500 # Unchanged

    # Invalid crossing: Try lowering SL below current price
    exec.update_stop_loss(48000, 49000)
    assert exec.position["stop_loss"] == 50500 # Unchanged


from unittest.mock import patch

def test_stop_loss_missing_db_row(isolated_test_db):
    exec = LocalPaperExecutor(initial_balance=10000)
    params = {
        "symbol": "BTCUSDT",
        "side": "LONG",
        "quantity": 0.1,
        "leverage": 1,
        "entry_zone": {"low": 50000, "high": 50000},
        "stop_loss": 49000,
        "take_profit": 55000
    }
    exec.execute_params(params)
    exec.update_price(50000) # Open position

    # Simulate DB row deletion
    import src.execution.executor as executor_module
    db = executor_module.SessionLocal()
    db.query(Position).delete()
    db.commit()
    db.close()

    exec.update_stop_loss(49500, 51000)

    # Memory should remain unchanged because DB update failed
    assert exec.position["stop_loss"] == 49000

def test_stop_loss_db_commit_failure(isolated_test_db):
    exec = LocalPaperExecutor(initial_balance=10000)
    params = {
        "symbol": "BTCUSDT",
        "side": "LONG",
        "quantity": 0.1,
        "leverage": 1,
        "entry_zone": {"low": 50000, "high": 50000},
        "stop_loss": 49000,
        "take_profit": 55000
    }
    exec.execute_params(params)
    exec.update_price(50000) # Open position

    # Mock commit to throw Exception
    with patch("sqlalchemy.orm.Session.commit") as mock_commit:
        mock_commit.side_effect = Exception("DB Connection Lost")
        exec.update_stop_loss(49500, 51000)

    # Memory should remain unchanged because DB commit raised Exception
    assert exec.position["stop_loss"] == 49000

def test_stop_loss_unknown_side(isolated_test_db):
    exec = LocalPaperExecutor(initial_balance=10000)
    params = {
        "symbol": "BTCUSDT",
        "side": "LONG",
        "quantity": 0.1,
        "leverage": 1,
        "entry_zone": {"low": 50000, "high": 50000},
        "stop_loss": 49000,
        "take_profit": 55000
    }
    exec.execute_params(params)
    exec.update_price(50000)

    # Hack the memory state to an unknown side
    exec.position["side"] = "UNKNOWN_SIDE"
    exec.update_stop_loss(49500, 51000)
    assert exec.position["stop_loss"] == 49000
