"""Middleware and helpers for writing AuditLog / ErrorLog rows.

The audit log middleware records every state-changing request
(POST/PUT/PATCH/DELETE) made against `/api/...` with the authenticated user,
HTTP status, source IP and a derived `resource`/`resource_id` pair. Login
attempts (success AND failure) are also captured.

Unhandled exceptions anywhere in the request pipeline are persisted to
ErrorLog via `record_error()`, invoked from the global exception handler
in `app/main.py`.

Writes are best-effort: if the database is down we swallow the error so
logging never masks the original failure.
"""
from __future__ import annotations

import logging
import re
import time
import traceback
from typing import Optional
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from jose import jwt, JWTError
from sqlmodel import select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.log import AuditLog, ErrorLog
from app.models.user import User

log = logging.getLogger(__name__)


# Paths that we never record in the audit trail (health checks, docs, etc.).
_AUDIT_PATH_IGNORE_PREFIXES = (
    "/api/health",
    "/api/docs",
    "/api/redoc",
    "/api/openapi",
    "/api/system/logs",  # reading the log page is not itself interesting
)

_AUDIT_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

_RESOURCE_RE = re.compile(r"^/api/([^/]+)(?:/([^/?]+))?")


def _client_ip(request: Request) -> Optional[str]:
    # Respect X-Forwarded-For if behind a trusted proxy; otherwise use peer.
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None


def _extract_user_from_token(request: Request) -> tuple[Optional[str], Optional[str]]:
    """Decode the JWT present on the request, if any, without DB access.

    Returns (user_id, None) — username is resolved lazily by middleware
    only when writing the audit row, to avoid a DB round-trip for every
    anonymous request.
    """
    auth = request.headers.get("authorization") or ""
    if not auth.lower().startswith("bearer "):
        return None, None
    token = auth.split(" ", 1)[1].strip()
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        return payload.get("sub"), None
    except JWTError:
        return None, None


def _parse_resource(path: str) -> tuple[Optional[str], Optional[str]]:
    m = _RESOURCE_RE.match(path)
    if not m:
        return None, None
    resource, rid = m.group(1), m.group(2)
    # Skip UUID-ish segments when they're clearly the resource name
    return resource, rid


async def _resolve_username(user_id: str) -> Optional[str]:
    try:
        async with AsyncSessionLocal() as db:
            result = await db.exec(select(User).where(User.id == user_id))
            user = result.first()
            return user.username if user else None
    except Exception:
        return None


import asyncio as _asyncio
_audit_write_lock = _asyncio.Lock()


async def _write_audit(row: AuditLog) -> None:
    """Write an audit row. Retries on transient SQLite lock contention."""
    last_exc: Optional[Exception] = None
    async with _audit_write_lock:
        for attempt in range(10):
            try:
                async with AsyncSessionLocal() as db:
                    db.add(row)
                    await db.commit()
                return
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                if "database is locked" in str(exc).lower():
                    await _asyncio.sleep(0.1 * (attempt + 1))
                    continue
                break
    log.warning("audit log write failed: %s", last_exc)


async def record_error(
    request: Optional[Request],
    exc: BaseException,
    *,
    level: str = "ERROR",
) -> None:
    """Persist a single ErrorLog row; safe to call from exception handlers."""
    try:
        user_id, username = (None, None)
        method = path = ip = None
        if request is not None:
            user_id, _ = _extract_user_from_token(request)
            method = request.method
            path = str(request.url.path)
            ip = _client_ip(request)
            if user_id:
                username = await _resolve_username(user_id)

        row = ErrorLog(
            level=level,
            error_type=type(exc).__name__,
            message=str(exc)[:4000],
            stack_trace="".join(traceback.format_exception(type(exc), exc, exc.__traceback__))[:20000],
            user_id=user_id,
            username=username,
            method=method,
            path=path,
            ip=ip,
        )
        async with AsyncSessionLocal() as db:
            db.add(row)
            await db.commit()
    except Exception as write_exc:  # noqa: BLE001
        log.warning("error log write failed: %s", write_exc)


class AuditLogMiddleware(BaseHTTPMiddleware):
    """Log mutating API calls (plus every /api/auth/login attempt).

    Success and failure are both recorded; status_code tells the story.
    """

    async def dispatch(self, request: Request, call_next):
        path = request.url.path or ""
        method = request.method.upper()

        should_log = False
        if path.startswith("/api/"):
            # Skip ignored prefixes.
            if not any(path.startswith(p) for p in _AUDIT_PATH_IGNORE_PREFIXES):
                if method in _AUDIT_METHODS or path.startswith("/api/auth/login"):
                    should_log = True

        if not should_log:
            return await call_next(request)

        start = time.perf_counter()
        status_code = 500
        try:
            response: Response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            duration_ms = int((time.perf_counter() - start) * 1000)
            try:
                user_id, _ = _extract_user_from_token(request)
                username = await _resolve_username(user_id) if user_id else None
                resource, rid = _parse_resource(path)
                row = AuditLog(
                    user_id=user_id,
                    username=username,
                    method=method,
                    path=path[:512],
                    status_code=status_code,
                    resource=resource,
                    resource_id=rid,
                    ip=_client_ip(request),
                    user_agent=(request.headers.get("user-agent") or "")[:256] or None,
                    duration_ms=duration_ms,
                )
                await _write_audit(row)
            except Exception as exc:  # noqa: BLE001
                log.warning("audit middleware error: %s", exc)
