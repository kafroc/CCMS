from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.response import ForbiddenError, NotFoundError
from app.models.toe import TOE, UserTOEPermission
from app.models.user import User


async def get_toe_access_level(toe: TOE, user: User, db: AsyncSession) -> Optional[str]:
    if user.role == "admin":
        return "write"
    if toe.user_id == user.id:
        return "write"

    permission = (await db.exec(
        select(UserTOEPermission).where(
            UserTOEPermission.user_id == user.id,
            UserTOEPermission.toe_id == toe.id,
            UserTOEPermission.deleted_at.is_(None),
        )
    )).first()
    if not permission:
        return None
    return permission.access_level


async def get_accessible_toe(toe_id: str, user: User, db: AsyncSession, writable: bool = False) -> TOE:
    toe = (await db.exec(
        select(TOE).where(
            TOE.id == toe_id,
            TOE.deleted_at.is_(None),
        )
    )).first()
    if not toe:
        raise NotFoundError("TOE not found")

    access_level = await get_toe_access_level(toe, user, db)
    if access_level is None:
        raise ForbiddenError("You do not have access to this TOE")
    if writable and access_level != "write":
        raise ForbiddenError("This TOE is read-only for the current user")
    return toe
