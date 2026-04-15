from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.database import get_db
from app.core.auth import get_current_user, get_current_admin, hash_password, verify_password
from app.core.response import ok, NotFoundError
from app.models.user import User, UserCreate, UserUpdate, UserRead, UserTOEPermissionRead, UserTOEPermissionPayload
from app.models.base import utcnow
from app.models.toe import TOE, UserTOEPermission

router = APIRouter(prefix="/api/users", tags=["User Management"])

# ── Password policy ──────────────────────────────────────────────────
import re

_MIN_PASSWORD_LENGTH = 10


def _validate_password_strength(password: str) -> None:
    """Enforce minimum password complexity requirements."""
    if len(password) < _MIN_PASSWORD_LENGTH:
        raise HTTPException(400, f"Password must be at least {_MIN_PASSWORD_LENGTH} characters")
    if not re.search(r"[A-Z]", password):
        raise HTTPException(400, "Password must contain at least one uppercase letter")
    if not re.search(r"[a-z]", password):
        raise HTTPException(400, "Password must contain at least one lowercase letter")
    if not re.search(r"\d", password):
        raise HTTPException(400, "Password must contain at least one digit")
    if not re.search(r"[!@#$%^&*\-_+=?]", password):
        raise HTTPException(400, "Password must contain at least one special character (!@#$%^&*-_+=?)")


async def _build_user_read(user: User, db: AsyncSession) -> UserRead:
    permissions = (await db.exec(
        select(UserTOEPermission, TOE).where(
            UserTOEPermission.user_id == user.id,
            UserTOEPermission.toe_id == TOE.id,
            UserTOEPermission.deleted_at.is_(None),
            TOE.deleted_at.is_(None),
        )
    )).all()
    toe_permissions = [
        UserTOEPermissionRead(
            toe_id=toe.id,
            toe_name=toe.name,
            access_level=permission.access_level,
        )
        for permission, toe in permissions
    ]
    toe_permissions.sort(key=lambda item: item.toe_name.lower())
    return UserRead(
        id=user.id,
        username=user.username,
        role=user.role,
        created_at=user.created_at,
        toe_permissions=toe_permissions,
    )


async def _replace_user_toe_permissions(user_id: str, permissions: list[UserTOEPermissionPayload], db: AsyncSession) -> None:
    rows = (await db.exec(
        select(UserTOEPermission).where(UserTOEPermission.user_id == user_id)
    )).all()
    for row in rows:
        await db.delete(row)

    normalized: dict[str, str] = {}
    for permission in permissions:
        toe_id = (permission.toe_id or "").strip()
        access_level = (permission.access_level or "read").strip().lower()
        if not toe_id:
            continue
        if access_level not in {"read", "write"}:
            raise HTTPException(status_code=400, detail="TOE access must be either read or write")
        normalized[toe_id] = access_level

    if not normalized:
        return

    toes = (await db.exec(
        select(TOE).where(TOE.id.in_(list(normalized.keys())), TOE.deleted_at.is_(None))
    )).all()
    valid_toe_ids = {toe.id for toe in toes}
    missing_ids = [toe_id for toe_id in normalized if toe_id not in valid_toe_ids]
    if missing_ids:
        raise HTTPException(status_code=400, detail=f"TOE not found: {missing_ids[0]}")

    for toe_id, access_level in normalized.items():
        db.add(UserTOEPermission(user_id=user_id, toe_id=toe_id, access_level=access_level))


@router.get("")
async def list_users(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    """Get the full user list (admin only)."""
    result = await db.exec(select(User).where(User.deleted_at.is_(None)))
    users = result.all()
    data = []
    for user in users:
        data.append(await _build_user_read(user, db))
    return ok(data=data)


@router.post("")
async def create_user(
    payload: UserCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    """Create a user (admin only)."""
    _validate_password_strength(payload.password)
    normalized_username = payload.username.strip()
    existing_user = (await db.exec(
        select(User).where(User.username == normalized_username)
    )).first()

    if existing_user and existing_user.deleted_at is None:
        raise HTTPException(status_code=400, detail="Username already exists")

    if existing_user:
        user = existing_user
        user.deleted_at = None
        user.updated_at = utcnow()
        user.password_hash = hash_password(payload.password)
        user.role = payload.role
    else:
        user = User(
            username=normalized_username,
            password_hash=hash_password(payload.password),
            role=payload.role,
        )

    db.add(user)
    await db.flush()
    if payload.role != "admin":
        await _replace_user_toe_permissions(user.id, payload.toe_permissions, db)
    else:
        await _replace_user_toe_permissions(user.id, [], db)
    await db.flush()
    return ok(data=await _build_user_read(user, db), msg="Created successfully")


@router.put("/{user_id}/toe-permissions")
async def update_user_toe_permissions(
    user_id: str,
    payload: list[UserTOEPermissionPayload],
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_admin),
):
    user = (await db.exec(
        select(User).where(User.id == user_id, User.deleted_at.is_(None))
    )).first()
    if not user:
        raise NotFoundError("User not found")
    if user.role == "admin":
        raise HTTPException(status_code=400, detail="Administrators already have full TOE access and do not need explicit assignments")

    await _replace_user_toe_permissions(user.id, payload, db)
    await db.flush()
    return ok(data=await _build_user_read(user, db), msg="Permissions updated successfully")


@router.put("/{user_id}/password")
async def change_password(
    user_id: str,
    payload: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Change a password (the user themselves or an admin)."""
    # Can only change own password, or admin can change any user
    if current_user.role != "admin" and current_user.id != user_id:
        raise HTTPException(status_code=403, detail="You do not have permission to change another user's password")

    result = await db.exec(
        select(User).where(User.id == user_id, User.deleted_at.is_(None))
    )
    user = result.first()
    if not user:
        raise NotFoundError("User not found")

    if not verify_password(payload.old_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    if payload.old_password == payload.new_password:
        raise HTTPException(status_code=400, detail="New password must differ from the old one")
    _validate_password_strength(payload.new_password)

    user.password_hash = hash_password(payload.new_password)
    user.must_change_password = False
    user.updated_at = utcnow()
    db.add(user)
    return ok(msg="Password changed successfully")


@router.delete("/{user_id}")
async def delete_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """Delete a user (admin only, and not the current user)."""
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot delete the currently logged-in user")

    result = await db.exec(
        select(User).where(User.id == user_id, User.deleted_at.is_(None))
    )
    user = result.first()
    if not user:
        raise NotFoundError("User not found")

    user.soft_delete()
    db.add(user)
    permission_rows = (await db.exec(
        select(UserTOEPermission).where(
            UserTOEPermission.user_id == user.id,
            UserTOEPermission.deleted_at.is_(None),
        )
    )).all()
    for row in permission_rows:
        row.soft_delete()
        db.add(row)
    return ok(msg="Deleted successfully")
