"""
Threat management routes - Phase 3.
Includes Assumption/OSP/Threat CRUD, review actions, AI suggestions and scans, and ST reference library management.
"""
import asyncio
import json
import os
import re
import uuid
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, func, col

from app.core.database import get_db
from app.core.auth import get_current_user, get_current_admin
from app.core.toe_permissions import get_accessible_toe
from app.core.config import settings
from app.core.response import ok, NotFoundError, validate_batch_ids
from app.core.uploads import (
    sanitize_filename,
    get_safe_extension,
    validate_size,
    ALLOWED_EXT_ST_REFERENCE,
)
from app.models.base import utcnow, new_uuid
from app.models.user import User
from app.models.toe import TOE, TOEAsset
from app.models.threat import Assumption, OSP, Threat, ThreatAssetLink, STReference, STReferenceFile
from app.models.security import (
    SecurityObjective,
    ThreatObjective,
    AssumptionObjective,
    OSPObjective,
    SFR,
    ObjectiveSFR,
)
from app.models.risk import RiskAssessment
from app.models.test_case import TestCase
from app.models.ai_task import AITask
from app.services.ai_service import get_ai_service

router = APIRouter(prefix="/api/toes/{toe_id}", tags=["Threat Management"])
st_router = APIRouter(prefix="/api/st-references", tags=["Global ST Reference Library"])

# ── Risk level calculation matrix ─────────────────────────────────────────
RISK_MATRIX = {
    ("low",    "low"):    "low",
    ("low",    "medium"): "low",
    ("low",    "high"):   "medium",
    ("medium", "low"):    "medium",
    ("medium", "medium"): "medium",
    ("medium", "high"):   "high",
    ("high",   "low"):    "medium",
    ("high",   "medium"): "high",
    ("high",   "high"):   "critical",
}


def calc_risk_level(likelihood: str, impact: str) -> str:
    return RISK_MATRIX.get((likelihood, impact), "medium")


# ── Helper: Confirm TOE ownership ──────────────────────────────────────

async def _get_user_toe(toe_id: str, user: User, db: AsyncSession, writable: bool = True) -> TOE:
    return await get_accessible_toe(toe_id, user, db, writable=writable)


# ── code uniqueness check ──────────────────────────────────────────

async def _unique_code(Model, toe_id: str, code: str, db: AsyncSession, exclude_id: str = None) -> str:
    """Ensure code is unique within the same TOE by appending a numeric suffix on conflicts."""
    base = code
    suffix = 2
    while True:
        stmt = select(Model).where(
            Model.toe_id == toe_id,
            Model.code == code,
            Model.deleted_at.is_(None),
        )
        if exclude_id:
            stmt = stmt.where(Model.id != exclude_id)
        existing = (await db.exec(stmt)).first()
        if not existing:
            return code
        code = f"{base}_{suffix}"
        suffix += 1


# ═══════════════════════════════════════════════════════════════
# B3-1  Assumption CRUD + AI suggestions + review
# ═══════════════════════════════════════════════════════════════

