"""Audit log and error log models.

AuditLog tracks mutating requests (POST/PUT/PATCH/DELETE): who called which
endpoint, with which HTTP status, from which IP. ErrorLog captures unhandled
server exceptions so administrators can review failures from the Settings UI
without SSH-ing into the server.
"""
from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field
from sqlalchemy import Column, Text, Index
from app.models.base import new_uuid, utcnow


class AuditLog(SQLModel, table=True):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_created_at", "created_at"),
    )

    id: str = Field(default_factory=new_uuid, primary_key=True)
    created_at: datetime = Field(default_factory=utcnow, nullable=False)

    user_id: Optional[str] = Field(default=None, max_length=64, index=True)
    username: Optional[str] = Field(default=None, max_length=64)

    method: str = Field(max_length=8)
    path: str = Field(max_length=512)
    status_code: int = Field(default=0)

    # Short resource descriptor derived from the path, e.g. "toes", "users".
    resource: Optional[str] = Field(default=None, max_length=64, index=True)
    # Optional resource-id parsed from the path.
    resource_id: Optional[str] = Field(default=None, max_length=64)

    ip: Optional[str] = Field(default=None, max_length=64)
    user_agent: Optional[str] = Field(default=None, max_length=256)

    duration_ms: Optional[int] = Field(default=None)
    # Free-form JSON-serialized extras (never store raw bodies — PII).
    extra: Optional[str] = Field(default=None, sa_column=Column(Text))


class ErrorLog(SQLModel, table=True):
    __tablename__ = "error_logs"
    __table_args__ = (
        Index("ix_error_logs_created_at", "created_at"),
    )

    id: str = Field(default_factory=new_uuid, primary_key=True)
    created_at: datetime = Field(default_factory=utcnow, nullable=False)

    level: str = Field(default="ERROR", max_length=16)
    # Short classification, e.g. "HTTPException", "ValueError"
    error_type: str = Field(default="Exception", max_length=128)
    message: str = Field(sa_column=Column(Text, nullable=False))
    stack_trace: Optional[str] = Field(default=None, sa_column=Column(Text))

    user_id: Optional[str] = Field(default=None, max_length=64, index=True)
    username: Optional[str] = Field(default=None, max_length=64)

    method: Optional[str] = Field(default=None, max_length=8)
    path: Optional[str] = Field(default=None, max_length=512)
    ip: Optional[str] = Field(default=None, max_length=64)
