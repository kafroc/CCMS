from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel
import httpx

from app.core.database import get_db
from app.core.auth import get_current_user
from app.core.response import ok, NotFoundError
from app.core.security import encrypt_api_key, decrypt_api_key, mask_api_key
from app.core.uploads import validate_ai_api_base
from app.models.user import User
from app.models.ai_model import AIModel, AIModelCreate, AIModelUpdate, AIModelRead
from app.models.base import utcnow

router = APIRouter(prefix="/api/ai-models", tags=["AI Model Management"])


def _to_read(m: AIModel) -> AIModelRead:
    plain = decrypt_api_key(m.api_key_encrypted)
    return AIModelRead(
        id=m.id,
        name=m.name,
        api_base=m.api_base,
        api_key_masked=mask_api_key(plain),
        model_name=m.model_name,
        is_verified=m.is_verified,
        verified_at=m.verified_at,
        timeout_seconds=m.timeout_seconds,
        is_active=m.is_active,
        created_at=m.created_at,
    )


def _check_owner(model: AIModel, user: User):
    if model.user_id != user.id and user.role != "admin":
        raise HTTPException(status_code=403, detail="You do not have permission to manage this model configuration")


@router.get("")
async def list_models(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.exec(
        select(AIModel).where(
            AIModel.user_id == current_user.id,
            AIModel.deleted_at.is_(None),
        ).order_by(AIModel.created_at)
    )
    models = result.all()
    return ok(data=[_to_read(m) for m in models])


@router.post("")
async def create_model(
    payload: AIModelCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    model = AIModel(
        user_id=current_user.id,
        name=payload.name,
        api_base=validate_ai_api_base(payload.api_base),
        api_key_encrypted=encrypt_api_key(payload.api_key),
        model_name=payload.model_name,
        timeout_seconds=payload.timeout_seconds,
    )
    db.add(model)
    await db.flush()
    return ok(data=_to_read(model), msg="Created successfully")


@router.put("/{model_id}")
async def update_model(
    model_id: str,
    payload: AIModelUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.exec(
        select(AIModel).where(AIModel.id == model_id, AIModel.deleted_at.is_(None))
    )
    model = result.first()
    if not model:
        raise NotFoundError("Model configuration not found")
    _check_owner(model, current_user)

    if payload.name is not None:
        model.name = payload.name
    if payload.api_base is not None:
        model.api_base = validate_ai_api_base(payload.api_base)
        model.is_verified = False
    if payload.api_key is not None:
        model.api_key_encrypted = encrypt_api_key(payload.api_key)
        model.is_verified = False
    if payload.model_name is not None:
        model.model_name = payload.model_name
        model.is_verified = False
    if payload.timeout_seconds is not None:
        model.timeout_seconds = payload.timeout_seconds

    model.updated_at = utcnow()
    db.add(model)
    return ok(data=_to_read(model), msg="Updated successfully")


@router.delete("/{model_id}")
async def delete_model(
    model_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.exec(
        select(AIModel).where(AIModel.id == model_id, AIModel.deleted_at.is_(None))
    )
    model = result.first()
    if not model:
        raise NotFoundError("Model configuration not found")
    _check_owner(model, current_user)

    model.soft_delete()
    db.add(model)
    return ok(msg="Deleted successfully")


@router.post("/{model_id}/verify")
async def verify_model(
    model_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Verify whether the model configuration is valid by calling the /models endpoint."""
    result = await db.exec(
        select(AIModel).where(AIModel.id == model_id, AIModel.deleted_at.is_(None))
    )
    model = result.first()
    if not model:
        raise NotFoundError("Model configuration not found")
    _check_owner(model, current_user)

    api_key = decrypt_api_key(model.api_key_encrypted)
    url = f"{model.api_base}/models"

    # Re-validate stored URL against SSRF rules (defense in depth)
    try:
        validate_ai_api_base(model.api_base)
    except HTTPException:
        return ok(data=_to_read(model), msg="Verification failed: api_base points to a blocked address")

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                url,
                headers={"Authorization": f"Bearer {api_key}"},
            )
        if resp.status_code == 200:
            model.is_verified = True
            model.verified_at = utcnow()
            model.updated_at = utcnow()
            db.add(model)
            return ok(data=_to_read(model), msg="Verification successful")
        else:
            model.is_verified = False
            model.updated_at = utcnow()
            db.add(model)
            return ok(data=_to_read(model), msg=f"Verification failed: service returned {resp.status_code}")
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("AI model verify failed: %s", e)
        model.is_verified = False
        model.updated_at = utcnow()
        db.add(model)
        return ok(data=_to_read(model), msg="Verification failed: unable to connect to the AI service")


@router.post("/{model_id}/set-active")
async def set_active_model(
    model_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Set the specified model as the current user's working model and clear other active models."""
    result = await db.exec(
        select(AIModel).where(AIModel.id == model_id, AIModel.deleted_at.is_(None))
    )
    model = result.first()
    if not model:
        raise NotFoundError("Model configuration not found")
    _check_owner(model, current_user)

    # First cancel active status for all other models of this user
    all_res = await db.exec(
        select(AIModel).where(
            AIModel.user_id == current_user.id,
            AIModel.deleted_at.is_(None),
        )
    )
    for m in all_res.all():
        if m.is_active:
            m.is_active = False
            db.add(m)

    model.is_active = True
    model.updated_at = utcnow()
    db.add(model)
    await db.commit()
    await db.refresh(model)
    return ok(data=_to_read(model), msg=f"Set '{model.name}' as the active model")


class ChatMessage(BaseModel):
    role: str   # user | assistant
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]


@router.post("/{model_id}/chat")
async def chat_with_model(
    model_id: str,
    body: ChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Chat with the specified model."""
    result = await db.exec(
        select(AIModel).where(AIModel.id == model_id, AIModel.deleted_at.is_(None))
    )
    model = result.first()
    if not model:
        raise NotFoundError("Model configuration not found")
    _check_owner(model, current_user)

    from openai import AsyncOpenAI
    api_key = decrypt_api_key(model.api_key_encrypted)
    client = AsyncOpenAI(
        api_key=api_key,
        base_url=model.api_base,
        timeout=float(model.timeout_seconds),
        max_retries=0,
    )

    messages = [{"role": m.role, "content": m.content} for m in body.messages]
    try:
        resp = await client.chat.completions.create(
            model=model.model_name,
            messages=messages,
            max_tokens=2048,
        )
        content = resp.choices[0].message.content
        return ok(data={"content": content, "role": "assistant"})
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("AI chat failed: %s", e)
        raise HTTPException(400, "AI invocation failed: unable to get a response from the model")
