from pydantic import BaseModel, Field, model_validator
from typing import List, Optional

class EntryZone(BaseModel):
    low: float
    high: float

class TradeDecision(BaseModel):
    action: str = Field(description="Must be LONG, SHORT, WAIT, HOLD, or CLOSE")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    setup_type: Optional[str] = Field(default=None, description="e.g. Breakout Retest, Trend Continuation")
    entry_reason: Optional[str] = None
    entry_zone: Optional[EntryZone] = None
    invalidation_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit_targets: Optional[List[float]] = None
    first_obstacle: Optional[float] = None
    market_regime: Optional[str] = None
    reasoning_summary: str = Field(description="Concise summary of evidence")
    warnings: Optional[List[str]] = Field(default_factory=list)

    @model_validator(mode='after')
    def validate_action_semantics(self) -> 'TradeDecision':
        valid_actions = {"LONG", "SHORT", "WAIT", "HOLD", "CLOSE"}
        if self.action not in valid_actions:
            raise ValueError(f"Invalid action {self.action}. Must be one of {valid_actions}")
        return self
