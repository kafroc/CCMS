from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field, Column, Text
from app.models.base import TimestampMixin, new_uuid
import sqlalchemy as sa


class TOE(SQLModel, TimestampMixin, table=True):
    __tablename__ = "toes"

    id: str = Field(default_factory=new_uuid, primary_key=True)
    user_id: str = Field(foreign_key="users.id", index=True)
    name: str = Field(max_length=256, index=True)
    toe_type: str = Field(max_length=32)     # hardware | software | system
    version: Optional[str] = Field(default=None, max_length=64)
    brief_intro: Optional[str] = Field(default=None, sa_column=Column(Text))
    # ── Active fields (displayed in UI) ──────────────────────────
    # What type of product the TOE is (e.g. Network Camera, CMS)
    toe_type_desc: Optional[str] = Field(default=None, sa_column=Column(Text))
    # How the TOE is typically used in a deployment scenario
    toe_usage: Optional[str] = Field(default=None, sa_column=Column(Text))
    # TOE's main security capabilities
    major_security_features: Optional[str] = Field(default=None, sa_column=Column(Text))
    # Required Non-TOE Hardware/Software/Firmware
    required_non_toe_hw_sw_fw: Optional[str] = Field(default=None, sa_column=Column(Text))
    # Physical scope: uniquely identifies the TOE (model, version, firmware)
    physical_scope: Optional[str] = Field(default=None, sa_column=Column(Text))
    # Logical scope: boundaries of TOE security functionality
    logical_scope: Optional[str] = Field(default=None, sa_column=Column(Text))
    # Hardware interfaces (physically accessible)
    hw_interfaces: Optional[str] = Field(default=None, sa_column=Column(Text))
    # Software interfaces (programmatically accessible)
    sw_interfaces: Optional[str] = Field(default=None, sa_column=Column(Text))
    # ── Legacy fields (kept for DB compat, hidden in UI) ─────────
    description: Optional[str] = Field(default=None, sa_column=Column(Text))
    usage_and_security_features: Optional[str] = Field(default=None, sa_column=Column(Text))
    boundary: Optional[str] = Field(default=None, sa_column=Column(Text))
    operational_env: Optional[str] = Field(default=None, sa_column=Column(Text))
    intended_users: Optional[str] = Field(default=None, sa_column=Column(Text))
    external_interfaces: Optional[str] = Field(default=None, sa_column=Column(Text))
    security_features_overview: Optional[str] = Field(default=None, sa_column=Column(Text))
    ai_generated_at: Optional[datetime] = Field(default=None)


class UserTOEPermission(SQLModel, TimestampMixin, table=True):
    __tablename__ = "user_toe_permissions"

    user_id: str = Field(foreign_key="users.id", primary_key=True)
    toe_id: str = Field(foreign_key="toes.id", primary_key=True)
    access_level: str = Field(default="read", max_length=16)  # read | write


class TOEAsset(SQLModel, TimestampMixin, table=True):
    __tablename__ = "toe_assets"

    id: str = Field(default_factory=new_uuid, primary_key=True)
    toe_id: str = Field(foreign_key="toes.id", index=True)
    name: str = Field(max_length=256)
    description: Optional[str] = Field(default=None, sa_column=Column(Text))
    asset_type: str = Field(max_length=32)  # data|function|privacy|config|other
    importance: int = Field(default=3)       # 1-5
    importance_reason: Optional[str] = Field(default=None, sa_column=Column(Text))
    ai_generated: bool = Field(default=False)
    weak_coverage_ignored: bool = Field(default=False)  # Mark weak coverage as ignored


class TOEFile(SQLModel, TimestampMixin, table=True):
    __tablename__ = "toe_files"

    id: str = Field(default_factory=new_uuid, primary_key=True)
    toe_id: str = Field(foreign_key="toes.id", index=True)
    filename: str = Field(max_length=256)
    original_filename: str = Field(max_length=256)
    file_path: str = Field(max_length=512)
    file_type: str = Field(max_length=32)    # document|image|video|other
    mime_type: str = Field(default="", max_length=128)
    file_size: int = Field(default=0)
    file_category: str = Field(default="manual", max_length=32)  # manual|st_pp|other
    process_status: str = Field(default="pending", max_length=32)  # pending|processing|ready|failed
    extracted_text_path: Optional[str] = Field(default=None, max_length=512)
    process_error: Optional[str] = Field(default=None, sa_column=Column(Text))
