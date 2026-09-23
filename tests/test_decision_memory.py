import pytest
import asyncio
from datetime import datetime, timedelta
from src.main import TradingBot
from src.execution.executor import LocalPaperExecutor
from src.storage.database import SessionLocal
from src.storage.models import Decision, ActiveTradePlan, Position, Trade

@pytest.mark.asyncio
async def test_recent_decision_loading(isolated_test_db, monkeypatch):
    import src.main as main_mod
    bot = TradingBot()
    # explicitly fetch isolated engine
    db = main_mod.SessionLocal()
    db.query(Decision).delete()
    db.commit()
    # Insert 6 decisions
    now = datetime.utcnow()
    for i in range(6):
        d = Decision(
            symbol="BTCUSDT",
            action="WAIT",
            confidence=0.5 + (i * 0.1),
            setup_type=f"Setup {i}",
            entry_zone_low=49000 + i,
            entry_zone_high=50000 + i,
            invalidation_price=48000 + i,
            first_obstacle=51000 + i,
            reasoning_summary=f"Decision {i}",
            timestamp=now + timedelta(seconds=i),
            is_valid=True
        )
        db.add(d)
    db.commit()
    db.close()

    # We will just patch llm_client.get_decision to inspect context_json
    captured_context = None
    async def mock_get_decision(context_json):
        nonlocal captured_context
        captured_context = context_json
        return None

    bot.llm_client.get_decision = mock_get_decision
    bot.executor = LocalPaperExecutor(initial_balance=10000.0)

    await bot.run_decision_cycle()

    assert captured_context is not None
    import json
    ctx = json.loads(captured_context)

    recent_decisions = ctx.get("recent_decisions", [])
    assert len(recent_decisions) == 5

    # Check chronological order and specific fields for last element (chronologically newest)
    last_decision = recent_decisions[-1]
    assert last_decision["reasoning_summary"] == "Decision 5"
    assert last_decision["confidence"] == 1.0
    assert last_decision["setup_type"] == "Setup 5"
    assert last_decision["entry_zone_low"] == 49005
    assert last_decision["entry_zone_high"] == 50005
    assert last_decision["invalidation_price"] == 48005
    assert last_decision["first_obstacle"] == 51005

    # Check first element (chronologically oldest retained)
    first_decision = recent_decisions[0]
    assert first_decision["reasoning_summary"] == "Decision 1"
    assert first_decision["confidence"] == 0.6
    assert first_decision["setup_type"] == "Setup 1"
    assert first_decision["entry_zone_low"] == 49001
    assert first_decision["entry_zone_high"] == 50001
    assert first_decision["invalidation_price"] == 48001
    assert first_decision["first_obstacle"] == 51001

@pytest.mark.asyncio
async def test_active_trade_plan_lifecycle(isolated_test_db):
    import src.execution.executor as executor_module
    db = executor_module.SessionLocal()
    db.query(Position).delete()
    db.query(Trade).delete()
    db.query(ActiveTradePlan).delete()
    db.commit()

    executor = LocalPaperExecutor(initial_balance=10000.0)

    params = {
        "symbol": "BTCUSDT",
        "side": "LONG",
        "quantity": 0.1,
        "leverage": 1,
        "entry_zone": {"low": 50000, "high": 50000},
        "stop_loss": 49000,
        "take_profit": 55000,
        "setup_type": "Breakout",
        "entry_reason": "High volume breakout",
        "first_obstacle": 51000,
        "market_regime": "Uptrend"
    }

    # 1. Pending setup should NOT create ActiveTradePlan
    executor.execute_params(params)
    assert db.query(ActiveTradePlan).count() == 0
    assert executor.active_trade_plan is None

    # 2. Fill position should CREATE ActiveTradePlan
    executor.update_price(50000)

    plan = db.query(ActiveTradePlan).first()
    assert plan is not None
    assert plan.setup_type == "Breakout"

    assert executor.active_trade_plan is not None
    assert executor.active_trade_plan["setup_type"] == "Breakout"

    # 3. Simulate restart
    executor2 = LocalPaperExecutor(initial_balance=10000.0)
    assert executor2.active_trade_plan is not None
    assert executor2.active_trade_plan["setup_type"] == "Breakout"

    # 4. Close position should REMOVE ActiveTradePlan
    executor2.update_price(55000) # Hit TP

    assert db.query(ActiveTradePlan).count() == 0
    assert executor2.active_trade_plan is None
    db.close()

def test_legacy_position_compatibility(isolated_test_db):
    import src.execution.executor as executor_module
    db = executor_module.SessionLocal()
    db.query(Position).delete()
    db.query(Trade).delete()
    db.query(ActiveTradePlan).delete()
    db.commit()
    db_trade = Trade(symbol="BTCUSDT", side="LONG", entry_price=50000.0, quantity=0.1, leverage=1.0, status="OPEN")
    db.add(db_trade)
    db_pos = Position(symbol="BTCUSDT", side="LONG", entry_price=50000.0, quantity=0.1, leverage=1.0, stop_loss=49000.0, take_profit=55000.0)
    db.add(db_pos)
    db.commit()
    db.close()

    executor = LocalPaperExecutor(initial_balance=10000.0)
    assert executor.position is not None
    assert executor.active_trade_plan is None # Safely handled

from src.risk.manager import RiskManager
from src.agent.schemas import TradeDecision
from src.features.market_context import MarketContext, PositionState, TimeframeContext

def test_risk_manager_to_executor_passthrough(isolated_test_db):
    import src.execution.executor as executor_module
    db = executor_module.SessionLocal()
    db.query(Position).delete()
    db.query(Trade).delete()
    db.query(ActiveTradePlan).delete()
    db.commit()

    decision = TradeDecision(
        action="LONG",
        confidence=0.9,
        setup_type="Breakout Retest",
        entry_reason="Testing passthrough",
        entry_zone={"low": 49000, "high": 50000},
        invalidation_price=48000,
        stop_loss=48500,
        take_profit_targets=[55000],
        first_obstacle=52000,
        market_regime="Uptrend Volatile",
        reasoning_summary="Because testing",
        warnings=[]
    )

    ctx = MarketContext(
        symbol="BTCUSDT",
        position_state=PositionState(has_position=False),
        tf_1h=TimeframeContext(timeframe="1H", trend="UP", current_price=49500),
        tf_15m=TimeframeContext(timeframe="15M", trend="UP", current_price=49500),
        tf_5m=TimeframeContext(timeframe="5M", trend="UP", current_price=49500)
    )

    rm = RiskManager()
    is_approved, _, params = rm.calculate_position(decision, ctx, 10000.0)
    assert is_approved

    # Verify RiskManager correctly populated the fields
    assert params["setup_type"] == "Breakout Retest"
    assert params["entry_reason"] == "Testing passthrough"
    assert params["invalidation_price"] == 48000
    assert params["first_obstacle"] == 52000
    assert params["market_regime"] == "Uptrend Volatile"

    # Pass to executor
    executor = LocalPaperExecutor(initial_balance=10000.0)
    executor.execute_params(params)
    executor.update_price(49500)

    # Assert DB is correctly loaded
    plan = db.query(ActiveTradePlan).first()
    assert plan is not None
    assert plan.setup_type == "Breakout Retest"
    assert plan.entry_reason == "Testing passthrough"
    assert plan.invalidation_price == 48000
    assert plan.original_first_obstacle == 52000
    assert plan.market_regime == "Uptrend Volatile"
    assert plan.original_stop_loss == 48500
    assert plan.original_take_profit == 55000
    assert plan.entry_zone_low == 49000
    assert plan.entry_zone_high == 50000

    db.close()
