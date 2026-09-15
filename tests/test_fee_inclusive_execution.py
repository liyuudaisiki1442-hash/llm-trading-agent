import pytest
from src.agent.schemas import TradeDecision
from src.features.market_context import MarketContext, PositionState, TimeframeContext
from src.risk.manager import RiskManager
from src.execution.executor import LocalPaperExecutor

def get_params_for_decision(action, entry_low, entry_high, sl, tp, risk_pct):
    ctx = MarketContext(
        symbol="BTCUSDT",
        position_state=PositionState(has_position=False),
        tf_1h=TimeframeContext(timeframe="1H", trend="UP", current_price=entry_high),
        tf_15m=TimeframeContext(timeframe="15M", trend="UP", current_price=entry_high),
        tf_5m=TimeframeContext(timeframe="5M", trend="UP", current_price=entry_high),
    )
    dec = TradeDecision(
        action=action,
        reasoning_summary="test",
        stop_loss=sl,
        take_profit_targets=[tp],
        entry_zone={"low": entry_low, "high": entry_high}
    )
    class MockConfig:
        MAX_LEVERAGE = 10
        RISK_PER_TRADE = risk_pct
        MAX_POSITIONS = 1
        MAX_DAILY_LOSS = 0.05
        MIN_FIRST_OBSTACLE_R = 1.0

    rm = RiskManager(config=MockConfig())
    rm._check_daily_loss = lambda bal: (True, "")
    is_appr, _, params = rm.calculate_position(dec, ctx, 10000.0)
    return is_appr, params

def test_fee_inclusive_loss_at_stop_long_low_entry(isolated_test_db):
    initial_balance = 10000.0
    risk_pct = 0.01 # Max loss 100.0
    # For LONG worst case entry is zone high (50000). SL=49000
    is_appr, params = get_params_for_decision("LONG", 49500, 50000, 49000, 55000, risk_pct)
    assert is_appr

    executor = LocalPaperExecutor(initial_balance=initial_balance)
    executor.execute_params(params)

    # Enter at zone low (49500) -> actual risk here is smaller than worst case 50000
    executor.update_price(49500)
    assert executor.position is not None

    # Hit SL
    executor.update_price(49000)
    assert executor.position is None

    loss = initial_balance - executor.balance
    assert loss <= initial_balance * risk_pct + 1e-6

def test_fee_inclusive_loss_at_stop_long_high_entry(isolated_test_db):
    initial_balance = 10000.0
    risk_pct = 0.01
    # For LONG worst case entry is zone high (50000). SL=49000
    is_appr, params = get_params_for_decision("LONG", 49500, 50000, 49000, 55000, risk_pct)
    assert is_appr

    executor = LocalPaperExecutor(initial_balance=initial_balance)
    executor.execute_params(params)

    # Enter at worst case (zone high)
    executor.update_price(50000)
    assert executor.position is not None

    # Hit SL
    executor.update_price(49000)
    assert executor.position is None

    loss = initial_balance - executor.balance
    assert loss <= initial_balance * risk_pct + 1e-6

def test_fee_inclusive_loss_at_stop_short_low_entry(isolated_test_db):
    initial_balance = 10000.0
    risk_pct = 0.01
    # For SHORT worst case entry is zone low (49500). SL=50500
    is_appr, params = get_params_for_decision("SHORT", 49500, 50000, 50500, 45000, risk_pct)
    assert is_appr

    executor = LocalPaperExecutor(initial_balance=initial_balance)
    executor.execute_params(params)

    # Enter at worst case (zone low)
    executor.update_price(49500)
    assert executor.position is not None

    # Hit SL
    executor.update_price(50500)
    assert executor.position is None

    loss = initial_balance - executor.balance
    assert loss <= initial_balance * risk_pct + 1e-6

def test_fee_inclusive_loss_at_stop_short_high_entry(isolated_test_db):
    initial_balance = 10000.0
    risk_pct = 0.01
    # For SHORT worst case entry is zone low (49500). SL=50500
    is_appr, params = get_params_for_decision("SHORT", 49500, 50000, 50500, 45000, risk_pct)
    assert is_appr

    executor = LocalPaperExecutor(initial_balance=initial_balance)
    executor.execute_params(params)

    # Enter at best case (zone high)
    executor.update_price(50000)
    assert executor.position is not None

    # Hit SL
    executor.update_price(50500)
    assert executor.position is None

    loss = initial_balance - executor.balance
    assert loss <= initial_balance * risk_pct + 1e-6
