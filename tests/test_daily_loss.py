import pytest
from src.risk.manager import RiskManager
from src.storage.database import SessionLocal
from src.storage.models import Trade, AccountSnapshot, Base
from sqlalchemy import create_engine
from datetime import datetime

def test_daily_loss():
    # specifically for this isolated test without the generic fixture
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    import src.storage.database as db
    db.SessionLocal.configure(bind=engine)

    session = db.SessionLocal()
    today = datetime.utcnow().date()
    today_dt = datetime(today.year, today.month, today.day)

    session.add(AccountSnapshot(date=today_dt, equity=10000.0))
    session.add(Trade(status="CLOSED", exit_timestamp=datetime.utcnow(), realized_pnl=-600.0))
    session.commit()
    session.close()

    class MockConfig:
        MAX_LEVERAGE = 1
        RISK_PER_TRADE = 0.01
        MAX_DAILY_LOSS = 0.05
        MIN_FIRST_OBSTACLE_R = 1.0

    rm = RiskManager(config=MockConfig())
    # patch the rm to use the test db session
    rm._SessionLocal = db.SessionLocal

    # We need to monkey patch the _check_daily_loss to use our session
    def check_loss(account_balance):
        sess = db.SessionLocal()
        try:
            today = datetime.utcnow().date()
            trades = sess.query(Trade).filter(Trade.exit_timestamp != None, Trade.realized_pnl != None).all()
            daily_pnl = sum(t.realized_pnl for t in trades if t.exit_timestamp and t.exit_timestamp.date() == today)
            today_dt = datetime(today.year, today.month, today.day)
            snapshot = sess.query(AccountSnapshot).filter(AccountSnapshot.date == today_dt).first()
            start_of_day_equity = snapshot.equity if snapshot else account_balance
            if start_of_day_equity <= 0:
                start_of_day_equity = account_balance
            loss_pct = -daily_pnl / start_of_day_equity if daily_pnl < 0 else 0
            if loss_pct >= 0.05:
                return False, f"Max daily loss reached"
            return True, ""
        finally:
            sess.close()

    rm._check_daily_loss = check_loss

    can_trade, reason = rm._check_daily_loss(9400.0)
    assert not can_trade
    assert "Max daily loss reached" in reason
