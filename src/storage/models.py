from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime

Base = declarative_base()

class Decision(Base):
    __tablename__ = "decisions"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    action = Column(String)  # LONG, SHORT, WAIT, HOLD, CLOSE
    confidence = Column(Float)
    setup_type = Column(String)
    entry_zone_low = Column(Float, nullable=True)
    entry_zone_high = Column(Float, nullable=True)
    invalidation_price = Column(Float, nullable=True)
    first_obstacle = Column(Float, nullable=True)
    risk_reward_calc = Column(Float, nullable=True)  # Deterministic calculation
    reasoning_summary = Column(String)
    is_valid = Column(Boolean)
    rejection_reason = Column(String, nullable=True)

class Trade(Base):
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, index=True)
    entry_timestamp = Column(DateTime, default=datetime.utcnow)
    exit_timestamp = Column(DateTime, nullable=True)
    side = Column(String)
    entry_price = Column(Float)
    exit_price = Column(Float, nullable=True)
    quantity = Column(Float)
    leverage = Column(Float)
    realized_pnl = Column(Float, nullable=True)
    trading_fees = Column(Float, nullable=True)
    status = Column(String) # OPEN, CLOSED

class Position(Base):
    __tablename__ = "positions"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, unique=True, index=True)
    side = Column(String)
    entry_price = Column(Float)
    quantity = Column(Float)
    leverage = Column(Float)
    stop_loss = Column(Float, nullable=True)
    take_profit = Column(Float, nullable=True)
    unrealized_pnl = Column(Float, default=0.0)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class SystemEvent(Base):
    __tablename__ = "system_events"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    event_type = Column(String) # ERROR, INFO, STARTUP, SHUTDOWN
    message = Column(String)
