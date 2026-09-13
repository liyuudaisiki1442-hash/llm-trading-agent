import pytest
from unittest.mock import patch
from src.risk.manager import RiskManager
from src.risk.validation import DecisionValidator
from src.agent.schemas import TradeDecision
from src.features.market_context import MarketContext, PositionState, TimeframeContext

def test_validation_tp_sl_direction():
    validator = DecisionValidator()

    ctx = MarketContext(
        symbol="BTCUSDT",
        position_state=PositionState(has_position=False),
        tf_1h=TimeframeContext(timeframe="1H", trend="UP", current_price=50000),
        tf_15m=TimeframeContext(timeframe="15M", trend="UP", current_price=50000),
        tf_5m=TimeframeContext(timeframe="5M", trend="UP", current_price=50000),
    )

    # Valid LONG
    dec = TradeDecision(action="LONG", reasoning_summary="test", stop_loss=49000, take_profit_targets=[52000], entry_zone={"low": 49500, "high": 50500})
    is_valid, _ = validator.validate(dec, ctx)
    assert is_valid

    # Invalid LONG (TP below entry)
    dec = TradeDecision(action="LONG", reasoning_summary="test", stop_loss=49000, take_profit_targets=[49500], entry_zone={"low": 49600, "high": 50500})
    is_valid, reason = validator.validate(dec, ctx)
    assert not is_valid
    assert "LONG requires Stop Loss" in reason

    # Valid SHORT
    dec = TradeDecision(action="SHORT", reasoning_summary="test", stop_loss=51000, take_profit_targets=[48000], entry_zone={"low": 49500, "high": 50500})
    is_valid, _ = validator.validate(dec, ctx)
    assert is_valid

    # Invalid SHORT (TP above entry)
    dec = TradeDecision(action="SHORT", reasoning_summary="test", stop_loss=51000, take_profit_targets=[52000], entry_zone={"low": 49500, "high": 50500})
    is_valid, reason = validator.validate(dec, ctx)
    assert not is_valid
    assert "SHORT requires Take Profit" in reason

def test_risk_manager_sizing_and_leverage():
    # Setup test with mock settings
    class MockConfig:
        MAX_LEVERAGE = 10
        RISK_PER_TRADE = 0.01
        MAX_POSITIONS = 1
        MAX_DAILY_LOSS = 0.05

    rm = RiskManager(config=MockConfig())
    # Mock out DB calls for daily loss
    rm._check_daily_loss = lambda bal: (True, "")

    ctx = MarketContext(
        symbol="BTCUSDT",
        position_state=PositionState(has_position=False),
        tf_1h=TimeframeContext(timeframe="1H", trend="UP", current_price=50000),
        tf_15m=TimeframeContext(timeframe="15M", trend="UP", current_price=50000),
        tf_5m=TimeframeContext(timeframe="5M", trend="UP", current_price=50000),
    )

    # Balance 10000, Risk 1% = 100
    # Entry 50000, SL 49000 -> Risk per unit = 1000
    # Quantity should be 100 / 1000 = 0.1
    # Position Value = 0.1 * 50000 = 5000
    # Required leverage = 5000 / 10000 = 0.5 -> should be clamped to 1.0
    dec = TradeDecision(action="LONG", reasoning_summary="test", stop_loss=49000, take_profit_targets=[52000], entry_zone={"low": 50000, "high": 50000})

    is_approved, reason, params = rm.calculate_position(dec, ctx, 10000)
    assert is_approved
    assert params["quantity"] == 0.1
    assert params["leverage"] == 1.0

    # Tight stop -> higher leverage
    # Entry 50000, SL 49900 -> Risk per unit = 100
    # Quantity = 100 / 100 = 1.0
    # Position Value = 50000
    # Required leverage = 50000 / 10000 = 5.0
    dec = TradeDecision(action="LONG", reasoning_summary="test", stop_loss=49900, take_profit_targets=[52000], entry_zone={"low": 50000, "high": 50000})
    is_approved, reason, params = rm.calculate_position(dec, ctx, 10000)
    assert is_approved
    assert params["quantity"] == 1.0
    assert params["leverage"] == 5.0

    # Extremely tight stop (exceeds max leverage 10)
    # Entry 50000, SL 49950 -> Risk per unit = 50
    # Quantity (ideal) = 100 / 50 = 2.0 -> Value = 100000 -> leverage 10
    dec = TradeDecision(action="LONG", reasoning_summary="test", stop_loss=49950, take_profit_targets=[52000], entry_zone={"low": 50000, "high": 50000})
    is_approved, reason, params = rm.calculate_position(dec, ctx, 10000)
    assert is_approved
    assert params["quantity"] == 2.0
    assert params["leverage"] == 10.0

    # Even tighter stop -> should clamp value to max leverage and reduce risk
    # Entry 50000, SL 49990 -> Risk per unit = 10
    # Quantity (ideal) = 100 / 10 = 10.0 -> Value = 500000 (leverage 50 > max 10)
    # Max value = 100000 -> Quantity = 2.0 -> Risk = 20
    dec = TradeDecision(action="LONG", reasoning_summary="test", stop_loss=49990, take_profit_targets=[52000], entry_zone={"low": 50000, "high": 50000})
    is_approved, reason, params = rm.calculate_position(dec, ctx, 10000)
    assert is_approved
    assert params["quantity"] == 2.0
    assert params["leverage"] == 10.0
    assert params["risk_amount"] == 100.0 # original target risk

def test_first_obstacle():
    class MockConfig:
        MAX_LEVERAGE = 10
        RISK_PER_TRADE = 0.01
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

    # Entry 50000, SL 49000, TP 52000. Risk = 1000.
    # First obstacle 50500 -> R = 500 / 1000 = 0.5 < 1.0 (should reject)
    dec = TradeDecision(action="LONG", reasoning_summary="test", stop_loss=49000, take_profit_targets=[52000], entry_zone={"low": 50000, "high": 50000}, first_obstacle=50500)
    is_appr, reason, _ = rm.calculate_position(dec, ctx, 10000)
    assert not is_appr
    assert "First obstacle R" in reason
