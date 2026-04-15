from datetime import datetime, timezone
from typing import Optional
from sqlmodel import Field
import uuid


def utcnow() -> datetime:
    # asyncpg requires naive UTC datetimes for TIMESTAMP (no tz) columns
    return datetime.now(timezone.utc).replace(tzinfo=None)


def new_uuid() -> str:
    return str(uuid.uuid4())


class TimestampMixin:
    """Common timestamp fields."""
    created_at: datetime = Field(default_factory=utcnow, nullable=False)
    updated_at: Optional[datetime] = Field(default=None)
    deleted_at: Optional[datetime] = Field(default=None, index=True)

    def soft_delete(self):
        self.deleted_at = utcnow()

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None
