from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field, Column, Text
from app.models.base import TimestampMixin, new_uuid


class TestCase(SQLModel, TimestampMixin, table=True):
    __tablename__ = "test_cases"

    id: str = Field(default_factory=new_uuid, primary_key=True)
    case_number: Optional[str] = Field(default=None, max_length=64)  # human-readable ID e.g. TC-001
    toe_id: str = Field(foreign_key="toes.id", index=True)
    primary_sfr_id: str = Field(foreign_key="sfrs.id", index=True)
    related_sfr_ids: Optional[str] = Field(default=None, sa_column=Column(Text))  # JSON array
    test_type: str = Field(max_length=128)  # JSON array: ["coverage","depth","independent"]
    title: str = Field(max_length=256)
    objective: Optional[str] = Field(default=None, sa_column=Column(Text))
    test_target: Optional[str] = Field(default=None, sa_column=Column(Text))
    test_scenario: Optional[str] = Field(default=None, sa_column=Column(Text))
    precondition: Optional[str] = Field(default=None, sa_column=Column(Text))
    test_steps: Optional[str] = Field(default=None, sa_column=Column(Text))
    expected_result: Optional[str] = Field(default=None, sa_column=Column(Text))
    review_status: str = Field(default="draft", max_length=32)
    ai_generated: bool = Field(default=False)
    reviewed_at: Optional[datetime] = Field(default=None)
