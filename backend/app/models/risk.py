from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field, Column, Text
from app.models.base import TimestampMixin, new_uuid


class RiskAssessment(SQLModel, TimestampMixin, table=True):
    __tablename__ = "risk_assessments"

    id: str = Field(default_factory=new_uuid, primary_key=True)
    toe_id: str = Field(foreign_key="toes.id", index=True)
    threat_id: str = Field(foreign_key="threats.id", index=True, unique=True)
    residual_risk: str = Field(max_length=32)  # accepted|mitigated|transferred|avoided
    mitigation_notes: Optional[str] = Field(default=None, sa_column=Column(Text))
    assessor: Optional[str] = Field(default=None, max_length=128)
    assessed_at: datetime = Field(default_factory=lambda: __import__('datetime').datetime.now(__import__('datetime').timezone.utc))


class TOERiskCache(SQLModel, table=True):
    """Cached risk dashboard data for a TOE."""
    __tablename__ = "toe_risk_cache"

    toe_id: str = Field(foreign_key="toes.id", primary_key=True)
    risk_score: int = Field(default=0)
    risk_level: str = Field(default="low", max_length=16)
    ai_summary: Optional[str] = Field(default=None, sa_column=Column(Text))
    calculated_at: Optional[datetime] = Field(default=None)
    ai_generated_at: Optional[datetime] = Field(default=None)
    is_stale: bool = Field(default=True)


class BlindSpotSuggestion(SQLModel, TimestampMixin, table=True):
    """AI-generated blind spot suggestion for a TOE."""
    __tablename__ = "blind_spot_suggestions"

    id: str = Field(default_factory=new_uuid, primary_key=True)
    toe_id: str = Field(foreign_key="toes.id", index=True)
    category: str = Field(max_length=32)  # asset, threat, sfr, test, general
    content: str = Field(sa_column=Column(Text))
    is_ignored: bool = Field(default=False)
