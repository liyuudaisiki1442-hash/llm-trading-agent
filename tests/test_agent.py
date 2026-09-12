import pytest
from src.agent.schemas import TradeDecision
from pydantic import ValidationError

def test_trade_decision_validation():
    # Valid
    d = TradeDecision(action="LONG", reasoning_summary="Looks good")
    assert d.action == "LONG"

    # Invalid action
    with pytest.raises(ValidationError):
        TradeDecision(action="BUY", reasoning_summary="Invalid action")

    # Valid HOLD
    d = TradeDecision(action="HOLD", reasoning_summary="Hold it")
    assert d.action == "HOLD"
