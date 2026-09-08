from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field
from typing import Optional

class Direction(str, Enum):
    CALL="CALL"; PUT="PUT"; NONE="NONE"

class Decision(str, Enum):
    BUY="BUY"; NO_TRADE="NO_TRADE"

class FeatureSnapshot(BaseModel):
    timestamp: datetime
    close: float
    vwap: float
    ema9: float
    ema21: float
    ema50: float
    atr: float
    rsi: float
    adx: float
    relative_volume: float
    atr_percentile: float
    vwap_distance_atr: float

class RegimeResult(BaseModel):
    regime: str
    confidence: float = Field(ge=0, le=1)
    evidence: list[str] = Field(default_factory=list)

class SetupCandidate(BaseModel):
    setup_id: str
    direction: Direction
    confidence: float
    entry_reference: float
    invalidation: float
    stop_percent: float
    target_percent: float
    evidence: list[str] = Field(default_factory=list)

class OptionContract(BaseModel):
    security_id: str
    symbol: str
    strike: float
    option_type: str
    ltp: float
    bid: float
    ask: float
    volume: float = 0
    oi: float = 0
    oi_change: float = 0
    iv: Optional[float] = None
    delta: Optional[float] = None
    gamma: Optional[float] = None
    theta: Optional[float] = None
    vega: Optional[float] = None
    spread_pct: float = 0
    score: float = 0

class ExpectancyResult(BaseModel):
    p_target: float
    p_stop: float
    p_no_resolution: float
    target_rupees: float
    stop_rupees: float
    expected_cost_rupees: float
    expected_value_rupees: float

class RiskDecision(BaseModel):
    approved: bool
    quantity: int = 0
    risk_rupees: float = 0
    reason: str = ""
