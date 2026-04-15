from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.database import get_db
from app.core.auth import verify_password, create_access_token, get_current_user, hash_password
from app.core.response import ok
from app.models.user import User

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

# ── Brute-force protection ──────────────────────────────────────────
# Simple in-memory rate limiter. Production deployments behind a load
# balancer should prefer a Redis-backed solution.
import time
import threading

_login_attempts: dict[str, list[float]] = {}   # key → list of timestamps
_lock = threading.Lock()
_MAX_ATTEMPTS = 5
_WINDOW_SECONDS = 300  # 5 minutes

# Pre-computed dummy hash so we can call verify_password even when the
# user doesn't exist (constant-time defence against timing enumeration).
_DUMMY_HASH = hash_password("__dummy_placeholder_pw__")


def _check_rate_limit(key: str) -> None:
    """Raise 429 if the key has exceeded the allowed login attempts."""
    now = time.monotonic()
    with _lock:
        attempts = _login_attempts.get(key, [])
        # Prune old entries
        attempts = [t for t in attempts if now - t < _WINDOW_SECONDS]
        _login_attempts[key] = attempts
        if len(attempts) >= _MAX_ATTEMPTS:
            raise HTTPException(
                status_code=429,
                detail=f"Too many login attempts. Please try again after {_WINDOW_SECONDS // 60} minutes.",
            )


def _record_failed_attempt(key: str) -> None:
    now = time.monotonic()
    with _lock:
        _login_attempts.setdefault(key, []).append(now)


def _clear_attempts(key: str) -> None:
    with _lock:
        _login_attempts.pop(key, None)


@router.post("/login")
async def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    """Log in a user and return a JWT token.

    When the account is flagged `must_change_password` the client is
    expected to redirect the user straight to the change-password flow
    before allowing any other action.
    """
    # Rate-limit by username + IP to limit brute-force attacks.
    client_ip = request.client.host if request.client else "unknown"
    rate_key = f"{form_data.username}::{client_ip}"
    _check_rate_limit(rate_key)

    result = await db.exec(
        select(User).where(
            User.username == form_data.username,
            User.deleted_at.is_(None),
        )
    )
    user = result.first()

    # Constant-time: always run bcrypt even for non-existent users to
    # prevent timing-based username enumeration.
    if not user:
        verify_password(form_data.password, _DUMMY_HASH)
        _record_failed_attempt(rate_key)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not verify_password(form_data.password, user.password_hash):
        _record_failed_attempt(rate_key)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    _clear_attempts(rate_key)
    token = create_access_token(user.id)
    return ok(
        data={
            "access_token": token,
            "token_type": "bearer",
            "user": {
                "id": user.id,
                "username": user.username,
                "role": user.role,
                "must_change_password": bool(user.must_change_password),
            },
        },
        msg="Login successful",
    )


@router.get("/me")
async def get_me(current_user: User = Depends(get_current_user)):
    """Get the current authenticated user's information."""
    return ok(data={
        "id": current_user.id,
        "username": current_user.username,
        "role": current_user.role,
        "must_change_password": bool(current_user.must_change_password),
    })
