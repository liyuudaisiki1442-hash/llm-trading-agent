import pytest
from src.risk.manager import RiskManager
from src.agent.schemas import TradeDecision
from src.features.market_context import MarketContext, PositionState, TimeframeContext
from src.execution.executor import LocalPaperExecutor

def test_leverage_calculation():
    class MockConfig:
        MAX_LEVERAGE = 5
        RISK_PER_TRADE = 0.01 # 100 risk
        MAX_POSITIONS = 1
        MAX_DAILY_LOSS = 0.05

    rm = RiskManager(config=MockConfig())
    rm._check_daily_loss = lambda bal: (True, "")

    ctx = MarketContext(
        symbol="BTCUSDT", position_state=PositionState(has_position=False),
        tf_1h=TimeframeContext(timeframe="1H", trend="UP", current_price=50000),
        tf_15m=TimeframeContext(timeframe="15M", trend="UP", current_price=50000),
        tf_5m=TimeframeContext(timeframe="5M", trend="UP", current_price=50000),
    )

    # Very tight stop -> requires large position
    # Entry zone high = 50000 (worst case entry)
    # SL = 49900 -> Risk per unit = 100
    # Risk amount = 100 -> Qty = 1
    # Position value = 50000
    # Required leverage = 50000 / 10000 = 5
    dec = TradeDecision(action="LONG", reasoning_summary="", stop_loss=49900, take_profit_targets=[51000], entry_zone={"low": 49000, "high": 50000})

    is_appr, reason, params = rm.calculate_position(dec, ctx, 10000)
    assert is_appr
    # Because of the buffer max notional is 10000/1.005 * 5 = 49751.24
    # Quantity will be 49751.24 / 50000 = 0.995
    assert params["quantity"] < 1.0
    assert params["leverage"] == 5.0

    # Margin check in executor
    exec = LocalPaperExecutor(initial_balance=10000)
    exec.execute_params(params)

    # Enter at worst case
    exec.update_price(50000)
    assert exec.position is not None
    assert exec.position["quantity"] < 1.0
    # Margin should be ~10000. Balance is 10000. Fee is 50000 * 0.0004 = 20.
    # Actually margin + fee = 10000 + 20 = 10020 > 10000. This should fail!
    # Let's verify the executor rightly rejects it if it doesn't fit.
    # Wait, the assert above says it passed. Let's see what happened.
