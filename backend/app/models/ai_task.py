from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field, Column, Text
from app.models.base import TimestampMixin, new_uuid


class AITask(SQLModel, TimestampMixin, table=True):
    __tablename__ = "ai_tasks"

    id: str = Field(default_factory=new_uuid, primary_key=True)
    user_id: str = Field(foreign_key="users.id", index=True)
    toe_id: Optional[str] = Field(default=None, foreign_key="toes.id", index=True)
    task_type: str = Field(max_length=32)
    # threat_scan|objective_gen|sfr_match|test_gen|st_export|file_process|st_parse
    status: str = Field(default="pending", max_length=16)
    # pending|running|done|failed
    progress_message: Optional[str] = Field(default=None, max_length=512)
    result_summary: Optional[str] = Field(default=None, sa_column=Column(Text))
    error_message: Optional[str] = Field(default=None, sa_column=Column(Text))
    download_url: Optional[str] = Field(default=None, max_length=512)
    finished_at: Optional[datetime] = Field(default=None)
