"""
api/schemas.py — Pydantic models for the ViralWatch FastAPI service.

Keeping these separate from main.py so the request/response contracts are
easy to scan on their own, and easy to reuse if we add more endpoints later.
"""

from pydantic import BaseModel, Field
from typing import Optional


# =========================================================================
# /predict/{zone}
# =========================================================================
class ZonePredictionResponse(BaseModel):
    zone: str = Field(..., description="Canonical health-zone name (nom_clean)")
    province: str
    cross_border_watch: bool = Field(
        ..., description="True if this zone is in Nord-Kivu or Sud-Kivu (bordering Rwanda)"
    )
    has_case_data: bool = Field(
        ..., description="False if this zone has no rows in daily_cases yet"
    )
    cumulative_confirmed_cases: float
    days_since_first_case: int
    population_density: float
    next_7d_onset_probability: float = Field(
        ..., description="Keras model's probability this zone reports new cases in the next 7 days"
    )
    baseline_rf_probability: float = Field(
        ..., description="Day 3 scikit-learn RandomForest baseline, for comparison against the Keras model"
    )


# =========================================================================
# /earlywarning
# =========================================================================
class EarlyWarningZone(BaseModel):
    zone: str
    province: str
    cross_border_watch: bool
    date: str = Field(..., description="Date of this zone's most recent anomaly score")
    anomaly_score: float = Field(
        ..., description="Higher = more anomalous, per Day 4's One-Class SVM (score is not a probability)"
    )
    rank: int


class EarlyWarningResponse(BaseModel):
    generated_from_date: str = Field(..., description="Most recent date present across scored zones")
    zone_count: int
    zones: list[EarlyWarningZone]


# =========================================================================
# /briefing
# =========================================================================
class CaseDeathCount(BaseModel):
    value: int
    type: str
    context: str


class ParagraphSeverity(BaseModel):
    paragraph: str
    label: str
    confidence: float


class BulletinBriefing(BaseModel):
    bulletin: str
    locations_mentioned: list[str]
    case_death_counts: list[CaseDeathCount]
    paragraph_severity: list[ParagraphSeverity]
    most_severe_paragraph: Optional[ParagraphSeverity] = None


class BriefingResponse(BaseModel):
    latest_bulletin: BulletinBriefing
    bulletin_count: int
