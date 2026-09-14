import pytest
from unittest.mock import patch
from src.agent.schemas import TradeDecision
from src.features.market_context import MarketContext, PositionState, TimeframeContext
from src.risk.validation import DecisionValidator
from src.risk.manager import RiskManager
from src.execution.executor import LocalPaperExecutor
from src.storage.database import engine
from src.storage.models import Base

def test_end_to_end_paper_execution():

    # 1. Provide Context
    ctx = MarketContext(
        symbol="BTCUSDT",
        position_state=PositionState(has_position=False),
        tf_1h=TimeframeContext(timeframe="1H", trend="UP", current_price=50000),
        tf_15m=TimeframeContext(timeframe="15M", trend="UP", current_price=50000),
        tf_5m=TimeframeContext(timeframe="5M", trend="UP", current_price=50000),
    )

    # 2. LLM Decision (TradeDecision)
    dec = TradeDecision(
        action="LONG",
        reasoning_summary="E2E test",
        stop_loss=49000,
        take_profit_targets=[52000],
        entry_zone={"low": 49900, "high": 50100},
        first_obstacle=51500
    )

    # 3. Validation
    validator = DecisionValidator()
    is_valid, v_reason = validator.validate(dec, ctx)
    assert is_valid, f"Validation failed: {v_reason}"

    # 4. Risk Manager
    class MockConfig:
        MAX_LEVERAGE = 5
        RISK_PER_TRADE = 0.01 # 100 risk on 10000 balance
        MAX_POSITIONS = 1
        MAX_DAILY_LOSS = 0.05

    rm = RiskManager(config=MockConfig())
    rm._check_daily_loss = lambda bal: (True, "")
    is_appr, r_reason, params = rm.calculate_position(dec, ctx, account_balance=10000)
    assert is_appr, f"Risk rejected: {r_reason}"

    # Quantity logic: Entry is worst case for LONG (highest in zone) = 50100
    # SL = 49000 -> Risk = 1100
    # Quantity = 100 / 1100 = 0.09090909
    # Leverage required = (0.09 * 50100) / 10000 = 0.45 -> clamped to 1.0
    assert abs(params["quantity"] - (100.0/1100.0)) < 0.0001
    assert params["leverage"] == 1.0

    # 5. Local Executor
    executor = LocalPaperExecutor(initial_balance=10000)
    executor.execute_params(params)

    assert executor.pending_setup is not None
    assert executor.position is None

    # Tick inside entry zone
    executor.update_price(50050)

    assert executor.pending_setup is None
    assert executor.position is not None
    assert executor.position["side"] == "LONG"
    assert abs(executor.position["quantity"] - (100.0/1100.0)) < 0.0001

    # 6. Tick to Stop Loss
    executor.update_price(48999)
    assert executor.position is None # SL triggered
    assert executor.realized_pnl < 0
    assert executor.balance < 10000
