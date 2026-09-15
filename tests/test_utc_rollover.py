import pytest
from src.execution.executor import LocalPaperExecutor
from src.storage.models import AccountSnapshot
from unittest.mock import patch
from datetime import datetime, timedelta

def test_utc_rollover_without_restart(isolated_test_db):
    import src.execution.executor as executor_module
    executor_module.SessionLocal.configure(bind=isolated_test_db)
    db = executor_module.SessionLocal()
    # Ensure empty
    db.query(AccountSnapshot).delete()
    db.commit()

    # Initialize executor (will create today's snapshot)
    today = datetime.utcnow().date()
    executor = LocalPaperExecutor(initial_balance=10000.0)

    snapshot1 = db.query(AccountSnapshot).filter(AccountSnapshot.date == datetime(today.year, today.month, today.day)).first()
    assert snapshot1 is not None
    assert snapshot1.equity == 10000.0

    # Fast forward time to tomorrow
    tomorrow = today + timedelta(days=1)
    tomorrow_dt = datetime(tomorrow.year, tomorrow.month, tomorrow.day)

    class MockDatetime(datetime):
        @classmethod
        def utcnow(cls):
            return datetime.utcnow() + timedelta(days=1)

    with patch("src.execution.executor.datetime", MockDatetime):
        # Tick price (should trigger rollover check)
        # Note: the in-memory cache _last_snapshot_date should detect the change
        executor.update_price(50000)

    snapshot2 = db.query(AccountSnapshot).filter(AccountSnapshot.date == tomorrow_dt).first()
    assert snapshot2 is not None
    assert snapshot2.equity == 10000.0
