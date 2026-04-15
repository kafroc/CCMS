from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field, Column, Text
from app.models.base import TimestampMixin, new_uuid


class SFRLibrary(SQLModel, table=True):
    """CC Part 2 standard SFR library (globally read-only)."""
    __tablename__ = "sfr_library"

    id: str = Field(default_factory=new_uuid, primary_key=True)
    sfr_class: str = Field(max_length=16, index=True)        # e.g. FDP
    sfr_class_name: str = Field(max_length=128)              # e.g. User Data Protection
    sfr_family: str = Field(max_length=32, index=True)       # e.g. FDP_ACC
    sfr_family_name: str = Field(max_length=128)
    sfr_component: str = Field(max_length=32, unique=True)   # e.g. FDP_ACC.1
    sfr_component_name: str = Field(max_length=256)
    description: Optional[str] = Field(default=None, sa_column=Column(Text))
    element_text: Optional[str] = Field(default=None, sa_column=Column(Text))
    dependencies: Optional[str] = Field(default=None, max_length=512)
    cc_version: str = Field(default="3.1R5", max_length=16)


class SecurityObjective(SQLModel, TimestampMixin, table=True):
    __tablename__ = "security_objectives"

    id: str = Field(default_factory=new_uuid, primary_key=True)
    toe_id: str = Field(foreign_key="toes.id", index=True)
    code: str = Field(max_length=64)          # e.g. O.AUTH_CONTROL or OE.LOCATE
    obj_type: str = Field(max_length=4)       # O | OE
    description: Optional[str] = Field(default=None, sa_column=Column(Text))
    rationale: Optional[str] = Field(default=None, sa_column=Column(Text))
    review_status: str = Field(default="draft", max_length=32)
    ai_generated: bool = Field(default=False)
    reviewed_at: Optional[datetime] = Field(default=None)


class ThreatObjective(SQLModel, table=True):
    """Many-to-many relation between Threat and SecurityObjective."""
    __tablename__ = "threat_objectives"

    threat_id: str = Field(foreign_key="threats.id", primary_key=True)
    objective_id: str = Field(foreign_key="security_objectives.id", primary_key=True)


class AssumptionObjective(SQLModel, table=True):
    """Many-to-many relation between Assumption and SecurityObjective."""
    __tablename__ = "assumption_objectives"

    assumption_id: str = Field(foreign_key="assumptions.id", primary_key=True)
    objective_id: str = Field(foreign_key="security_objectives.id", primary_key=True)


class OSPObjective(SQLModel, table=True):
    """Many-to-many relation between OSP and SecurityObjective."""
    __tablename__ = "osp_objectives"

    osp_id: str = Field(foreign_key="osps.id", primary_key=True)
    objective_id: str = Field(foreign_key="security_objectives.id", primary_key=True)


class SFR(SQLModel, TimestampMixin, table=True):
    __tablename__ = "sfrs"

    id: str = Field(default_factory=new_uuid, primary_key=True)
    toe_id: str = Field(foreign_key="toes.id", index=True)
    sfr_library_id: Optional[str] = Field(default=None, foreign_key="sfr_library.id")
    sfr_id: str = Field(max_length=64)        # FDP_ACC.1 or CUSTOM.xxx
    sfr_name: Optional[str] = Field(default=None, max_length=256)
    sfr_detail: Optional[str] = Field(default=None, sa_column=Column(Text))
    dependency: Optional[str] = Field(default=None, sa_column=Column(Text))
    source: str = Field(default="standard", max_length=16)   # standard | custom
    customization_note: Optional[str] = Field(default=None, sa_column=Column(Text))
    review_status: str = Field(default="draft", max_length=32)
    ai_rationale: Optional[str] = Field(default=None, sa_column=Column(Text))
    dependency_warning: Optional[str] = Field(default=None, sa_column=Column(Text))
    reviewed_at: Optional[datetime] = Field(default=None)


class ObjectiveSFR(SQLModel, table=True):
    """Many-to-many relation between SecurityObjective and SFR."""
    __tablename__ = "objective_sfrs"

    objective_id: str = Field(foreign_key="security_objectives.id", primary_key=True)
    sfr_id: str = Field(foreign_key="sfrs.id", primary_key=True)
    mapping_rationale: Optional[str] = Field(default=None, sa_column=Column(Text))
