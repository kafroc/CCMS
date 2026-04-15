from typing import Optional, Annotated
from sqlmodel import SQLModel, Field
from pydantic import StringConstraints
from app.models.base import TimestampMixin, new_uuid, utcnow
from datetime import datetime


class User(SQLModel, TimestampMixin, table=True):
    __tablename__ = "users"

    id: str = Field(default_factory=new_uuid, primary_key=True)
    username: str = Field(max_length=64, unique=True, index=True)
    password_hash: str = Field(max_length=256)
    role: str = Field(default="user", max_length=16)  # admin | user
    # True when the user was seeded with a temporary password and must
    # change it before the account is fully usable. Cleared by the
    # password-change endpoint.
    must_change_password: bool = Field(default=False, nullable=False)

    # For response only (not stored in DB)
    class Config:
        populate_by_name = True


class UserCreate(SQLModel):
    username: Annotated[str, StringConstraints(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9]+$")]
    password: str = Field(min_length=6, max_length=128)
    role: str = Field(default="user")
    toe_permissions: list["UserTOEPermissionPayload"] = []


class UserUpdate(SQLModel):
    old_password: str
    new_password: str = Field(min_length=6, max_length=128)


class UserRead(SQLModel):
    id: str
    username: str
    role: str
    created_at: datetime
    toe_permissions: list["UserTOEPermissionRead"] = []


class UserTOEPermissionPayload(SQLModel):
    toe_id: str
    access_level: str = Field(default="read")


class UserTOEPermissionRead(SQLModel):
    toe_id: str
    toe_name: str
    access_level: str