@router.get("/assumptions")
async def list_assumptions(
    toe_id: str,
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_user_toe(toe_id, current_user, db, writable=False)
    stmt = select(Assumption).where(
        Assumption.toe_id == toe_id,
        Assumption.deleted_at.is_(None),
    ).order_by(Assumption.created_at)
    if status:
        stmt = stmt.where(Assumption.review_status == status)
    result = await db.exec(stmt)
    return ok(data=[_assumption_dict(a) for a in result.all()])


@router.post("/assumptions")
async def create_assumption(
    toe_id: str,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_user_toe(toe_id, current_user, db, writable=True)
    code = (payload.get("code") or "").strip().upper()
    if not code:
        raise HTTPException(400, "code is required")
    if not code.startswith("A."):
        code = "A." + code
    code = await _unique_code(Assumption, toe_id, code, db)

    obj = Assumption(
        toe_id=toe_id,
        code=code,
        description=payload.get("description"),
        review_status=payload.get("review_status", "draft"),
        ai_generated=payload.get("ai_generated", False),
    )
    db.add(obj)
    await db.flush()
    return ok(data=_assumption_dict(obj), msg="Created successfully")


@router.put("/assumptions/{item_id}")
async def update_assumption(
    toe_id: str, item_id: str, payload: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_user_toe(toe_id, current_user, db, writable=True)
    obj = await _get_item(Assumption, item_id, toe_id, db)
    for f in ["code", "description"]:
        if f in payload:
            setattr(obj, f, payload[f])
    obj.updated_at = utcnow()
    db.add(obj)
    return ok(data=_assumption_dict(obj))


@router.delete("/assumptions/{item_id}")
async def delete_assumption(
    toe_id: str, item_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_user_toe(toe_id, current_user, db, writable=True)
    obj = await _get_item(Assumption, item_id, toe_id, db)
    obj.soft_delete()
    db.add(obj)
    return ok(msg="Deleted successfully")


@router.post("/assumptions/{item_id}/confirm")
async def confirm_assumption(
    toe_id: str, item_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_user_toe(toe_id, current_user, db, writable=True)
    obj = await _get_item(Assumption, item_id, toe_id, db)
    obj.review_status = "confirmed"
    obj.reviewed_at = utcnow()
    db.add(obj)
    return ok(data=_assumption_dict(obj))


@router.post("/assumptions/{item_id}/reject")
async def reject_assumption(
    toe_id: str, item_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_user_toe(toe_id, current_user, db, writable=True)
    obj = await _get_item(Assumption, item_id, toe_id, db)
    obj.review_status = "rejected"
    obj.reviewed_at = utcnow()
    db.add(obj)
    return ok(data=_assumption_dict(obj))


@router.post("/assumptions/{item_id}/revert")
async def revert_assumption(
    toe_id: str, item_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_user_toe(toe_id, current_user, db, writable=True)
    obj = await _get_item(Assumption, item_id, toe_id, db)
    obj.review_status = "draft"
    obj.reviewed_at = None
    db.add(obj)
    return ok(data=_assumption_dict(obj))


@router.post("/assumptions/batch-confirm")
async def batch_confirm_assumptions(
    toe_id: str,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Batch confirm assumptions."""
    await _get_user_toe(toe_id, current_user, db, writable=True)
    ids = validate_batch_ids(payload.get("ids", []))
    
    result = await db.exec(
        select(Assumption).where(
            Assumption.toe_id == toe_id,
            Assumption.id.in_(ids),
            Assumption.deleted_at.is_(None),
        )
    )
    items = result.all()
    
    for item in items:
        item.review_status = "confirmed"
        item.reviewed_at = utcnow()
        db.add(item)
    
    await db.commit()
    return ok(data={"updated": len(items)})


@router.post("/assumptions/batch-reject")
async def batch_reject_assumptions(
    toe_id: str,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Batch reject assumptions."""
    await _get_user_toe(toe_id, current_user, db)
    ids = validate_batch_ids(payload.get("ids", []))
    
    result = await db.exec(
        select(Assumption).where(
            Assumption.toe_id == toe_id,
            Assumption.id.in_(ids),
            Assumption.deleted_at.is_(None),
        )
    )
    items = result.all()
    
    for item in items:
        item.review_status = "rejected"
        item.reviewed_at = utcnow()
        db.add(item)
    
    await db.commit()
    return ok(data={"updated": len(items)})


@router.post("/assumptions/ai-suggest")
async def ai_suggest_assumptions(
    toe_id: str,
    language: str = Query("en"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Suggest assumptions with AI (synchronous call)."""
    toe = await _get_user_toe(toe_id, current_user, db, writable=False)
    ai = await get_ai_service(db, current_user.id)
    if not ai:
        raise HTTPException(400, "Please configure and verify an AI model first")

    existing = (await db.exec(
        select(Assumption).where(Assumption.toe_id == toe_id, Assumption.deleted_at.is_(None))
    )).all()
    existing_codes = [a.code for a in existing]

    language = (language or "en").lower()

    output_language = "Chinese" if language == "zh" else "English"
    prompt = f"""Generate a list of environmental assumptions for the TOE below.

TOE Name: {toe.name}
TOE Type: {toe.toe_type}
Summary: {toe.brief_intro or 'None'}
Operational Environment: {toe.operational_env or 'None'}
Boundary: {toe.boundary or 'None'}

Existing assumptions (do not duplicate): {', '.join(existing_codes) if existing_codes else 'None'}

Assumptions should describe preconditions that must hold in the operational environment. Format: A.VERB_OR_NOUN_PHRASE (uppercase).

Return JSON in this format:
{{
    "assumptions": [
        {{
            "code": "A.PHYSICAL_PROTECTION",
            "description": "Assumption description"
        }}
    ]
}}

Requirements:
- Generate 3-6 assumptions
- Do not duplicate existing assumptions
- Descriptions must be in {output_language}, code must be in English"""

    result = await ai.chat_json(prompt)
    return ok(data=result.get("assumptions", []))


# ═══════════════════════════════════════════════════════════════
# B3-2  OSP CRUD + AI suggestions + review (structure same as Assumption)
# ═══════════════════════════════════════════════════════════════

@router.get("/osps")
async def list_osps(
    toe_id: str,
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_user_toe(toe_id, current_user, db, writable=False)
    stmt = select(OSP).where(OSP.toe_id == toe_id, OSP.deleted_at.is_(None)).order_by(OSP.created_at)
    if status:
        stmt = stmt.where(OSP.review_status == status)
    result = await db.exec(stmt)
    return ok(data=[_osp_dict(o) for o in result.all()])


@router.post("/osps")
async def create_osp(
    toe_id: str, payload: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_user_toe(toe_id, current_user, db)
    code = (payload.get("code") or "").strip().upper()
    if not code:
        raise HTTPException(400, "code is required")
    if not code.startswith("P."):
        code = "P." + code
    code = await _unique_code(OSP, toe_id, code, db)

    obj = OSP(
        toe_id=toe_id, code=code,
        description=payload.get("description"),
        review_status=payload.get("review_status", "draft"),
        ai_generated=payload.get("ai_generated", False),
    )
    db.add(obj)
    await db.flush()
    return ok(data=_osp_dict(obj), msg="Created successfully")


@router.put("/osps/{item_id}")
async def update_osp(
    toe_id: str, item_id: str, payload: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_user_toe(toe_id, current_user, db)
    obj = await _get_item(OSP, item_id, toe_id, db)
    for f in ["code", "description"]:
        if f in payload:
            setattr(obj, f, payload[f])
    obj.updated_at = utcnow()
    db.add(obj)
    return ok(data=_osp_dict(obj))


@router.delete("/osps/{item_id}")
async def delete_osp(
    toe_id: str, item_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_user_toe(toe_id, current_user, db)
    obj = await _get_item(OSP, item_id, toe_id, db)
    obj.soft_delete()
    db.add(obj)
    return ok(msg="Deleted successfully")


@router.post("/osps/{item_id}/confirm")
async def confirm_osp(toe_id: str, item_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    await _get_user_toe(toe_id, current_user, db)
    obj = await _get_item(OSP, item_id, toe_id, db)
    obj.review_status = "confirmed"; obj.reviewed_at = utcnow(); db.add(obj)
    return ok(data=_osp_dict(obj))


@router.post("/osps/{item_id}/reject")
async def reject_osp(toe_id: str, item_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    await _get_user_toe(toe_id, current_user, db)
    obj = await _get_item(OSP, item_id, toe_id, db)
    obj.review_status = "rejected"; obj.reviewed_at = utcnow(); db.add(obj)
    return ok(data=_osp_dict(obj))


@router.post("/osps/{item_id}/revert")
async def revert_osp(toe_id: str, item_id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    await _get_user_toe(toe_id, current_user, db)
    obj = await _get_item(OSP, item_id, toe_id, db)
    obj.review_status = "draft"; obj.reviewed_at = None; db.add(obj)
    return ok(data=_osp_dict(obj))


@router.post("/osps/batch-confirm")
async def batch_confirm_osps(
    toe_id: str,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Batch confirm OSPs."""
    await _get_user_toe(toe_id, current_user, db)
    ids = validate_batch_ids(payload.get("ids", []))
    
    result = await db.exec(
        select(OSP).where(
            OSP.toe_id == toe_id,
            OSP.id.in_(ids),
            OSP.deleted_at.is_(None),
        )
    )
    items = result.all()
    
    for item in items:
        item.review_status = "confirmed"
        item.reviewed_at = utcnow()
        db.add(item)
    
    await db.commit()
    return ok(data={"updated": len(items)})


@router.post("/osps/batch-reject")
async def batch_reject_osps(
    toe_id: str,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Batch reject OSPs."""
    await _get_user_toe(toe_id, current_user, db)
    ids = validate_batch_ids(payload.get("ids", []))
    
    result = await db.exec(
        select(OSP).where(
            OSP.toe_id == toe_id,
            OSP.id.in_(ids),
            OSP.deleted_at.is_(None),
        )
    )
    items = result.all()
    
    for item in items:
        item.review_status = "rejected"
        item.reviewed_at = utcnow()
        db.add(item)
    
    await db.commit()
    return ok(data={"updated": len(items)})


@router.post("/osps/ai-suggest")
async def ai_suggest_osps(
    toe_id: str,
    language: str = Query("en"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Suggest OSPs with AI (synchronous call)."""
    toe = await _get_user_toe(toe_id, current_user, db)
    ai = await get_ai_service(db, current_user.id)
    if not ai:
        raise HTTPException(400, "Please configure and verify an AI model first")

    existing = (await db.exec(
        select(OSP).where(OSP.toe_id == toe_id, OSP.deleted_at.is_(None))
    )).all()
    existing_codes = [o.code for o in existing]

    language = (language or "en").lower()

    output_language = "Chinese" if language == "zh" else "English"
    prompt = f"""Generate a list of organizational security policies (OSPs) for the TOE below.

TOE Name: {toe.name}
TOE Type: {toe.toe_type}
Summary: {toe.brief_intro or 'None'}
Description: {toe.description or 'None'}

Existing OSPs (do not duplicate): {', '.join(existing_codes) if existing_codes else 'None'}

OSPs should describe mandatory organizational security requirements or regulations. Format: P.NOUN_PHRASE (uppercase).

Return JSON in this format:
{{
    "osps": [
        {{
            "code": "P.ACCESS_CONTROL",
            "description": "OSP description"
        }}
    ]
}}

Requirements:
- Generate 3-5 OSPs
- Do not duplicate existing OSPs
- Descriptions must be in {output_language}, code must be in English"""

    result = await ai.chat_json(prompt)
    return ok(data=result.get("osps", []))


# ═══════════════════════════════════════════════════════════════
# B3-3 / B3-5  ST reference library upload & CRUD
# ═══════════════════════════════════════════════════════════════

ST_MIME_OK = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/html",
    "text/plain",
}


@router.get("/st-references")
async def list_st_references(
    toe_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get available ST references: private (owned) plus globally shared ones."""
    await _get_user_toe(toe_id, current_user, db, writable=False)
    result = await db.exec(
        select(STReference).where(
            STReference.deleted_at.is_(None),
            (STReference.user_id == current_user.id) | (STReference.is_shared == True),
        ).order_by(STReference.created_at.desc())
    )
    return ok(data=[_st_ref_dict(r) for r in result.all()])


@router.post("/st-references")
async def upload_st_reference(
    toe_id: str,
    product_name: Optional[str] = Query(None),
    language: str = Query("en"),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """B3-3: Upload an ST reference document and trigger the parsing task."""
    import logging, aiofiles
    log = logging.getLogger(__name__)
    log.info("[ST upload] start user=%s toe=%s file=%s", current_user.id, toe_id, file.filename)

    await _get_user_toe(toe_id, current_user, db)
    log.info("[ST upload] TOE validation passed")

    safe_original = sanitize_filename(file.filename)
    ext = get_safe_extension(safe_original, ALLOWED_EXT_ST_REFERENCE)
    mime = file.content_type or "application/octet-stream"
    # Fallback MIME inference using extension, prevent browser sending application/octet-stream
    _ext_mime = {
        ".pdf": "application/pdf",
        ".doc": "application/msword",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".html": "text/html",
        ".htm": "text/html",
    }
    if mime not in ST_MIME_OK and ext in _ext_mime:
        mime = _ext_mime[ext]
    if mime not in ST_MIME_OK:
        raise HTTPException(400, f"Only PDF, Word, and HTML files are supported (received {mime})")

    log.info("[ST upload] reading file content")
    content = await file.read()
    log.info("[ST upload] file read complete size=%d", len(content))

    validate_size(len(content))

    store_dir = os.path.join(settings.storage_path, current_user.id, "st_references")
    os.makedirs(store_dir, exist_ok=True)
    stored_name = f"{uuid.uuid4().hex}{ext}"
    file_path = os.path.join(store_dir, stored_name)

    # Use aiofiles for async file write, don't block event loop
    log.info("[ST upload] writing file path=%s", file_path)
    async with aiofiles.open(file_path, "wb") as f:
        await f.write(content)
    log.info("[ST upload] file write complete")

    # Infer file type tag from MIME
    _mime_label = {
        "application/pdf": "PDF",
        "application/msword": "Word",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "Word",
        "text/html": "HTML",
        "application/xhtml+xml": "HTML",
    }
    file_type_label = _mime_label.get(mime, ext.lstrip(".").upper() or "Unknown")

    # Create ST_REFERENCE record
    name = product_name or os.path.splitext(safe_original)[0] or "Untitled"
    st_ref = STReference(
        user_id=current_user.id,
        toe_id=toe_id,
        product_name=name,
        product_type=file_type_label,
        parse_status="pending",
    )
    db.add(st_ref)
    await db.flush()

    # Create file record
    st_file = STReferenceFile(
        st_reference_id=st_ref.id,
        filename=stored_name,
        file_path=file_path,
        file_size=len(content),
        mime_type=mime,
    )
    db.add(st_file)

    # Create parsing task
    progress_msg = "Processing..."
    task = AITask(
        user_id=current_user.id,
        toe_id=toe_id,
        task_type="st_parse",
        status="pending",
        progress_message=progress_msg,
    )
    db.add(task)
    await db.flush()

    from app.worker.worker import arq_pool
    if arq_pool:
        await arq_pool.enqueue_job("st_parse_task", st_ref.id, task.id, language)

    msg = "Uploaded successfully, parsing in progress"
    return ok(data={**_st_ref_dict(st_ref), "task_id": task.id}, msg=msg)


@router.delete("/st-references/{ref_id}")
async def delete_st_reference(
    toe_id: str, ref_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_user_toe(toe_id, current_user, db)
    result = await db.exec(
        select(STReference).where(
            STReference.id == ref_id,
            STReference.user_id == current_user.id,
            STReference.deleted_at.is_(None),
        )
    )
    ref = result.first()
    if not ref:
        raise NotFoundError("ST reference not found")
    ref.soft_delete()
    db.add(ref)
    return ok(msg="Deleted successfully")


@router.post("/st-references/{ref_id}/retry-parse")
async def retry_st_parse(
    toe_id: str, ref_id: str,
    language: str = Query("en"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Re-parse a failed ST reference."""
    await _get_user_toe(toe_id, current_user, db)
    result = await db.exec(
        select(STReference).where(
            STReference.id == ref_id,
            STReference.user_id == current_user.id,
            STReference.deleted_at.is_(None),
        )
    )
    ref = result.first()
    if not ref:
        raise NotFoundError("ST reference not found")

    ref.parse_status = "pending"
    ref.parse_error = None
    db.add(ref)

    progress_msg = "Re-processing..."
    task = AITask(
        user_id=current_user.id,
        toe_id=toe_id,
        task_type="st_parse",
        status="pending",
        progress_message=progress_msg,
    )
    db.add(task)
    await db.flush()

    from app.worker.worker import arq_pool
    if arq_pool:
        await arq_pool.enqueue_job("st_parse_task", ref.id, task.id, language)

    msg = "Re-queued successfully"
    return ok(data={"task_id": task.id}, msg=msg)


@router.patch("/st-references/{ref_id}/share")
async def toggle_share_st_reference(
    toe_id: str, ref_id: str,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """Allow an admin to mark an ST reference as globally shared."""
    result = await db.exec(
        select(STReference).where(STReference.id == ref_id, STReference.deleted_at.is_(None))
    )
    ref = result.first()
    if not ref:
        raise NotFoundError("ST reference not found")
    ref.is_shared = bool(payload.get("is_shared", True))
    db.add(ref)
    return ok(data=_st_ref_dict(ref))


# ═══════════════════════════════════════════════════════════════
# B3-6  Threat CRUD
# ═══════════════════════════════════════════════════════════════

@router.get("/threats")
async def list_threats(
    toe_id: str,
    status: Optional[str] = Query(None),
    risk_level: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_user_toe(toe_id, current_user, db, writable=False)
    stmt = select(Threat).where(
        Threat.toe_id == toe_id,
        Threat.deleted_at.is_(None),
    ).order_by(Threat.created_at)
    if status:
        stmt = stmt.where(Threat.review_status == status)
    if risk_level:
        stmt = stmt.where(Threat.risk_level == risk_level)
    result = await db.exec(stmt)
    threats = result.all()
    threat_ids = [item.id for item in threats]
    linked_assets = await _load_threat_asset_map(threat_ids, db)
    return ok(data=[_threat_dict(t, linked_assets.get(t.id, [])) for t in threats])


@router.post("/threats")
async def create_threat(
    toe_id: str, payload: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_user_toe(toe_id, current_user, db)
    code = (payload.get("code") or "").strip().upper()
    if not code:
        raise HTTPException(400, "code is required")
    if not code.startswith("T."):
        code = "T." + code
    code = await _unique_code(Threat, toe_id, code, db)

    likelihood = payload.get("likelihood", "medium")
    impact = payload.get("impact", "medium")
    risk_level = calc_risk_level(likelihood, impact)

    threat = Threat(
        toe_id=toe_id,
        code=code,
        threat_agent=payload.get("threat_agent"),
        adverse_action=payload.get("adverse_action"),
        assets_affected=payload.get("assets_affected"),
        likelihood=likelihood,
        impact=impact,
        risk_level=risk_level,
        review_status=payload.get("review_status", "pending"),
        ai_rationale=payload.get("ai_rationale"),
        ai_source_ref=payload.get("ai_source_ref"),
    )
    db.add(threat)
    await db.flush()
    linked_assets = await _resolve_threat_assets_for_payload(toe_id, payload, db, threat)
    await _replace_threat_asset_links(threat.id, linked_assets, db)
    return ok(data=_threat_dict(threat, linked_assets), msg="Created successfully")


@router.put("/threats/{threat_id}")
async def update_threat(
    toe_id: str, threat_id: str, payload: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_user_toe(toe_id, current_user, db)
    threat = await _get_item(Threat, threat_id, toe_id, db)

    updatable = ["code", "threat_agent", "adverse_action", "assets_affected", "likelihood", "impact"]
    for f in updatable:
        if f in payload:
            setattr(threat, f, payload[f])

    # B3-8: Recalculate risk level (unless manually overridden)
    if not threat.risk_overridden:
        threat.risk_level = calc_risk_level(threat.likelihood, threat.impact)

    if "asset_ids" in payload:
        linked_assets = await _resolve_explicit_assets(toe_id, payload.get("asset_ids") or [], db)
        await _replace_threat_asset_links(threat.id, linked_assets, db)
    else:
        linked_assets = await _load_assets_for_threat(threat.id, db)

    threat.updated_at = utcnow()
    db.add(threat)
    return ok(data=_threat_dict(threat, linked_assets))


@router.delete("/threats/{threat_id}")
async def delete_threat(
    toe_id: str, threat_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_user_toe(toe_id, current_user, db)
    threat = await _get_item(Threat, threat_id, toe_id, db)
    threat.soft_delete()
    db.add(threat)
    return ok(msg="Deleted successfully")


# ═══════════════════════════════════════════════════════════════
# B3-7  Threat review interface (single + batch)
# ═══════════════════════════════════════════════════════════════

@router.post("/threats/{threat_id}/confirm")
async def confirm_threat(
    toe_id: str, threat_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_user_toe(toe_id, current_user, db)
    threat = await _get_item(Threat, threat_id, toe_id, db)
    threat.review_status = "confirmed"
    threat.reviewed_at = utcnow()
    db.add(threat)
    return ok(data=_threat_dict(threat))


@router.post("/threats/{threat_id}/false-positive")
async def false_positive_threat(
    toe_id: str, threat_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_user_toe(toe_id, current_user, db)
    threat = await _get_item(Threat, threat_id, toe_id, db)
    threat.review_status = "false_positive"
    threat.reviewed_at = utcnow()
    db.add(threat)
    return ok(data=_threat_dict(threat))


@router.post("/threats/{threat_id}/revert")
async def revert_threat(
    toe_id: str, threat_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_user_toe(toe_id, current_user, db)
    threat = await _get_item(Threat, threat_id, toe_id, db)
    threat.review_status = "pending"
    threat.reviewed_at = None
    db.add(threat)
    return ok(data=_threat_dict(threat))


@router.put("/threats/{threat_id}/risk-override")
async def override_risk_level(
    toe_id: str, threat_id: str, payload: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """B3-8: Manually override the risk level."""
    await _get_user_toe(toe_id, current_user, db)
    threat = await _get_item(Threat, threat_id, toe_id, db)
    new_level = payload.get("risk_level")
    if new_level not in ("low", "medium", "high", "critical"):
        raise HTTPException(400, "risk_level must be one of low, medium, high, or critical")
    threat.risk_level = new_level
    threat.risk_overridden = True
    threat.updated_at = utcnow()
    db.add(threat)
    return ok(data=_threat_dict(threat))


@router.post("/threats/batch-confirm")
async def batch_confirm_threats(
    toe_id: str, payload: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Batch confirm threats."""
    await _get_user_toe(toe_id, current_user, db)
    ids: List[str] = validate_batch_ids(payload.get("ids", []))
    now = utcnow()
    updated = 0
    for tid in ids:
        result = await db.exec(
            select(Threat).where(Threat.id == tid, Threat.toe_id == toe_id, Threat.deleted_at.is_(None))
        )
        t = result.first()
        if t:
            t.review_status = "confirmed"
            t.reviewed_at = now
            db.add(t)
            updated += 1
    return ok(data={"updated": updated})


@router.post("/threats/batch-delete")
async def batch_delete_threats(
    toe_id: str, payload: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Batch delete threats."""
    await _get_user_toe(toe_id, current_user, db)
    ids: List[str] = validate_batch_ids(payload.get("ids", []))
    deleted = 0
    for tid in ids:
        result = await db.exec(
            select(Threat).where(Threat.id == tid, Threat.toe_id == toe_id, Threat.deleted_at.is_(None))
        )
        t = result.first()
        if t:
            t.soft_delete()
            db.add(t)
            deleted += 1
    return ok(data={"deleted": deleted})


@router.post("/threats/batch-false-positive")
async def batch_false_positive_threats(
    toe_id: str, payload: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Batch mark threats as false positives."""
    await _get_user_toe(toe_id, current_user, db)
    ids: List[str] = validate_batch_ids(payload.get("ids", []))
    now = utcnow()
    updated = 0
    for tid in ids:
        result = await db.exec(
            select(Threat).where(Threat.id == tid, Threat.toe_id == toe_id, Threat.deleted_at.is_(None))
        )
        t = result.first()
        if t:
            t.review_status = "false_positive"
            t.reviewed_at = now
            db.add(t)
            updated += 1
    return ok(data={"updated": updated})


@router.post("/assets/{asset_id}/toggle-weak-coverage-ignore")
async def toggle_weak_coverage_ignore(
    toe_id: str,
    asset_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Toggle ignore flag for weak coverage finding on an asset."""
    toe = await _get_user_toe(toe_id, current_user, db)
    
    asset = (await db.exec(
        select(TOEAsset).where(TOEAsset.id == asset_id, TOEAsset.toe_id == toe_id)
    )).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    # Toggle the flag
    asset.weak_coverage_ignored = not asset.weak_coverage_ignored
    db.add(asset)
    await db.commit()
    await db.refresh(asset)
    
    return ok(data={"asset_id": asset.id, "weak_coverage_ignored": asset.weak_coverage_ignored})


@router.get("/threats/completeness-report")
async def get_threat_completeness_report(
    toe_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate a threat completeness report based on the current modeling results."""
    toe = await _get_user_toe(toe_id, current_user, db, writable=False)

    assets = (await db.exec(
        select(TOEAsset).where(
            TOEAsset.toe_id == toe_id,
            TOEAsset.deleted_at.is_(None),
        ).order_by(TOEAsset.importance.desc(), TOEAsset.created_at)
    )).all()
    threats = (await db.exec(
        select(Threat).where(
            Threat.toe_id == toe_id,
            Threat.deleted_at.is_(None),
        ).order_by(Threat.created_at)
    )).all()
    assumptions = (await db.exec(
        select(Assumption).where(
            Assumption.toe_id == toe_id,
            Assumption.deleted_at.is_(None),
        )
    )).all()
    osps = (await db.exec(
        select(OSP).where(
            OSP.toe_id == toe_id,
            OSP.deleted_at.is_(None),
        )
    )).all()
    objectives = (await db.exec(
        select(SecurityObjective).where(
            SecurityObjective.toe_id == toe_id,
            SecurityObjective.deleted_at.is_(None),
        )
    )).all()
    sfrs = (await db.exec(
        select(SFR).where(
            SFR.toe_id == toe_id,
            SFR.deleted_at.is_(None),
        )
    )).all()
    objective_ids = {item.id for item in objectives}
    threat_ids = [item.id for item in threats]
    assumption_ids = [item.id for item in assumptions]
    osp_ids = [item.id for item in osps]
    threat_asset_map = await _load_threat_asset_map(threat_ids, db)

    threat_objective_rows = (await db.exec(
        select(ThreatObjective).where(ThreatObjective.threat_id.in_(threat_ids))
    )).all() if threat_ids else []
    assumption_objective_rows = (await db.exec(
        select(AssumptionObjective).where(AssumptionObjective.assumption_id.in_(assumption_ids))
    )).all() if assumption_ids else []
    osp_objective_rows = (await db.exec(
        select(OSPObjective).where(OSPObjective.osp_id.in_(osp_ids))
    )).all() if osp_ids else []
    relevant_threats = [item for item in threats if item.review_status != "false_positive"]
    threat_texts = {
        item.id: _normalize_text(" ".join([
            item.code or "",
            item.threat_agent or "",
            item.adverse_action or "",
            item.assets_affected or "",
            item.ai_rationale or "",
            item.ai_source_ref or "",
        ]))
        for item in relevant_threats
    }
    threat_text_list = list(threat_texts.values())
    combined_threat_text = " ".join(threat_text_list)
    threat_codes = {item.code for item in relevant_threats}

    mapped_threat_ids = {row.threat_id for row in threat_objective_rows}
    mapped_assumption_ids = {row.assumption_id for row in assumption_objective_rows}
    mapped_osp_ids = {row.osp_id for row in osp_objective_rows}
    objectives_with_sources = {
        *(row.objective_id for row in threat_objective_rows if row.objective_id in objective_ids),
        *(row.objective_id for row in assumption_objective_rows if row.objective_id in objective_ids),
        *(row.objective_id for row in osp_objective_rows if row.objective_id in objective_ids),
    }
    objective_type_by_id = {item.id: item.obj_type for item in objectives}

    threat_objective_type_map: Dict[str, Set[str]] = {item.id: set() for item in relevant_threats}
    for row in threat_objective_rows:
        objective_type = objective_type_by_id.get(row.objective_id)
        if objective_type and row.threat_id in threat_objective_type_map:
            threat_objective_type_map[row.threat_id].add(objective_type)

    assumption_objective_type_map: Dict[str, Set[str]] = {item.id: set() for item in assumptions}
    for row in assumption_objective_rows:
        objective_type = objective_type_by_id.get(row.objective_id)
        if objective_type and row.assumption_id in assumption_objective_type_map:
            assumption_objective_type_map[row.assumption_id].add(objective_type)

    osp_objective_type_map: Dict[str, Set[str]] = {item.id: set() for item in osps}
    for row in osp_objective_rows:
        objective_type = objective_type_by_id.get(row.objective_id)
        if objective_type and row.osp_id in osp_objective_type_map:
            osp_objective_type_map[row.osp_id].add(objective_type)

    uncovered_assets = []
    lightly_covered_assets = []
    for asset in assets:
        related = [item for item in relevant_threats if asset.id in {linked.id for linked in threat_asset_map.get(item.id, [])}]
        if not related:
            terms = _build_asset_search_terms(asset)
            for threat in relevant_threats:
                threat_text = threat_texts.get(threat.id, "")
                if any(term and term in threat_text for term in terms):
                    related.append(threat)

        if not related:
            uncovered_assets.append({
                "id": asset.id,
                "label": asset.name,
                "detail": f"{asset.asset_type} / Importance: {asset.importance}",
                "importance": asset.importance,
            })
        elif asset.importance >= 4 and len(related) < 2:
            # Skip if this weak coverage issue is ignored
            if not asset.weak_coverage_ignored:
                lightly_covered_assets.append({
                    "id": asset.id,
                    "label": asset.name,
                    "detail": f"Only associated with {len(related)} threat(s): {', '.join(t.code for t in related[:3])}",
                    "importance": asset.importance,
                })

    interface_gaps = []
    interface_entries = _split_interface_entries([
        toe.hw_interfaces,
        toe.sw_interfaces,
        toe.external_interfaces,
    ])
    for entry in interface_entries:
        normalized = _normalize_text(entry)
        if not normalized:
            continue
        if normalized in combined_threat_text:
            continue
        if any(token and token in combined_threat_text for token in _extract_ascii_tokens(entry)):
            continue
        interface_gaps.append({
            "label": entry,
            "detail": "Interface appears in TOE description, but is not explicitly covered by current threat text.",
        })

    threats_without_objectives = [
        {
            "id": item.id,
            "label": item.code,
            "detail": _threat_summary(item),
            "risk_level": item.risk_level,
        }
        for item in relevant_threats
        if item.id not in mapped_threat_ids
    ]
    assumptions_without_objectives = [
        {
            "id": item.id,
            "label": item.code,
            "detail": _compact_text(item.description),
        }
        for item in assumptions
        if item.id not in mapped_assumption_ids
    ]
    osps_without_objectives = [
        {
            "id": item.id,
            "label": item.code,
            "detail": _compact_text(item.description),
        }
        for item in osps
        if item.id not in mapped_osp_ids
    ]
    objectives_without_sources = [
        {
            "id": item.id,
            "label": item.code,
            "detail": _compact_text(item.description),
        }
        for item in objectives
        if item.id not in objectives_with_sources
    ]
    threats_mapped_to_oe_count = sum(
        1 for item in relevant_threats if "OE" in threat_objective_type_map.get(item.id, set())
    )
    assumptions_without_o_objectives = [
        {
            "id": item.id,
            "label": item.code,
            "detail": _compact_text(item.description),
        }
        for item in assumptions
        if "O" not in assumption_objective_type_map.get(item.id, set())
    ]
    assumptions_without_oe_objectives = [
        {
            "id": item.id,
            "label": item.code,
            "detail": _compact_text(item.description),
        }
        for item in assumptions
        if "OE" not in assumption_objective_type_map.get(item.id, set())
    ]
    osps_mapped_to_oe_count = sum(
        1 for item in osps if "OE" in osp_objective_type_map.get(item.id, set())
    )
    o_objectives_without_sources = [
        {
            "id": item.id,
            "label": item.code,
            "detail": _compact_text(item.description),
        }
        for item in objectives
        if item.obj_type == "O" and item.id not in objectives_with_sources
    ]
    oe_objectives_without_sources = [
        {
            "id": item.id,
            "label": item.code,
            "detail": _compact_text(item.description),
        }
        for item in objectives
        if item.obj_type == "OE" and item.id not in objectives_with_sources
    ]
    metrics = [
        _build_metric("asset_coverage", len(assets) - len(uncovered_assets), len(assets)),
        _build_metric("threat_objective_coverage", len(relevant_threats) - len(threats_without_objectives), len(relevant_threats)),
        _build_metric("assumption_objective_coverage", len(assumptions) - len(assumptions_without_objectives), len(assumptions)),
        _build_metric("osp_objective_coverage", len(osps) - len(osps_without_objectives), len(osps)),
    ]
    score = _weighted_score(metrics)

    findings = [
        _build_finding("uncovered_assets", "high", uncovered_assets),
        _build_finding("lightly_covered_assets", "medium", lightly_covered_assets),
        _build_finding("threats_without_assets", "medium", [
            {
                "id": item.id,
                "label": item.code,
                "detail": _threat_summary(item),
            }
            for item in relevant_threats
            if not threat_asset_map.get(item.id)
        ]),
        _build_finding("interface_gaps", "medium", interface_gaps),
        _build_finding("threats_without_objectives", "high", threats_without_objectives),
        _build_finding("assumptions_without_objectives", "medium", assumptions_without_objectives),
        _build_finding("osps_without_objectives", "medium", osps_without_objectives),
        _build_finding("objectives_without_sources", "medium", objectives_without_sources),
    ]

    next_actions = []
    if uncovered_assets:
        next_actions.append("action_cover_uncovered_assets")
    if threats_without_objectives:
        next_actions.append("action_threat_objectives")
    if assumptions_without_objectives:
        next_actions.append("action_assumption_objectives")
    if osps_without_objectives:
        next_actions.append("action_osp_objectives")
    if objectives_without_sources:
        next_actions.append("action_objectives_sources")
    if not next_actions:
        next_actions.append("action_no_gaps")

    total_findings = sum(item["count"] for item in findings)
    high_findings = sum(1 for item in findings if item["severity"] == "high" and item["count"] > 0)
    summary_status = "good" if score >= 85 and high_findings == 0 else "attention" if score >= 60 else "weak"

    mapping_gap_sections = [
        {
            "key": "threat_to_o",
            "source_type": "threat",
            "objective_type": "O",
            "covered": len(relevant_threats) - len(threats_without_objectives),
            "total": len(relevant_threats),
            "gaps": threats_without_objectives[:8],
            "overflow": max(0, len(threats_without_objectives) - 8),
        },
        {
            "key": "threat_to_oe",
            "source_type": "threat",
            "objective_type": "OE",
            "covered": threats_mapped_to_oe_count,
            "total": len(relevant_threats),
            "gaps": [],
            "overflow": 0,
        },
        {
            "key": "assumption_to_oe",
            "source_type": "assumption",
            "objective_type": "OE",
            "covered": len(assumptions) - len(assumptions_without_oe_objectives),
            "total": len(assumptions),
            "gaps": assumptions_without_oe_objectives[:8],
            "overflow": max(0, len(assumptions_without_oe_objectives) - 8),
        },
        {
            "key": "osp_to_o",
            "source_type": "osp",
            "objective_type": "O",
            "covered": len(osps) - len(osps_without_objectives),
            "total": len(osps),
            "gaps": osps_without_objectives[:8],
            "overflow": max(0, len(osps_without_objectives) - 8),
        },
        {
            "key": "osp_to_oe",
            "source_type": "osp",
            "objective_type": "OE",
            "covered": osps_mapped_to_oe_count,
            "total": len(osps),
            "gaps": [],
            "overflow": 0,
        },
        {
            "key": "objective_o_to_sources",
            "source_type": "objective",
            "objective_type": "O",
            "covered": len([item for item in objectives if item.obj_type == "O"]) - len(o_objectives_without_sources),
            "total": len([item for item in objectives if item.obj_type == "O"]),
            "gaps": o_objectives_without_sources[:8],
            "overflow": max(0, len(o_objectives_without_sources) - 8),
        },
        {
            "key": "objective_oe_to_sources",
            "source_type": "objective",
            "objective_type": "OE",
            "covered": len([item for item in objectives if item.obj_type == "OE"]) - len(oe_objectives_without_sources),
            "total": len([item for item in objectives if item.obj_type == "OE"]),
            "gaps": oe_objectives_without_sources[:8],
            "overflow": max(0, len(oe_objectives_without_sources) - 8),
        },
    ]

    covered_assets_count = len(assets) - len(uncovered_assets)

    return ok(data={
        "summary": {
            "score": score,
            "status": summary_status,
            "total_findings": total_findings,
            "high_findings": high_findings,
            "generated_at": utcnow().isoformat(),
            "basis_note": "basis_note_threats",
        },
        "basis": {
            "asset_count": len(assets),
            "covered_assets_count": covered_assets_count,
            "threat_count": len(relevant_threats),
            "confirmed_threat_count": len([item for item in relevant_threats if item.review_status == "confirmed"]),
            "assumption_count": len(assumptions),
            "osp_count": len(osps),
            "objective_count": len(objectives),
            "sfr_count": 0,
            "test_count": 0,
            "reference_threat_count": 0,
        },
        "metrics": metrics,
        "mapping_gap_sections": mapping_gap_sections,
        "findings": findings,
        "next_actions": next_actions,
    })


# ═══════════════════════════════════════════════════════════════
# B3-9 / B3-10  AI threat scanning (full + incremental)
# ═══════════════════════════════════════════════════════════════

@router.post("/threats/import-from-docs")
async def trigger_threat_import(
    toe_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Extract threats from the TOE's ST/PP documents and return a task_id."""
    await _get_user_toe(toe_id, current_user, db)

    # Check if there are available ST/PP documents
    from app.models.toe import TOEFile
    files_result = await db.exec(
        select(TOEFile).where(
            TOEFile.toe_id == toe_id,
            TOEFile.file_category == "st_pp",
            TOEFile.process_status == "ready",
            TOEFile.deleted_at.is_(None),
        )
    )
    st_pp_files = files_result.all()
    if not st_pp_files:
        raise HTTPException(400, "No processed ST/PP documents were found for this TOE. Upload one and wait for processing to finish.")

    task = AITask(
        user_id=current_user.id,
        toe_id=toe_id,
        task_type="threat_import",
        status="pending",
        progress_message="Preparing threat extraction from documents...",
    )
    db.add(task)
    await db.flush()

    from app.worker.worker import arq_pool
    if arq_pool:
        await arq_pool.enqueue_job("threat_import_task", toe_id, task.id)

    return ok(data={"task_id": task.id}, msg="Threat import task queued")


@router.post("/threats/ai-scan")
async def trigger_threat_scan(
    toe_id: str,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Trigger an AI threat scan task and return a task_id. mode: full | incremental"""
    await _get_user_toe(toe_id, current_user, db)
    mode = payload.get("mode", "full")
    language = (payload.get("language") or "en").lower()
    if mode not in ("full", "incremental"):
        raise HTTPException(400, "mode must be full or incremental")
    if language not in ("zh", "en"):
        language = "en"

    progress_message = "Stage 1/4: Preparing scan..."
    queued_message = "Threat scan task started"

    task = AITask(
        user_id=current_user.id,
        toe_id=toe_id,
        task_type="threat_scan",
        status="pending",
        progress_message=progress_message,
    )
    db.add(task)
    await db.flush()

    from app.worker.worker import arq_pool
    if arq_pool:
        await arq_pool.enqueue_job("threat_scan_task", toe_id, mode, task.id, language)
    else:
        from app.worker.tasks import threat_scan_task
        asyncio.create_task(threat_scan_task({}, toe_id, mode, task.id, language))

    return ok(data={"task_id": task.id}, msg=queued_message)


# ═══════════════════════════════════════════════════════════════
# Helper functions
# ═══════════════════════════════════════════════════════════════

async def _get_item(Model, item_id: str, toe_id: str, db: AsyncSession):
    result = await db.exec(
        select(Model).where(
            Model.id == item_id,
            Model.toe_id == toe_id,
            Model.deleted_at.is_(None),
        )
    )
    obj = result.first()
    if not obj:
        raise NotFoundError(f"{Model.__tablename__} not found")
    return obj


def _assumption_dict(a: Assumption) -> dict:
    return {
        "id": a.id, "toe_id": a.toe_id, "code": a.code,
        "description": a.description,
        "review_status": a.review_status, "ai_generated": a.ai_generated,
        "reviewed_at": a.reviewed_at.isoformat() if a.reviewed_at else None,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


def _osp_dict(o: OSP) -> dict:
    return {
        "id": o.id, "toe_id": o.toe_id, "code": o.code,
        "description": o.description,
        "review_status": o.review_status, "ai_generated": o.ai_generated,
        "reviewed_at": o.reviewed_at.isoformat() if o.reviewed_at else None,
        "created_at": o.created_at.isoformat() if o.created_at else None,
    }


async def _load_threat_asset_map(threat_ids: List[str], db: AsyncSession) -> dict[str, List[TOEAsset]]:
    if not threat_ids:
        return {}
    link_rows = (await db.exec(
        select(ThreatAssetLink).where(ThreatAssetLink.threat_id.in_(threat_ids))
    )).all()
    if not link_rows:
        return {threat_id: [] for threat_id in threat_ids}

    asset_ids = list({row.asset_id for row in link_rows})
    assets = (await db.exec(
        select(TOEAsset).where(
            TOEAsset.id.in_(asset_ids),
            TOEAsset.deleted_at.is_(None),
        )
    )).all()
    asset_map = {item.id: item for item in assets}

    result = {threat_id: [] for threat_id in threat_ids}
    for row in link_rows:
        asset = asset_map.get(row.asset_id)
        if asset:
            result.setdefault(row.threat_id, []).append(asset)
    return result


async def _load_assets_for_threat(threat_id: str, db: AsyncSession) -> List[TOEAsset]:
    return (await _load_threat_asset_map([threat_id], db)).get(threat_id, [])


async def _resolve_explicit_assets(toe_id: str, asset_ids: List[str], db: AsyncSession) -> List[TOEAsset]:
    unique_ids = list(dict.fromkeys([asset_id for asset_id in asset_ids if asset_id]))
    if not unique_ids:
        return []
    assets = (await db.exec(
        select(TOEAsset).where(
            TOEAsset.toe_id == toe_id,
            TOEAsset.id.in_(unique_ids),
            TOEAsset.deleted_at.is_(None),
        )
    )).all()
    if len(assets) != len(unique_ids):
        raise HTTPException(400, "asset_ids contains invalid assets")
    asset_map = {item.id: item for item in assets}
    return [asset_map[asset_id] for asset_id in unique_ids]


async def _replace_threat_asset_links(threat_id: str, assets: List[TOEAsset], db: AsyncSession):
    await db.exec(delete(ThreatAssetLink).where(ThreatAssetLink.threat_id == threat_id))
    for asset in assets:
        db.add(ThreatAssetLink(threat_id=threat_id, asset_id=asset.id))


async def _resolve_threat_assets_for_payload(
    toe_id: str,
    payload: dict,
    db: AsyncSession,
    threat: Optional[Threat] = None,
) -> List[TOEAsset]:
    if "asset_ids" in payload:
        return await _resolve_explicit_assets(toe_id, payload.get("asset_ids") or [], db)
    return await _infer_assets_for_threat(toe_id, payload, db, threat)


async def _infer_assets_for_threat(
    toe_id: str,
    payload: dict,
    db: AsyncSession,
    threat: Optional[Threat] = None,
) -> List[TOEAsset]:
    assets = (await db.exec(
        select(TOEAsset).where(
            TOEAsset.toe_id == toe_id,
            TOEAsset.deleted_at.is_(None),
        )
    )).all()
    if not assets:
        return []

    text = _normalize_text(" ".join([
        str(payload.get("assets_affected") or ""),
        str(payload.get("adverse_action") or ""),
        str(payload.get("threat_agent") or ""),
        threat.assets_affected if threat and threat.assets_affected else "",
        threat.adverse_action if threat and threat.adverse_action else "",
        threat.threat_agent if threat and threat.threat_agent else "",
    ]))
    linked = []
    for asset in assets:
        for term in _build_asset_search_terms(asset):
            if term and term in text:
                linked.append(asset)
                break
    return linked


def _threat_dict(t: Threat, linked_assets: Optional[List[TOEAsset]] = None) -> dict:
    linked_assets = linked_assets or []
    return {
        "id": t.id, "toe_id": t.toe_id, "code": t.code,
        "threat_agent": t.threat_agent, "adverse_action": t.adverse_action,
        "assets_affected": t.assets_affected,
        "asset_ids": [item.id for item in linked_assets],
        "linked_assets": [
            {
                "id": item.id,
                "name": item.name,
                "asset_type": item.asset_type,
                "importance": item.importance,
            }
            for item in linked_assets
        ],
        "likelihood": t.likelihood, "impact": t.impact,
        "risk_level": t.risk_level, "risk_overridden": t.risk_overridden,
        "review_status": t.review_status,
        "ai_rationale": t.ai_rationale, "ai_source_ref": t.ai_source_ref,
        "reviewed_at": t.reviewed_at.isoformat() if t.reviewed_at else None,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }


def _st_ref_dict(r: STReference) -> dict:
    return {
        "id": r.id, "user_id": r.user_id, "toe_id": r.toe_id,
        "product_name": r.product_name, "product_type": r.product_type,
        "toe_type": r.toe_type, "cc_version": r.cc_version,
        "parse_status": r.parse_status, "parse_error": r.parse_error,
        "is_shared": r.is_shared,
        "threats_extracted": r.threats_extracted,
        "objectives_extracted": r.objectives_extracted,
        "sfr_extracted": r.sfr_extracted,
        "assets_extracted": r.assets_extracted,
        "parsed_at": r.parsed_at.isoformat() if r.parsed_at else None,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


def _normalize_text(value: Optional[str]) -> str:
    if not value:
        return ""
    text = re.sub(r"\s+", " ", value).strip().lower()
    return text


def _compact_text(value: Optional[str], limit: int = 100) -> str:
    text = re.sub(r"\s+", " ", (value or "")).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _extract_ascii_tokens(value: Optional[str]) -> List[str]:
    if not value:
        return []
    tokens = []
    for token in re.split(r"[^a-zA-Z0-9_./-]+", value.lower()):
        if len(token) >= 3:
            tokens.append(token)
    return list(dict.fromkeys(tokens))


def _build_asset_search_terms(asset: TOEAsset) -> List[str]:
    terms = []
    normalized_name = _normalize_text(asset.name)
    if normalized_name:
        terms.append(normalized_name)
    for token in _extract_ascii_tokens(asset.name):
        if token not in terms:
            terms.append(token)
    return terms


def _split_interface_entries(values: List[Optional[str]]) -> List[str]:
    entries = []
    for value in values:
        if not value:
            continue
        for item in re.split(r"[\n,;，；、]+", value):
            cleaned = item.strip()
            if len(cleaned) >= 3:
                entries.append(cleaned)
    return list(dict.fromkeys(entries))


def _threat_summary(threat: Threat) -> str:
    parts = [part for part in [threat.threat_agent, threat.adverse_action, threat.assets_affected] if part]
    return _compact_text(" / ".join(parts)) or "Threat definition not provided"


def _parse_json_list(raw: Optional[str]) -> List:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except Exception:
        return []
    return parsed if isinstance(parsed, list) else []


def _extract_reference_threats(raw: Optional[str]) -> List[dict]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except Exception:
        return []

    if isinstance(parsed, dict):
        candidates = parsed.get("threats") or parsed.get("items") or []
    elif isinstance(parsed, list):
        candidates = parsed
    else:
        candidates = []

    results = []
    for item in candidates:
        if isinstance(item, str):
            text = item.strip()
            if text:
                results.append({"code": "", "title": text, "text": text})
            continue
        if not isinstance(item, dict):
            continue
        code = str(item.get("code") or item.get("id") or "").strip()
        title = str(item.get("title") or item.get("name") or code).strip()
        text = str(item.get("description") or item.get("text") or title).strip()
        if code or title or text:
            results.append({"code": code, "title": title, "text": text})
    return results


def _build_metric(key: str, covered: int, total: int) -> dict:
    if total <= 0:
        return {
            "key": key,
            "covered": 0,
            "total": 0,
            "percent": 100,
            "status": "not_applicable",
        }
    percent = round(covered * 100 / total)
    status = "good" if percent >= 85 else "attention" if percent >= 60 else "weak"
    return {
        "key": key,
        "covered": covered,
        "total": total,
        "percent": percent,
        "status": status,
    }


def _weighted_score(metrics: List[dict]) -> int:
    weight_map = {
        "asset_coverage": 0.20,
        "threat_objective_coverage": 0.20,
        "assumption_objective_coverage": 0.05,
        "osp_objective_coverage": 0.05,
        "objective_sfr_coverage": 0.20,
        "sfr_test_coverage": 0.15,
        "risk_assessment_coverage": 0.10,
        "reference_alignment": 0.05,
    }
    active = [item for item in metrics if item["total"] > 0]
    if not active:
        return 100
    total_weight = sum(weight_map.get(item["key"], 0.0) for item in active) or 1.0
    score = sum(item["percent"] * weight_map.get(item["key"], 0.0) for item in active)
    return round(score / total_weight)


def _build_finding(key: str, severity: str, items: List[dict]) -> dict:
    return {
        "key": key,
        "severity": severity,
        "count": len(items),
        "items": items[:20],
        "overflow": max(len(items) - 20, 0),
    }
