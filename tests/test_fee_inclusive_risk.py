import pytest
from src.risk.manager import RiskManager
from src.agent.schemas import TradeDecision
from src.features.market_context import MarketContext, PositionState, TimeframeContext

def test_fee_inclusive_sizing():
    class MockConfig:
        MAX_LEVERAGE = 10
        RISK_PER_TRADE = 0.01 # 100 risk on 10000 balance
        MAX_POSITIONS = 1
        MAX_DAILY_LOSS = 0.05
        MIN_FIRST_OBSTACLE_R = 1.0

    rm = RiskManager(config=MockConfig())
    rm._check_daily_loss = lambda bal: (True, "")

    ctx = MarketContext(
        symbol="BTCUSDT", position_state=PositionState(has_position=False),
        tf_1h=TimeframeContext(timeframe="1H", trend="UP", current_price=50000),
        tf_15m=TimeframeContext(timeframe="15M", trend="UP", current_price=50000),
        tf_5m=TimeframeContext(timeframe="5M", trend="UP", current_price=50000),
    )

    # LONG entry zone high = 50000. SL = 49000. TP = 55000
    # Price difference risk = 1000
    # Expected fee risk = (50000 * 0.0004) + (49000 * 0.0004) = 20 + 19.6 = 39.6
    # Total effective risk per unit = 1039.6
    # Target total risk = 100
    # Quantity = 100 / 1039.6 = 0.0961908
    dec = TradeDecision(action="LONG", reasoning_summary="", stop_loss=49000, take_profit_targets=[55000], entry_zone={"low": 49000, "high": 50000})

    is_appr, reason, params = rm.calculate_position(dec, ctx, 10000)
    assert is_appr
    assert abs(params["quantity"] - (100 / 1039.6)) < 0.0001

    # SHORT entry zone low = 49000. SL = 50000. TP = 40000
    # Price difference risk = 1000
    # Expected fee risk = (49000 * 0.0004) + (50000 * 0.0004) = 19.6 + 20 = 39.6
    # Quantity = 100 / 1039.6
    dec2 = TradeDecision(action="SHORT", reasoning_summary="", stop_loss=50000, take_profit_targets=[40000], entry_zone={"low": 49000, "high": 50000})
    is_appr2, reason2, params2 = rm.calculate_position(dec2, ctx, 10000)
    assert is_appr2
    assert abs(params2["quantity"] - (100 / 1039.6)) < 0.0001
