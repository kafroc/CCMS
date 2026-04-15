from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field, Column, Text
from app.models.base import TimestampMixin, new_uuid


class Assumption(SQLModel, TimestampMixin, table=True):
    __tablename__ = "assumptions"

    id: str = Field(default_factory=new_uuid, primary_key=True)
    toe_id: str = Field(foreign_key="toes.id", index=True)
    code: str = Field(max_length=64)         # e.g. A.LOCATE
    description: Optional[str] = Field(default=None, sa_column=Column(Text))
    review_status: str = Field(default="draft", max_length=32)  # draft|confirmed|rejected
    ai_generated: bool = Field(default=False)
    reviewed_at: Optional[datetime] = Field(default=None)


class OSP(SQLModel, TimestampMixin, table=True):
    __tablename__ = "osps"

    id: str = Field(default_factory=new_uuid, primary_key=True)
    toe_id: str = Field(foreign_key="toes.id", index=True)
    code: str = Field(max_length=64)         # e.g. P.ACCESS
    description: Optional[str] = Field(default=None, sa_column=Column(Text))
    review_status: str = Field(default="draft", max_length=32)
    ai_generated: bool = Field(default=False)
    reviewed_at: Optional[datetime] = Field(default=None)


class Threat(SQLModel, TimestampMixin, table=True):
    __tablename__ = "threats"

    id: str = Field(default_factory=new_uuid, primary_key=True)
    toe_id: str = Field(foreign_key="toes.id", index=True)
    code: str = Field(max_length=64)         # e.g. T.UNAUTH_ACCESS
    threat_agent: Optional[str] = Field(default=None, sa_column=Column(Text))
    adverse_action: Optional[str] = Field(default=None, sa_column=Column(Text))
    assets_affected: Optional[str] = Field(default=None, sa_column=Column(Text))
    likelihood: str = Field(default="medium", max_length=16)   # low|medium|high
    impact: str = Field(default="medium", max_length=16)       # low|medium|high
    risk_level: str = Field(default="medium", max_length=16)   # low|medium|high|critical
    risk_overridden: bool = Field(default=False)
    review_status: str = Field(default="pending", max_length=32)  # pending|confirmed|false_positive
    ai_rationale: Optional[str] = Field(default=None, sa_column=Column(Text))
    ai_source_ref: Optional[str] = Field(default=None, max_length=256)
    identified_at: Optional[datetime] = Field(default=None)
    reviewed_at: Optional[datetime] = Field(default=None)


class ThreatAssetLink(SQLModel, table=True):
    __tablename__ = "threat_asset_links"

    threat_id: str = Field(foreign_key="threats.id", primary_key=True)
    asset_id: str = Field(foreign_key="toe_assets.id", primary_key=True)


class STReference(SQLModel, TimestampMixin, table=True):
    __tablename__ = "st_references"

    id: str = Field(default_factory=new_uuid, primary_key=True)
    user_id: str = Field(foreign_key="users.id", index=True)
    toe_id: Optional[str] = Field(default=None, foreign_key="toes.id", index=True)
    product_name: str = Field(max_length=256)
    product_type: Optional[str] = Field(default=None, max_length=128)
    toe_type: Optional[str] = Field(default=None, max_length=32)
    cc_version: Optional[str] = Field(default=None, max_length=32)
    source_url: Optional[str] = Field(default=None, max_length=512)
    parse_status: str = Field(default="pending", max_length=32)
    parse_error: Optional[str] = Field(default=None, sa_column=Column(Text))
    threats_extracted: Optional[str] = Field(default=None, sa_column=Column(Text))   # JSON
    objectives_extracted: Optional[str] = Field(default=None, sa_column=Column(Text))
    sfr_extracted: Optional[str] = Field(default=None, sa_column=Column(Text))
    assets_extracted: Optional[str] = Field(default=None, sa_column=Column(Text))
    is_shared: bool = Field(default=False)
    parsed_at: Optional[datetime] = Field(default=None)


class STReferenceFile(SQLModel, TimestampMixin, table=True):
    __tablename__ = "st_reference_files"

    id: str = Field(default_factory=new_uuid, primary_key=True)
    st_reference_id: str = Field(foreign_key="st_references.id", index=True)
    filename: str = Field(max_length=256)
    file_path: str = Field(max_length=512)
    file_size: int = Field(default=0)
    mime_type: str = Field(default="", max_length=128)
