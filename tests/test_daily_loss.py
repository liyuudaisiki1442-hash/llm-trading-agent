import pytest
from src.risk.manager import RiskManager
from src.storage.models import Trade, AccountSnapshot, Base
from datetime import datetime, timedelta

def test_daily_loss(isolated_test_db):
    from sqlalchemy.orm import sessionmaker
    TestingSessionLocal = sessionmaker(bind=isolated_test_db)

    db = TestingSessionLocal()
    # Explicitly clear tables since autouse might leak data from previous tests
    db.query(Trade).delete()
    db.query(AccountSnapshot).delete()

    today = datetime.utcnow().date()
    today_dt = datetime(today.year, today.month, today.day)

    db.add(AccountSnapshot(date=today_dt, equity=10000.0))
    db.add(Trade(status="CLOSED", exit_timestamp=datetime.utcnow(), realized_pnl=-600.0))

    yesterday = datetime.utcnow() - timedelta(days=1)
    db.add(Trade(status="CLOSED", exit_timestamp=yesterday, realized_pnl=-1000.0))

    db.commit()

    class MockConfig:
        MAX_LEVERAGE = 1
        RISK_PER_TRADE = 0.01
        MAX_DAILY_LOSS = 0.05 # 5% of 10000 = 500
        MIN_FIRST_OBSTACLE_R = 1.0

    import src.risk.manager as rm_mod
    rm_mod.SessionLocal = TestingSessionLocal
    rm = RiskManager(config=MockConfig())
    # Test the real implementation! No mocked function.
    can_trade, reason = rm._check_daily_loss(9400.0)

    assert not can_trade
    assert "Max daily loss reached" in reason

    # Now simulate only 400 loss today
    today_trades = db.query(Trade).filter(Trade.exit_timestamp >= today_dt).all()
    for t in today_trades:
        t.realized_pnl = -400.0
    db.commit()
    db.close()

    can_trade_2, reason_2 = rm._check_daily_loss(9600.0)
    assert can_trade_2
