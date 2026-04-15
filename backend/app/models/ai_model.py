from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field
from app.models.base import TimestampMixin, new_uuid


class AIModel(SQLModel, TimestampMixin, table=True):
    __tablename__ = "ai_models"

    id: str = Field(default_factory=new_uuid, primary_key=True)
    user_id: str = Field(foreign_key="users.id", index=True)
    name: str = Field(max_length=128)
    api_base: str = Field(max_length=512)
    api_key_encrypted: str = Field(max_length=1024)  # Encrypted storage
    model_name: str = Field(max_length=128)
    is_verified: bool = Field(default=False)
    verified_at: Optional[datetime] = Field(default=None)
    timeout_seconds: int = Field(default=60)       # AI call timeout (seconds)
    is_active: bool = Field(default=False, index=True)  # Current working model


class AIModelCreate(SQLModel):
    name: str = Field(min_length=1, max_length=128)
    api_base: str = Field(min_length=1, max_length=512)
    api_key: str = Field(min_length=1, max_length=512)
    model_name: str = Field(min_length=1, max_length=128)
    timeout_seconds: int = Field(default=60)


class AIModelUpdate(SQLModel):
    name: Optional[str] = Field(default=None, max_length=128)
    api_base: Optional[str] = Field(default=None, max_length=512)
    api_key: Optional[str] = Field(default=None, max_length=512)
    model_name: Optional[str] = Field(default=None, max_length=128)
    timeout_seconds: Optional[int] = Field(default=None)


class AIModelRead(SQLModel):
    id: str
    name: str
    api_base: str
    api_key_masked: str  # Masked API key
    model_name: str
    is_verified: bool
    verified_at: Optional[datetime]
    timeout_seconds: int
    is_active: bool
    created_at: datetime
