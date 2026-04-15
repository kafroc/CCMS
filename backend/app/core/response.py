from typing import Any, Optional
from fastapi import HTTPException


def ok(data: Any = None, msg: str = "success") -> dict:
    return {"code": 0, "msg": msg, "data": data}


def fail(msg: str, code: int = 1) -> dict:
    return {"code": code, "msg": msg, "data": None}


class AppException(HTTPException):
    def __init__(self, msg: str, status_code: int = 400):
        super().__init__(status_code=status_code, detail=msg)


class NotFoundError(AppException):
    def __init__(self, msg: str = "Resource not found"):
        super().__init__(msg, status_code=404)


class ForbiddenError(AppException):
    def __init__(self, msg: str = "Access denied"):
        super().__init__(msg, status_code=403)


# ── Batch operation guard ────────────────────────────────────────────
MAX_BATCH_SIZE = 200


def validate_batch_ids(ids: list, label: str = "ids") -> list:
    """Raise 400 if the batch list exceeds the allowed maximum."""
    if not isinstance(ids, list):
        raise HTTPException(status_code=400, detail=f"{label} must be a list")
    if len(ids) > MAX_BATCH_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"Batch size exceeds the limit ({MAX_BATCH_SIZE})",
        )
    return ids
