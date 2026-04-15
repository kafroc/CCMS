"""
System settings + log viewer routes (admin only).
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, func, col

from app.core.database import get_db
from app.core.auth import get_current_user
from app.core.response import ok
from app.models.user import User
from app.models.system_setting import SystemSetting, SYSTEM_SETTING_DEFAULTS
from app.models.log import AuditLog, ErrorLog

router = APIRouter(prefix="/api/system", tags=["System Settings"])


def _require_admin(current_user: User):
    if current_user.role != "admin":
        raise HTTPException(403, "Only administrators can manage system settings")


def _build_response(rows: list[SystemSetting]) -> dict:
    """Merge database rows with defaults and return a complete settings dictionary."""
    db_map = {r.key: r.value for r in rows}
    result = {}
    for key, meta in SYSTEM_SETTING_DEFAULTS.items():
        raw = db_map.get(key, meta["default"])
        result[key] = {
            "value": raw,
            "label": meta["label"],
            "type": meta["type"],
            "min": meta.get("min"),
            "max": meta.get("max"),
        }
    return result


@router.get("/settings")
async def get_system_settings(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Read all system settings with defaults applied."""
    _require_admin(current_user)
    result = await db.exec(select(SystemSetting))
    rows = list(result.all())
    return ok(data=_build_response(rows))


@router.patch("/settings")
async def update_system_settings(
    payload: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update system settings (admin only)."""
    _require_admin(current_user)

    for key, value in payload.items():
        if key not in SYSTEM_SETTING_DEFAULTS:
            raise HTTPException(400, f"Unknown setting: {key}")
        meta = SYSTEM_SETTING_DEFAULTS[key]
        # Validate the setting type.
        if meta["type"] == "int":
            try:
                v = int(value)
            except (TypeError, ValueError):
                raise HTTPException(400, f"{key} must be an integer")
            if "min" in meta and v < meta["min"]:
                raise HTTPException(400, f"{key} must be at least {meta['min']}")
            if "max" in meta and v > meta["max"]:
                raise HTTPException(400, f"{key} must be at most {meta['max']}")
            str_value = str(v)
        else:
            str_value = str(value)

        result = await db.exec(select(SystemSetting).where(SystemSetting.key == key))
        row = result.first()
        if row:
            row.value = str_value
            db.add(row)
        else:
            db.add(SystemSetting(key=key, value=str_value))

    await db.commit()

    result = await db.exec(select(SystemSetting))
    rows = list(result.all())
    return ok(data=_build_response(rows))


# ── Log viewer ────────────────────────────────────────────────────────


def _paginate_params(page: int, page_size: int) -> tuple[int, int]:
    page = max(1, page)
    page_size = min(200, max(1, page_size))
    return page, page_size


@router.get("/logs/audit")
async def list_audit_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    username: Optional[str] = Query(None, description="Exact username filter"),
    method: Optional[str] = Query(None, description="HTTP method filter (POST/PUT/...)"),
    resource: Optional[str] = Query(None),
    status_min: Optional[int] = Query(None, ge=100, le=599),
    status_max: Optional[int] = Query(None, ge=100, le=599),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Paginated audit log (admin only). Newest first."""
    _require_admin(current_user)
    page, page_size = _paginate_params(page, page_size)

    stmt = select(AuditLog)
    count_stmt = select(func.count()).select_from(AuditLog)
    if username:
        stmt = stmt.where(AuditLog.username == username)
        count_stmt = count_stmt.where(AuditLog.username == username)
    if method:
        m = method.upper()
        stmt = stmt.where(AuditLog.method == m)
        count_stmt = count_stmt.where(AuditLog.method == m)
    if resource:
        stmt = stmt.where(AuditLog.resource == resource)
        count_stmt = count_stmt.where(AuditLog.resource == resource)
    if status_min is not None:
        stmt = stmt.where(AuditLog.status_code >= status_min)
        count_stmt = count_stmt.where(AuditLog.status_code >= status_min)
    if status_max is not None:
        stmt = stmt.where(AuditLog.status_code <= status_max)
        count_stmt = count_stmt.where(AuditLog.status_code <= status_max)

    stmt = stmt.order_by(col(AuditLog.created_at).desc()).offset((page - 1) * page_size).limit(page_size)
    rows = list((await db.exec(stmt)).all())
    total = (await db.exec(count_stmt)).one()

    return ok(data={
        "items": [
            {
                "id": r.id,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "username": r.username,
                "user_id": r.user_id,
                "method": r.method,
                "path": r.path,
                "status_code": r.status_code,
                "resource": r.resource,
                "resource_id": r.resource_id,
                "ip": r.ip,
                "duration_ms": r.duration_ms,
            }
            for r in rows
        ],
        "total": int(total),
        "page": page,
        "page_size": page_size,
    })


@router.get("/logs/errors")
async def list_error_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    level: Optional[str] = Query(None),
    error_type: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Paginated error log (admin only). Newest first."""
    _require_admin(current_user)
    page, page_size = _paginate_params(page, page_size)

    stmt = select(ErrorLog)
    count_stmt = select(func.count()).select_from(ErrorLog)
    if level:
        stmt = stmt.where(ErrorLog.level == level.upper())
        count_stmt = count_stmt.where(ErrorLog.level == level.upper())
    if error_type:
        stmt = stmt.where(ErrorLog.error_type == error_type)
        count_stmt = count_stmt.where(ErrorLog.error_type == error_type)

    stmt = stmt.order_by(col(ErrorLog.created_at).desc()).offset((page - 1) * page_size).limit(page_size)
    rows = list((await db.exec(stmt)).all())
    total = (await db.exec(count_stmt)).one()

    return ok(data={
        "items": [
            {
                "id": r.id,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "level": r.level,
                "error_type": r.error_type,
                "message": r.message,
                "stack_trace": r.stack_trace,
                "username": r.username,
                "user_id": r.user_id,
                "method": r.method,
                "path": r.path,
                "ip": r.ip,
            }
            for r in rows
        ],
        "total": int(total),
        "page": page,
        "page_size": page_size,
    })


@router.delete("/logs/audit")
async def clear_audit_logs(
    before_days: int = Query(30, ge=1, le=3650),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete audit log rows older than N days (admin only)."""
    _require_admin(current_user)
    from datetime import timedelta
    from app.models.base import utcnow
    cutoff = utcnow() - timedelta(days=before_days)
    from sqlalchemy import delete as sa_delete
    result = await db.exec(sa_delete(AuditLog).where(AuditLog.created_at < cutoff))
    await db.commit()
    return ok(data={"deleted": result.rowcount or 0})


@router.delete("/logs/errors")
async def clear_error_logs(
    before_days: int = Query(30, ge=1, le=3650),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete error log rows older than N days (admin only)."""
    _require_admin(current_user)
    from datetime import timedelta
    from app.models.base import utcnow
    cutoff = utcnow() - timedelta(days=before_days)
    from sqlalchemy import delete as sa_delete
    result = await db.exec(sa_delete(ErrorLog).where(ErrorLog.created_at < cutoff))
    await db.commit()
    return ok(data={"deleted": result.rowcount or 0})
