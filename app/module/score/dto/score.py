from datetime import date
from typing import Optional

from pydantic import BaseModel


class ScoreComponentDto(BaseModel):
    key: str
    name: str
    description: str
    weight: float
    score: float
    points: float
    max_points: float
    has_data: bool
    detail: str


class ScoreTierDto(BaseModel):
    key: str
    name: str
    description: str
    min_score: int
    max_score: int


class ScoreHistoryPointDto(BaseModel):
    year: int
    month: int
    label: str
    period_start: date
    score: float


class FinclarScoreDto(BaseModel):
    year: int
    month: int
    label: str
    period_start: date
    period_end: date
    score: float
    previous_score: Optional[float] = None
    delta: Optional[float] = None
    has_data: bool
    tier: ScoreTierDto
    next_tier: Optional[ScoreTierDto] = None
    points_to_next_tier: Optional[float] = None
    components: list[ScoreComponentDto]
    tiers: list[ScoreTierDto]
    history: list[ScoreHistoryPointDto]
