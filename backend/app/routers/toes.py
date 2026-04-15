"""
TOE management routes - Phase 2.
Includes TOE CRUD, asset CRUD, file upload and status queries, AI description generation, AI asset suggestions, and cascading soft delete.
"""
import os
import re
import uuid
import json
import io
import logging
import zipfile

logger = logging.getLogger(__name__)
from typing import Optional, get_args, get_origin
from datetime import datetime, date, timezone
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, Form
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, func, col, delete

from app.core.database import get_db
from app.core.auth import get_current_user
from app.core.toe_permissions import get_accessible_toe, get_toe_access_level
from app.core.config import settings
from app.core.response import ok, NotFoundError, ForbiddenError
from app.core.uploads import (
    sanitize_filename,
    get_safe_extension,
    validate_size,
    ALLOWED_EXT_TOE_FILE,
)
from app.models.base import utcnow, new_uuid


def _escape_like(value: str) -> str:
    """Escape LIKE wildcards (% and _) so user input is treated as literals."""
    return value.replace("%", "\\%").replace("_", "\\_")
from app.models.user import User
from app.models.toe import TOE, TOEAsset, TOEFile, UserTOEPermission
from app.models.threat import Threat, ThreatAssetLink, Assumption, OSP
from app.models.security import SecurityObjective, ThreatObjective, AssumptionObjective, OSPObjective, SFR, ObjectiveSFR, SFRLibrary
from app.models.test_case import TestCase
from app.models.risk import RiskAssessment
from app.models.ai_task import AITask
from app.services.ai_service import get_ai_service

router = APIRouter(prefix="/api/toes", tags=["TOE Management"])

PACKAGE_VERSION = 1


# ── Helper: Ensure TOE belongs to current user ──────────────────────────────

async def _get_user_toe(toe_id: str, user: User, db: AsyncSession, writable: bool = True) -> TOE:
    return await get_accessible_toe(toe_id, user, db, writable=writable)


# ═══════════════════════════════════════════════════════════════
# B2-1  TOE CRUD
# ═══════════════════════════════════════════════════════════════

@router.get("")
async def list_toes(
    search: Optional[str] = Query(None, description="Search by name"),
    toe_type: Optional[str] = Query(None, description="Filter by type"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List the current user's TOEs with name search and type filtering."""
    stmt = select(TOE).where(TOE.deleted_at.is_(None)).order_by(TOE.created_at.desc())

    if current_user.role != "admin":
        permission_toe_ids = select(UserTOEPermission.toe_id).where(
            UserTOEPermission.user_id == current_user.id,
            UserTOEPermission.deleted_at.is_(None),
        )
        stmt = stmt.where(
            (TOE.user_id == current_user.id) | (TOE.id.in_(permission_toe_ids))
        )

    if search:
        stmt = stmt.where(col(TOE.name).ilike(f"%{_escape_like(search)}%"))
    if toe_type:
        stmt = stmt.where(TOE.toe_type == toe_type)

    result = await db.exec(stmt)
    toes = result.all()

    # Include count of assets and files for each TOE
    data = []
    for t in toes:
        asset_cnt = (await db.exec(
            select(func.count()).where(
                TOEAsset.toe_id == t.id, TOEAsset.deleted_at.is_(None)
            )
        )).one()
        file_cnt = (await db.exec(
            select(func.count()).where(
                TOEFile.toe_id == t.id, TOEFile.deleted_at.is_(None)
            )
        )).one()
        data.append({
            **_toe_dict(t),
            "access_level": await get_toe_access_level(t, current_user, db),
            "asset_count": asset_cnt,
            "file_count": file_cnt,
        })
    return ok(data=data)


@router.post("")
async def create_toe(
    payload: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a TOE."""
    name = (payload.get("name") or "").strip()
    toe_type = (payload.get("toe_type") or "").strip()
    if not name:
        raise HTTPException(400, "Name is required")
    if toe_type not in ("hardware", "software", "system"):
        raise HTTPException(400, "toe_type must be hardware, software, or system")

    toe = TOE(
        user_id=current_user.id,
        name=name,
        toe_type=toe_type,
        brief_intro=payload.get("brief_intro"),
        version=payload.get("version"),
        toe_type_desc=payload.get("toe_type_desc"),
        toe_usage=payload.get("toe_usage"),
        major_security_features=payload.get("major_security_features"),
        required_non_toe_hw_sw_fw=payload.get("required_non_toe_hw_sw_fw"),
        physical_scope=payload.get("physical_scope"),
        logical_scope=payload.get("logical_scope"),
        hw_interfaces=payload.get("hw_interfaces"),
        sw_interfaces=payload.get("sw_interfaces"),
    )
    db.add(toe)
    await db.flush()
    return ok(data=_toe_dict(toe), msg="Created successfully")


@router.get("/{toe_id}")
async def get_toe(
    toe_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get TOE details."""
    toe = await _get_user_toe(toe_id, current_user, db, writable=False)
    data = _toe_dict(toe)
    data["access_level"] = await get_toe_access_level(toe, current_user, db)
    return ok(data=data)


@router.put("/{toe_id}")
async def update_toe(
    toe_id: str,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Edit a TOE."""
    toe = await _get_user_toe(toe_id, current_user, db)

    updatable = [
        "name", "toe_type", "version", "brief_intro",
        "toe_type_desc", "toe_usage", "major_security_features",
        "required_non_toe_hw_sw_fw", "physical_scope", "logical_scope",
        "hw_interfaces", "sw_interfaces",
    ]
    for field in updatable:
        if field in payload:
            setattr(toe, field, payload[field])
    toe.updated_at = utcnow()
    db.add(toe)
    return ok(data=_toe_dict(toe), msg="Updated successfully")


@router.delete("/{toe_id}")
async def delete_toe(
    toe_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    B2-8: Soft-delete a TOE and cascade the soft delete to all child data.
    Return the number of deleted records for each child data type.
    """
    toe = await _get_user_toe(toe_id, current_user, db)
    now = utcnow()

    # Cascading soft delete — assets
    asset_result = await db.exec(
        select(TOEAsset).where(TOEAsset.toe_id == toe_id, TOEAsset.deleted_at.is_(None))
    )
    assets = asset_result.all()
    for a in assets:
        a.deleted_at = now
        db.add(a)

    # Cascading soft delete — files
    file_result = await db.exec(
        select(TOEFile).where(TOEFile.toe_id == toe_id, TOEFile.deleted_at.is_(None))
    )
    files = file_result.all()
    for f in files:
        f.deleted_at = now
        db.add(f)

    # Cascading soft delete — threats (Phase 3 model, early compatibility)
    threat_count = 0
    objective_count = 0
    sfr_count = 0
    test_count = 0
    risk_count = 0

    try:
        from app.models.threat import Threat, Assumption, OSP
        for Model in [Threat, Assumption, OSP]:
            res = await db.exec(
                select(Model).where(Model.toe_id == toe_id, Model.deleted_at.is_(None))
            )
            for item in res.all():
                item.deleted_at = now
                db.add(item)
                threat_count += 1
    except Exception:
        pass

    try:
        from app.models.security import SecurityObjective, SFR
        for Model, counter_name in [(SecurityObjective, "objective"), (SFR, "sfr")]:
            res = await db.exec(
                select(Model).where(Model.toe_id == toe_id, Model.deleted_at.is_(None))
            )
            items = res.all()
            for item in items:
                item.deleted_at = now
                db.add(item)
            if counter_name == "objective":
                objective_count = len(items)
            else:
                sfr_count = len(items)
    except Exception:
        pass

    try:
        from app.models.test_case import TestCase
        res = await db.exec(
            select(TestCase).where(TestCase.toe_id == toe_id, TestCase.deleted_at.is_(None))
        )
        items = res.all()
        for item in items:
            item.deleted_at = now
            db.add(item)
        test_count = len(items)
    except Exception:
        pass

    try:
        from app.models.risk import RiskAssessment
        res = await db.exec(
            select(RiskAssessment).where(RiskAssessment.toe_id == toe_id, RiskAssessment.deleted_at.is_(None))
        )
        items = res.all()
        for item in items:
            item.deleted_at = now
            db.add(item)
        risk_count = len(items)
    except Exception:
        pass

    # Finally delete TOE itself
    toe.deleted_at = now
    db.add(toe)

    return ok(data={
        "asset_count": len(assets),
        "file_count": len(files),
        "threat_count": threat_count,
        "objective_count": objective_count,
        "sfr_count": sfr_count,
        "test_count": test_count,
        "risk_count": risk_count,
    }, msg="Deleted successfully")


# ═══════════════════════════════════════════════════════════════
# B2-2  AI generate TOE description
# ═══════════════════════════════════════════════════════════════

@router.post("/ai-generate-description-draft")
async def ai_generate_description_draft(
    payload: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate a draft TOE description with AI (no existing TOE required, for the create flow)."""
    name = (payload.get("name") or "").strip()
    toe_type = (payload.get("toe_type") or "").strip()
    brief_intro = (payload.get("brief_intro") or "").strip()
    version = (payload.get("version") or "").strip()
    language = (payload.get("language") or "en").lower()
    if language not in ("zh", "en"):
        language = "en"

    if not name or not toe_type:
        raise HTTPException(400, "Name and toe_type are required")

    ai = await get_ai_service(db, current_user.id)
    if not ai:
        raise HTTPException(400, "Please configure and verify an AI model first")

    output_language = "Chinese" if language == "zh" else "English"
    prompt = f"""You are a CC (Common Criteria) security evaluation expert. Generate a draft TOE description for the following product. Return JSON with all fields as strings, each 50-150 words, concise and professional.

TOE Name: {name}
Category (hardware/software/system): {toe_type}
Brief intro: {brief_intro or 'N/A'}
Version: {version or 'N/A'}

Return JSON with exactly these fields:
{{
  "toe_type_desc": "Describe what type of product the TOE is (e.g. network IP camera for surveillance, content management system for web publishing). Explain the product category and main purpose.",
  "toe_usage": "Describe how the TOE is typically used in a real-world deployment scenario. Include typical users, operational environment, and common use cases.",
  "major_security_features": "List the TOE's main security features such as authentication, access control, audit logging, encryption, etc. Be specific to the product type.",
  "required_non_toe_hw_sw_fw": "List hardware, software, and firmware components that the TOE depends on but are not part of the TOE itself (e.g. OS, database, network infrastructure, host hardware).",
  "physical_scope": "Describe the physical scope that uniquely identifies the TOE: product name, model number, hardware version, software version, firmware version.",
  "logical_scope": "Describe the logical boundaries of the TOE's security functionality: which security functions are included in the evaluation scope and which are excluded.",
  "hw_interfaces": "Describe the hardware interfaces that are physically accessible on the TOE (e.g. USB ports, Ethernet ports, serial interfaces, power connectors).",
    "sw_interfaces": "Describe the software interfaces accessible to users or external systems (e.g. REST API, web management console, CLI, SNMP, MQTT)."
}}

All field values must be written in {output_language}."""

    try:
        result = await ai.chat_json(prompt, max_tokens=2500)
    except Exception as e:
        logger.warning("AI call failed: %s", e)
        raise HTTPException(400, "AI call failed: unable to get a response from the model")
    return ok(data=result)


@router.post("/{toe_id}/ai-generate-description")
async def ai_generate_description(
    toe_id: str,
    payload: dict | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate a draft TOE description with AI (synchronous call)."""
    language = ((payload or {}).get("language") or "en").lower()
    if language not in ("zh", "en"):
        language = "en"

    toe = await _get_user_toe(toe_id, current_user, db)

    ai = await get_ai_service(db, current_user.id)
    if not ai:
        raise HTTPException(400, "Please configure and verify an AI model first")

    output_language = "Chinese" if language == "zh" else "English"
    prompt = f"""You are a CC (Common Criteria) security evaluation expert. Generate a draft TOE description for the following product. Return JSON with all fields as strings, each 50-150 words, concise and professional.

TOE Name: {toe.name}
Category (hardware/software/system): {toe.toe_type}
Brief intro: {toe.brief_intro or 'N/A'}
Version: {toe.version or 'N/A'}

Return JSON with exactly these fields:
{{
  "toe_type_desc": "Describe what type of product the TOE is (e.g. network IP camera for surveillance, content management system for web publishing). Explain the product category and main purpose.",
  "toe_usage": "Describe how the TOE is typically used in a real-world deployment scenario. Include typical users, operational environment, and common use cases.",
  "major_security_features": "List the TOE's main security features such as authentication, access control, audit logging, encryption, etc. Be specific to the product type.",
  "required_non_toe_hw_sw_fw": "List hardware, software, and firmware components that the TOE depends on but are not part of the TOE itself (e.g. OS, database, network infrastructure, host hardware).",
  "physical_scope": "Describe the physical scope that uniquely identifies the TOE: product name, model number, hardware version, software version, firmware version.",
  "logical_scope": "Describe the logical boundaries of the TOE's security functionality: which security functions are included in the evaluation scope and which are excluded.",
  "hw_interfaces": "Describe the hardware interfaces that are physically accessible on the TOE (e.g. USB ports, Ethernet ports, serial interfaces, power connectors).",
    "sw_interfaces": "Describe the software interfaces accessible to users or external systems (e.g. REST API, web management console, CLI, SNMP, MQTT)."
}}

All field values must be written in {output_language}."""

    try:
        result = await ai.chat_json(prompt, max_tokens=2500)
    except Exception as e:
        logger.warning("AI call failed: %s", e)
        raise HTTPException(400, "AI call failed: unable to get a response from the model")
    return ok(data=result)


# ═══════════════════════════════════════════════════════════════
# B2-3  TOE asset CRUD
# ═══════════════════════════════════════════════════════════════

@router.get("/{toe_id}/assets")
async def list_assets(
    toe_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get the TOE asset list."""
    await _get_user_toe(toe_id, current_user, db, writable=False)
    result = await db.exec(
        select(TOEAsset).where(
            TOEAsset.toe_id == toe_id,
            TOEAsset.deleted_at.is_(None),
        ).order_by(TOEAsset.importance.desc(), TOEAsset.created_at)
    )
    return ok(data=[_asset_dict(a) for a in result.all()])


@router.post("/{toe_id}/assets")
async def create_asset(
    toe_id: str,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Add an asset."""
    await _get_user_toe(toe_id, current_user, db)

    name = (payload.get("name") or "").strip()
    asset_type = (payload.get("asset_type") or "").strip()
    if not name:
        raise HTTPException(400, "Asset name is required")
    if asset_type not in ("data", "function", "privacy", "config", "other"):
        raise HTTPException(400, "Invalid asset type")

    importance = payload.get("importance", 3)
    if not isinstance(importance, int) or importance < 1 or importance > 5:
        raise HTTPException(400, "Importance must be an integer from 1 to 5")

    asset = TOEAsset(
        toe_id=toe_id,
        name=name,
        description=payload.get("description"),
        asset_type=asset_type,
        importance=importance,
        importance_reason=payload.get("importance_reason"),
        ai_generated=payload.get("ai_generated", False),
    )
    db.add(asset)
    await db.flush()
    
    # Handle threat associations
    threat_ids = payload.get("asset_ids") or []
    if threat_ids:
        for threat_id in threat_ids:
            threat_result = await db.exec(
                select(Threat).where(Threat.id == threat_id, Threat.toe_id == toe_id)
            )
            if threat_result.first():
                db.add(ThreatAssetLink(threat_id=threat_id, asset_id=asset.id))
    
    await db.commit()
    return ok(data=_asset_dict(asset), msg="Created successfully")


@router.put("/{toe_id}/assets/{asset_id}")
async def update_asset(
    toe_id: str,
    asset_id: str,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Edit an asset."""
    await _get_user_toe(toe_id, current_user, db)
    result = await db.exec(
        select(TOEAsset).where(
            TOEAsset.id == asset_id,
            TOEAsset.toe_id == toe_id,
            TOEAsset.deleted_at.is_(None),
        )
    )
    asset = result.first()
    if not asset:
        raise NotFoundError("Asset not found")

    updatable = ["name", "description", "asset_type", "importance", "importance_reason"]
    for field in updatable:
        if field in payload:
            setattr(asset, field, payload[field])
    asset.updated_at = utcnow()
    db.add(asset)
    
    # Handle threat associations
    if "asset_ids" in payload:
        threat_ids = payload.get("asset_ids") or []
        # Delete old associations
        await db.exec(
            delete(ThreatAssetLink).where(ThreatAssetLink.asset_id == asset_id)
        )
        # Add new associations
        for threat_id in threat_ids:
            threat_result = await db.exec(
                select(Threat).where(Threat.id == threat_id, Threat.toe_id == toe_id)
            )
            if threat_result.first():
                db.add(ThreatAssetLink(threat_id=threat_id, asset_id=asset.id))
    
    await db.commit()
    return ok(data=_asset_dict(asset), msg="Updated successfully")


@router.delete("/{toe_id}/assets/{asset_id}")
async def delete_asset(
    toe_id: str,
    asset_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Soft-delete an asset."""
    await _get_user_toe(toe_id, current_user, db)
    result = await db.exec(
        select(TOEAsset).where(
            TOEAsset.id == asset_id,
            TOEAsset.toe_id == toe_id,
            TOEAsset.deleted_at.is_(None),
        )
    )
    asset = result.first()
    if not asset:
        raise NotFoundError("Asset not found")
    asset.soft_delete()
    db.add(asset)
    return ok(msg="Deleted successfully")


# ═══════════════════════════════════════════════════════════════
# B2-4  AI suggest assets
# ═══════════════════════════════════════════════════════════════

@router.post("/{toe_id}/assets/ai-suggest")
async def ai_suggest_assets(
    toe_id: str,
    language: str = "en",
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Suggest an asset list with AI (synchronous call) while passing existing assets to avoid duplicates."""
    toe = await _get_user_toe(toe_id, current_user, db)

    ai = await get_ai_service(db, current_user.id)
    if not ai:
        raise HTTPException(400, "Please configure and verify an AI model first")

    # Read existing assets
    result = await db.exec(
        select(TOEAsset).where(TOEAsset.toe_id == toe_id, TOEAsset.deleted_at.is_(None))
    )
    existing = [a.name for a in result.all()]

    # Generate prompt based on language
    prompt = f"""Please suggest important assets for the following TOE that need protection.

TOE Name: {toe.name}
TOE Type: {toe.toe_type}
Brief Intro: {toe.brief_intro or 'N/A'}
Description: {toe.description or 'N/A'}
Boundary: {toe.boundary or 'N/A'}
Operational Environment: {toe.operational_env or 'N/A'}

Existing Assets (avoid duplicates): {', '.join(existing) if existing else 'None'}

Please return the asset list in JSON format:
{{
  "assets": [
    {{
      "name": "Asset Name",
      "description": "Asset Description",
      "asset_type": "data|function|privacy|config|other",
      "importance": An integer from 1-5,
      "importance_reason": "Reason for importance level"
    }}
  ]
}}

Requirements:
- Suggest 5-10 assets
- Cover data, function, privacy, configuration and other types
- Rate importance based on asset criticality to TOE security
- Do not duplicate existing assets
- Output in English"""

    result = await ai.chat_json(prompt)
    return ok(data=result.get("assets", result))


# ═══════════════════════════════════════════════════════════════
# B2-5  File upload
# ═══════════════════════════════════════════════════════════════

# MIME type mapping
MIME_TO_TYPE = {
    "application/pdf": "document",
    "application/msword": "document",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "document",
    "text/plain": "document",
    "text/markdown": "document",
    "image/png": "image",
    "image/jpeg": "image",
    "image/gif": "image",
    "image/webp": "image",
    "video/mp4": "video",
    "video/quicktime": "video",
    "video/x-msvideo": "video",
}


@router.post("/{toe_id}/files")
async def upload_file(
    toe_id: str,
    file: UploadFile = File(...),
    file_category: str = Form("manual"),  # manual|st_pp|other
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Upload a file, validate MIME type and size, and enqueue an async processing task."""
    if file_category not in ("manual", "st_pp", "other"):
        file_category = "manual"
    toe = await _get_user_toe(toe_id, current_user, db)

    safe_original = sanitize_filename(file.filename)
    # Extension allow-list check runs before MIME inference so that a
    # malicious `.html` masquerading as `application/pdf` is rejected.
    ext = get_safe_extension(safe_original, ALLOWED_EXT_TOE_FILE)

    # Validate MIME type — fall back by extension, same as ST upload.
    mime = file.content_type or "application/octet-stream"
    file_type = MIME_TO_TYPE.get(mime, "other")
    if file_type == "other":
        if ext in (".pdf", ".doc", ".docx", ".txt", ".md", ".html", ".htm"):
            file_type = "document"
        elif ext in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
            file_type = "image"
        elif ext in (".mp4", ".mov", ".avi"):
            file_type = "video"

    # Read file content and validate size
    content = await file.read()
    validate_size(len(content))

    # Save file — only user.id and toe_id (both UUIDs) become path segments.
    store_dir = os.path.join(
        settings.storage_path, current_user.id, toe_id,
        {"document": "docs", "image": "images", "video": "videos"}.get(file_type, "others")
    )
    os.makedirs(store_dir, exist_ok=True)

    stored_name = f"{uuid.uuid4().hex}{ext}"
    file_path = os.path.join(store_dir, stored_name)

    import aiofiles
    async with aiofiles.open(file_path, "wb") as f:
        await f.write(content)

    # Create TOE_FILE record
    toe_file = TOEFile(
        toe_id=toe_id,
        filename=stored_name,
        original_filename=safe_original,
        file_path=file_path,
        file_type=file_type,
        file_category=file_category,
        mime_type=mime,
        file_size=len(content),
        process_status="pending",
    )
    db.add(toe_file)
    await db.flush()

    # Create async processing task
    task = AITask(
        user_id=current_user.id,
        toe_id=toe_id,
        task_type="file_process",
        status="pending",
        progress_message="Queued for processing...",
    )
    db.add(task)
    await db.flush()

    # Enqueue ARQ task
    from app.worker.worker import arq_pool
    if arq_pool:
        await arq_pool.enqueue_job("file_process_task", toe_file.id, task.id)

    return ok(data={
        "id": toe_file.id,
        "original_filename": toe_file.original_filename,
        "file_type": toe_file.file_type,
        "file_size": toe_file.file_size,
        "process_status": toe_file.process_status,
        "task_id": task.id,
    }, msg="Upload successful")


@router.get("/{toe_id}/files")
async def list_files(
    toe_id: str,
    file_category: Optional[str] = Query(None, description="Filter by file category: manual|st_pp|other"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get the TOE file list with optional category filtering."""
    await _get_user_toe(toe_id, current_user, db, writable=False)
    stmt = select(TOEFile).where(
        TOEFile.toe_id == toe_id,
        TOEFile.deleted_at.is_(None),
    )
    if file_category:
        stmt = stmt.where(TOEFile.file_category == file_category)
    stmt = stmt.order_by(TOEFile.created_at.desc())
    result = await db.exec(stmt)
    return ok(data=[_file_dict(f) for f in result.all()])


@router.delete("/{toe_id}/files/{file_id}")
async def delete_file(
    toe_id: str,
    file_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Soft-delete a file."""
    await _get_user_toe(toe_id, current_user, db)
    result = await db.exec(
        select(TOEFile).where(
            TOEFile.id == file_id,
            TOEFile.toe_id == toe_id,
            TOEFile.deleted_at.is_(None),
        )
    )
    f = result.first()
    if not f:
        raise NotFoundError("File not found")
    f.soft_delete()
    db.add(f)
    return ok(msg="Deleted successfully")


# ═══════════════════════════════════════════════════════════════
# B2-7  File processing status query
# ═══════════════════════════════════════════════════════════════

@router.get("/{toe_id}/files/{file_id}/status")
async def get_file_status(
    toe_id: str,
    file_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Query the file processing status."""
    await _get_user_toe(toe_id, current_user, db, writable=False)
    result = await db.exec(
        select(TOEFile).where(
            TOEFile.id == file_id,
            TOEFile.toe_id == toe_id,
            TOEFile.deleted_at.is_(None),
        )
    )
    f = result.first()
    if not f:
        raise NotFoundError("File not found")

    return ok(data={
        "id": f.id,
        "process_status": f.process_status,
        "process_error": f.process_error,
    })


# ═══════════════════════════════════════════════════════════════
# ── Helper: Extract most relevant passages from document text for target field ──────────────────────────

_ST_PP_KEYWORDS = [
    # TOE Overview/Description
    r"toe\s+overview", r"toe\s+description", r"toe\s+summary", r"toe\s+identification",
    r"product\s+description", r"product\s+type", r"product\s+overview",
    r"intended\s+use", r"intended\s+uses", r"operational\s+use", r"operational\s+uses",
    r"security\s+target\s+introduction", r"st\s+introduction", r"introduction",
    
    # Security Features/Functions
    r"security\s+objective", r"security\s+objectives", r"security\s+function",
    r"security\s+functions", r"\bsfr\b", r"sfrs", r"security\s+functional\s+req",
    r"security\s+feature", r"security\s+features", r"it\s+security\s+functions",
    r"security\s+properties", r"security\s+policy", r"security\s+policies",
    
    # Non-TOE/Environment
    r"non[-\s]toe", r"it\s+environment", r"operational\s+environment", 
    r"required.*(?:software|hardware|firmware)", r"platform\s+req", r"platform\s+requirements",
    r"dependencies", r"required\s+components", r"external\s+requirements",
    r"infrastructure", r"runtime\s+environment",
    
    # Scope/Boundary
    r"logical\s+(?:scope|boundary)", r"physical\s+scope", r"physical\s+boundary",
    r"toe\s+boundary", r"scope\s+of\s+(?:the\s+)?toe", r"toe\s+scope", r"boundaries",
    r"toe\s+security\s+function", r"security\s+boundary", r"protection\s+boundary",
]

_MANUAL_KEYWORDS = [
    # Interfaces
    r"hardware\s+interface", r"software\s+interface", r"external\s+interface",
    r"physical\s+interface", r"network\s+interface", r"management\s+interface",
    r"user\s+interface", r"\bapi\b", r"rest\s+api", r"web\s+api",
    r"\bcli\b", r"command\s+line", r"\bport\b", r"ports",
    r"connector", r"connectors", r"protocol", r"protocols",
    r"communication", r"interface", r"interfaces",
    
    # Usage/Scenarios
    r"intended\s+use", r"use\s+case", r"use\s+cases", 
    r"operational\s+scenario", r"operational\s+scenarios", r"typical\s+use",
    r"system\s+overview", r"usage", r"usages", r"deployment",
    r"installation", r"operation", r"operations", r"typical\s+deployment",
]

# Per-field keywords for targeted section extraction (async AI analysis)
_FIELD_KEYWORDS_ST_PP = {
    "toe_type": [
        r"toe\s+type", r"product\s+type", r"toe\s+overview", r"toe\s+identification",
        r"product\s+description", r"product\s+category", r"type\s+of\s+product",
    ],
    "toe_usage": [
        r"intended\s+use", r"operational\s+use", r"toe\s+usage", r"use\s+case",
        r"deployment", r"typical\s+use", r"usage\s+scenario",
    ],
    "major_security_features": [
        r"security\s+feature", r"security\s+function", r"it\s+security",
        r"security\s+objective", r"security\s+propert", r"security\s+capabilit",
    ],
    "required_non_toe_hw_sw_fw": [
        r"non.?toe", r"it\s+environment", r"operational\s+environment",
        r"required.*(?:hardware|software|firmware)", r"platform\s+req",
        r"external\s+req", r"dependencies", r"runtime\s+environment",
    ],
    "toe_description": [
        r"toe\s+description", r"product\s+description", r"toe\s+overview",
        r"toe\s+summary", r"system\s+description", r"general\s+description",
    ],
    "logical_scope": [
        r"logical\s+(?:scope|boundary)", r"toe\s+boundary", r"security\s+boundary",
        r"physical\s+(?:scope|boundary)", r"scope\s+of", r"boundaries",
    ],
}

_FIELD_SECTION_PATTERNS_ST_PP = {
    "toe_type": [
        r"\btoe\s+type\b",
        r"\bproduct\s+type\b",
    ],
    "toe_usage": [
        r"\btoe\s+usage\b",
        r"\bintended\s+use\b",
        r"\busage\s+and\s+major\s+security\s+features\b",
        r"\busage\s+and\s+major\s+security\s+features\s+of\s+a\s+toe\b",
    ],
    "major_security_features": [
        r"\btoe\s+major\s+security\s+features\b",
        r"\bmajor\s+security\s+features\b",
        r"\bsecurity\s+features\s+of\s+a\s+toe\b",
    ],
    "required_non_toe_hw_sw_fw": [
        r"\brequired\s+non-?toe\s+hardware/software/firmware\b",
        r"\brequired\s+non-?toe\s+hardware\b",
        r"\bnon-?toe\s+hardware/software/firmware\b",
        r"\boperational\s+environment\b",
    ],
    "toe_description": [
        r"\btoe\s+description\b",
        r"\btoe\s+overview\b",
        r"\bproduct\s+description\b",
    ],
    "logical_scope": [
        r"\blogical\s+scope\b",
        r"\blogical\s+boundary\b",
        r"\bsecurity\s+boundary\b",
        r"\btoe\s+boundary\b",
    ],
}

_FIELD_KEYWORDS_MANUAL = {
    "toe_usage": [
        r"intended\s+use", r"use\s+case", r"operational\s+scenario", r"typical\s+use",
        r"system\s+overview", r"usage", r"deployment", r"installation",
    ],
    "hw_interfaces": [
        r"hardware\s+interface", r"physical\s+interface", r"connector",
        r"\bport\b", r"ports", r"network\s+interface", r"physical\s+connection",
    ],
    "sw_interfaces": [
        r"software\s+interface", r"\bapi\b", r"rest\s+api", r"web\s+api",
        r"\bcli\b", r"command\s+line", r"management\s+interface", r"protocol",
    ],
}


def _normalize_section_line(line: str) -> str:
    return re.sub(r"\s+", " ", (line or "").strip())


def _is_toc_like_line(line: str) -> bool:
    normalized = _normalize_section_line(line)
    if not normalized:
        return False
    if re.search(r"\.{4,}\s*\d+\s*$", normalized):
        return True
    if re.search(r"^\d+(?:\.\d+)+\s+.+\s+\d+\s*$", normalized):
        return True
    if normalized.count(".") >= 8 and normalized[-1:].isdigit():
        return True
    return False


def _parse_heading_line(line: str) -> tuple[Optional[str], str]:
    normalized = _normalize_section_line(line)
    match = re.match(r"^(\d+(?:\.\d+)*)\s+(.+)$", normalized)
    if not match:
        return None, normalized
    return match.group(1), match.group(2).strip()


def _is_probable_heading(line: str) -> bool:
    number, title = _parse_heading_line(line)
    if not title:
        return False
    if _is_toc_like_line(line):
        return False
    if number:
        return len(title) <= 160 and not title.endswith((":", ";", "."))
    return len(title) <= 80 and title == title.title()


def _find_section_end_line(lines: list[str], start_index: int) -> int:
    current_number, _ = _parse_heading_line(lines[start_index])
    current_level = len(current_number.split(".")) if current_number else None

    for idx in range(start_index + 1, len(lines)):
        if not _is_probable_heading(lines[idx]):
            continue
        next_number, _ = _parse_heading_line(lines[idx])
        if current_level is None:
            return idx
        if not next_number:
            return idx
        next_level = len(next_number.split("."))
        if next_level <= current_level:
            return idx
    return len(lines)


def _score_section_candidate(lines: list[str], start_index: int, end_index: int) -> int:
    score = 0
    window = lines[start_index + 1:min(end_index, start_index + 40)]
    substantive_lines = 0
    toc_like_lines = 0

    for raw_line in window:
        normalized = _normalize_section_line(raw_line)
        if not normalized:
            continue
        if _is_toc_like_line(normalized):
            toc_like_lines += 1
            continue
        if len(normalized) >= 60:
            substantive_lines += 2
            continue
        if normalized.startswith(("-", "*", "•", "")):
            substantive_lines += 1
            continue
        if re.search(r"\bshall\b|\bmust\b|\bprovides\b|\bmaintains\b|\bprotects\b", normalized, re.IGNORECASE):
            substantive_lines += 1
            continue
        if re.search(r"\s{2,}\S", raw_line) and len(normalized) >= 20:
            substantive_lines += 1

    score += substantive_lines * 5
    score -= toc_like_lines * 12

    number, _ = _parse_heading_line(lines[start_index])
    if number:
        score += 15
        if len(number.split(".")) >= 3:
            score += 5
    if start_index < 120:
        score -= 10
    return score


def _extract_labeled_value_block(full_text: str, labels: list[str], max_chars: int = 1200) -> Optional[str]:
    lines = full_text.splitlines()
    for idx, raw_line in enumerate(lines):
        line = _normalize_section_line(raw_line)
        if _is_toc_like_line(line):
            continue
        for label in labels:
            pattern = re.compile(rf"^{re.escape(label)}\s*[:：-]?\s*(.+)$", re.IGNORECASE)
            match = pattern.match(line)
            if match and match.group(1).strip():
                snippet_lines = [line]
                for follow in lines[idx + 1:idx + 6]:
                    normalized = _normalize_section_line(follow)
                    if not normalized or _is_probable_heading(normalized):
                        break
                    snippet_lines.append(normalized)
                snippet = "\n".join(snippet_lines).strip()
                return snippet[:max_chars]
    return None


def _extract_st_pp_field_context(full_text: str, section_key: str, max_chars: int = 15000) -> str:
    if section_key == "toe_type":
        labeled_value = _extract_labeled_value_block(full_text, ["TOE Type", "Product Type"])
        if labeled_value:
            return labeled_value

    lines = full_text.splitlines()
    heading_patterns = _FIELD_SECTION_PATTERNS_ST_PP.get(section_key, [])
    candidates: list[tuple[int, int, int]] = []

    for idx, raw_line in enumerate(lines):
        normalized = _normalize_section_line(raw_line)
        if not normalized or _is_toc_like_line(normalized):
            continue
        _, title = _parse_heading_line(normalized)
        line_to_match = title or normalized
        if not any(re.search(pattern, line_to_match, re.IGNORECASE) for pattern in heading_patterns):
            continue
        end_index = _find_section_end_line(lines, idx)
        score = _score_section_candidate(lines, idx, end_index)
        if score <= 0:
            continue
        candidates.append((score, idx, end_index))

    if candidates:
        candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
        _, start_index, end_index = candidates[0]
        section_text = "\n".join(lines[start_index:end_index]).strip()
        if section_text:
            return section_text[:max_chars]

    return _extract_section_by_keywords(full_text, _FIELD_KEYWORDS_ST_PP.get(section_key, []), max_chars=max_chars)


def _extract_section_by_keywords(full_text: str, keywords: list[str], max_chars: int = 15000) -> str:
    """Extract portions of text relevant to specific keywords.
    
    Strategy:
    1. If text fits within max_chars, return as-is
    2. Find lines matching keywords, take context windows around them
    3. Fallback: return first max_chars of text
    """
    if len(full_text) <= max_chars:
        return full_text

    lines = full_text.split("\n")
    matched_indices: list[int] = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or len(stripped) > 300:
            continue
        low = stripped.lower()
        for kw in keywords:
            if re.search(kw, low):
                matched_indices.append(i)
                break

    if not matched_indices:
        return full_text[:max_chars]

    # For each match: 5 lines before + 200 lines after to capture full section
    selected: set[int] = set()
    for idx in matched_indices:
        start = max(0, idx - 5)
        end = min(len(lines), idx + 200)
        selected.update(range(start, end))

    sorted_idx = sorted(selected)
    parts: list[str] = []
    total = 0
    prev = -2
    for idx in sorted_idx:
        line = lines[idx]
        if total + len(line) + 1 > max_chars:
            break
        if idx != prev + 1 and parts and idx - prev > 5:
            parts.append("[...]\n")
        parts.append(line + "\n")
        total += len(line) + 1
        prev = idx

    result = "".join(parts).rstrip()
    return result if result.strip() else full_text[:max_chars]


def _extract_relevant_sections(full_text: str, focus: str, max_chars: int = 100000) -> str:
    """
    Extract the paragraphs most relevant to the target field from the full document text.
    Strategy:
    1. If the document is within max_chars, return the full text.
    2. If it is longer, locate key sections by keyword matching and extract them together.
    3. Fallback: if no keywords are found, return the first max_chars characters.
    """
    if len(full_text) <= max_chars:
        return full_text

    keywords = _ST_PP_KEYWORDS if focus == "st_pp" else _MANUAL_KEYWORDS
    lines = full_text.split("\n")

    # Find line indices where keywords matched
    matched_indices: list[int] = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or len(stripped) > 300:  # Very long lines may be data, skip
            continue
        low = stripped.lower()
        for kw in keywords:
            if re.search(kw, low):
                matched_indices.append(i)
                break

    if not matched_indices:
        # No keywords matched → return first max_chars
        return full_text[:max_chars]

    # Improved strategy: for each matched line, take 5 lines before + 300 lines after (more complete paragraphs)
    # This captures more context even in large documents
    selected: set[int] = set()
    for idx in matched_indices:
        start = max(0, idx - 5)
        end = min(len(lines), idx + 300)
        selected.update(range(start, end))

    sorted_idx = sorted(selected)

    # Reorganize in document order, build final text
    parts: list[str] = []
    total = 0
    prev = -2
    
    for idx in sorted_idx:
        line = lines[idx]
        if total + len(line) + 1 > max_chars:
            break
        
        # Check for jumps (insert separator if more than 5 lines gap)
        if idx != prev + 1 and parts and idx - prev > 5:
            parts.append("[...] (content omitted)\n")
        
        parts.append(line + "\n")
        total += len(line) + 1
        prev = idx

    # Direct concatenation, each line ends with \n
    result = "".join(parts).rstrip()
    
    return result if result.strip() else full_text[:max_chars]


# AI analyze document and backfill TOE fields
# ═══════════════════════════════════════════════════════════════

@router.post("/{toe_id}/ai-analyze-docs")
async def ai_analyze_docs(
    toe_id: str,
    payload: dict = {},
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Analyze a single TOE document and extract relevant fields based on document type.
    payload:
        file_id  (str)     — single file ID to analyze (must already be in ready state)
        focus    (str)     — "st_pp" | "manual", determines which fields to extract
        language (str)     — "en" | "zh", AI prompt language (default "en")
    """
    toe = await _get_user_toe(toe_id, current_user, db)

    ai = await get_ai_service(db, current_user.id)
    if not ai:
        raise HTTPException(400, "Please configure and verify an AI model first")

    file_id = (payload or {}).get("file_id")
    focus   = (payload or {}).get("focus", "manual")  # "st_pp" | "manual"
    language = (payload or {}).get("language", "en")  # "en" | "zh"

    if not file_id:
        raise HTTPException(400, "file_id is required")

    result_q = await db.exec(
        select(TOEFile).where(
            TOEFile.id == file_id,
            TOEFile.toe_id == toe_id,
            TOEFile.deleted_at.is_(None),
        )
    )
    f = result_q.first()
    if not f:
        raise HTTPException(404, "File not found")
    if f.process_status != "ready":
        raise HTTPException(400, "The file is still being processed. Try again later")
    if not f.extracted_text_path or not os.path.exists(f.extracted_text_path):
        raise HTTPException(400, "Document content is unavailable. Confirm the file was processed successfully")

    with open(f.extracted_text_path, "r", encoding="utf-8", errors="ignore") as fp:
        full_text = fp.read()

    doc_text = _extract_relevant_sections(full_text, focus)

    # ── Choose focused prompt by document type and language ──────────────────────────
    if focus == "st_pp":
        prompt = f"""You are a CC (Common Criteria) security evaluation expert analyzing a Security Target (ST) or Protection Profile (PP) document.

TOE: {toe.name} ({toe.toe_type})
Document: {f.original_filename}

IMPORTANT: Only extract content that is explicitly present in the text below. Do NOT generate, infer, or fabricate content that is not written in the document. If a section's content is not visible in the provided text, return null for that field.
IMPORTANT: Preserve the original document wording and language exactly. Do NOT translate, rewrite, or paraphrase any extracted text.

--- DOCUMENT TEXT (relevant sections) ---
{doc_text}
--- END ---

Extract the following four items by copying the actual text from the document above:
1. TOE usage / intended use scenario (look for "TOE Overview", "Intended Use", "TOE Description", "Product Description")
2. Major security features (look for "Security Objectives", "Security Functions", "SFRs", "IT Security Functions")
3. Required non-TOE hardware/software/firmware (look for "Non-TOE", "IT Environment", "Operational Environment", "Required Components")
4. Logical scope / logical boundary (look for "Logical Scope", "Logical Boundary", "TOE Boundary", "Security Boundary")

Return JSON with only the fields whose content you found in the text:
{{
  "toe_usage": "<full text of usage/intended use section, or null>",
  "major_security_features": "<full text of security functions/objectives section, or null>",
  "required_non_toe_hw_sw_fw": "<full text of non-TOE components section, or null>",
  "logical_scope": "<full text of logical scope/boundary section, or null>"
}}"""
        max_tok = 4000
    else:  # manual / spec
        prompt = f"""You are a CC (Common Criteria) security evaluation expert analyzing a TOE user manual or functional specification.

TOE: {toe.name} ({toe.toe_type})
Document: {f.original_filename}

IMPORTANT: Only extract content that is explicitly present in the text below. Do NOT generate, infer, or fabricate content that is not written in the document. If a section's content is not visible in the provided text, return null for that field.
IMPORTANT: Preserve the original document wording and language exactly. Do NOT translate, rewrite, or paraphrase any extracted text.

--- DOCUMENT TEXT (relevant sections) ---
{doc_text}
--- END ---

Extract the following items by copying the actual text from the document above:
1. Typical usage / operational scenarios (look for "Usage", "Intended Use", "Use Case", "System Overview")
2. Hardware interfaces (look for "Hardware Interface", "Physical Interface", "Ports", "Connectors")
3. Software interfaces (look for "Software Interface", "API", "CLI", "Management Interface", "Protocols")

Return JSON with only the fields whose content you found in the text:
{{
  "toe_usage": "<full text of usage/scenario section, or null>",
  "hw_interfaces": "<full text of hardware interfaces section, or null>",
  "sw_interfaces": "<full text of software interfaces section, or null>"
}}"""
        max_tok = 3000

    try:
        extracted = await ai.chat_json(prompt, max_tokens=max_tok)
    except Exception as e:
        logger.warning("AI call failed: %s", e)
        raise HTTPException(400, "AI call failed: unable to get a response from the model")

    # Remove null / empty values before returning so frontend knows what was found
    cleaned = {k: v for k, v in extracted.items() if v}
    return ok(data=cleaned)


@router.post("/{toe_id}/ai-analyze-docs-async")
async def ai_analyze_docs_async(
    toe_id: str,
    payload: dict = {},
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
        Analyze TOE documents asynchronously and return a task ID immediately while PDF parsing and AI extraction run in the background.
        The frontend polls /api/tasks/{task_id} for progress and results.

    payload:
            file_id  (str)  - ID of the file to analyze
            focus    (str)  - "st_pp" | "manual"
            language (str)  - "en" | "zh" (default: "en")

    Response:
      { "task_id": "..." }
    """
    from app.models.ai_task import AITask
    from app.core.database import AsyncSessionLocal
    import asyncio
    
    toe = await _get_user_toe(toe_id, current_user, db)
    file_id = (payload or {}).get("file_id")
    focus = (payload or {}).get("focus", "manual")
    language = (payload or {}).get("language", "en")
    
    if not file_id:
        raise HTTPException(400, "file_id is required")
    
    # Verify file exists
    result_q = await db.exec(
        select(TOEFile).where(
            TOEFile.id == file_id,
            TOEFile.toe_id == toe_id,
            TOEFile.deleted_at.is_(None),
        )
    )
    if not result_q.first():
        raise HTTPException(404, "File not found")
    
    # Create async task record
    task = AITask(
        user_id=current_user.id,
        toe_id=toe_id,
        task_type="ai_analyze_doc",
        status="pending",
        progress_message="Waiting to start...",
    )
    db.add(task)
    await db.commit()
    
    # Start processing in background (don't wait)
    asyncio.create_task(
        _analyze_doc_background(task.id, toe_id, file_id, focus, current_user.id, language)
    )
    
    msg = "Task created, please poll for progress"
    return ok(data={"task_id": task.id}, msg=msg)


async def _analyze_doc_background(task_id: str, toe_id: str, file_id: str, focus: str, user_id: str, language: str = "en"):
    """
    Background task for document analysis.

    ST/PP documents are extracted section by section with one AI request per section.
    Manual documents extract three fields directly.
    """
    from app.core.database import AsyncSessionLocal
    from app.models.ai_task import AITask
    from app.models.toe import TOE
    from app.services.ai_service import get_ai_service
    from datetime import timezone
    
    try:
        async with AsyncSessionLocal() as db:
            # Update task status: processing
            task_result = await db.exec(select(AITask).where(AITask.id == task_id))
            task = task_result.first()
            if task:
                task.status = "running"
                task.progress_message = "Reading file..."
                db.add(task)
                await db.commit()
            
            # Read file
            file_result = await db.exec(
                select(TOEFile).where(TOEFile.id == file_id, TOEFile.deleted_at.is_(None))
            )
            f = file_result.first()
            if not f:
                raise Exception("File not found")
            
            if f.process_status != "ready":
                raise Exception("The file is still being processed")
            
            if not f.extracted_text_path or not os.path.exists(f.extracted_text_path):
                raise Exception("Document content is unavailable")
            
            with open(f.extracted_text_path, "r", encoding="utf-8", errors="ignore") as fp:
                full_text = fp.read()
            
            # Read TOE information
            toe_result = await db.exec(select(TOE).where(TOE.id == toe_id, TOE.deleted_at.is_(None)))
            toe = toe_result.first()
            
            ai = await get_ai_service(db, user_id)
            if not ai:
                raise Exception("AI model is not configured")
            
            # Choose extraction strategy based on document type
            if focus == "st_pp":
                result = await _extract_st_pp_sections(full_text, toe, f, ai, task_id, language)
            else:  # manual
                result = await _extract_manual_sections(full_text, toe, f, ai, task_id, language)
            
            # Save results and complete task
            async with AsyncSessionLocal() as db:
                task_result = await db.exec(select(AITask).where(AITask.id == task_id))
                task = task_result.first()
                if task:
                    task.status = "done"
                    section_count = len([v for v in result.values() if v])
                    task.progress_message = f"Successfully extracted {section_count} sections"
                    task.result_summary = json.dumps(result, ensure_ascii=False)
                    task.finished_at = datetime.now(timezone.utc).replace(tzinfo=None)
                    db.add(task)
                    await db.commit()
    
    except Exception as e:
        # Mark task as failed
        try:
            async with AsyncSessionLocal() as db:
                task_result = await db.exec(select(AITask).where(AITask.id == task_id))
                task = task_result.first()
                if task:
                    task.status = "failed"
                    task.error_message = str(e)
                    task.finished_at = datetime.now(timezone.utc).replace(tzinfo=None)
                    db.add(task)
                    await db.commit()
        except Exception:
            pass


async def _extract_st_pp_sections(full_text: str, toe, file, ai, task_id: str, language: str = "en") -> dict:
    """
    Extract ST/PP document fields section by section.
    Fields are extracted in order: TOE Type, TOE Usage, Major Security Features,
    Required Non-TOE HW/SW/FW, TOE Description, and Logical Scope.

    Optimization: only pass the document segments relevant to each field through keyword location,
    rather than sending the entire document, which can exceed 79K characters.
    """
    from app.core.database import AsyncSessionLocal
    from app.models.ai_task import AITask
    from sqlmodel import select
    
    sections = [
        ("toe_type", "TOE Type - product type and technical characteristics"),
        ("toe_usage", "TOE Usage - intended use scenarios and deployment"),
        ("major_security_features", "Major Security Features - key security functions"),
        ("required_non_toe_hw_sw_fw", "Required Non-TOE Hardware/Software/Firmware - external dependencies"),
        ("toe_description", "TOE Description - detailed product description"),
        ("logical_scope", "Logical Scope - logical security boundary"),
    ]
    
    result = {}
    
    for idx, (section_key, section_name) in enumerate(sections, 1):
        # Update progress
        async with AsyncSessionLocal() as db:
            task_result = await db.exec(select(AITask).where(AITask.id == task_id))
            task = task_result.first()
            if task:
                task.progress_message = f"Extracting ({idx}/{len(sections)}): {section_name}..."
                db.add(task)
                await db.commit()
        
            # ST/PP prefer cut by real section titles, fallback to keyword window on failure.
            doc_section = _extract_st_pp_field_context(full_text, section_key, max_chars=15000)
        
        prompt = f"""You are a CC (Common Criteria) security evaluation expert analyzing a Security Target (ST) or Protection Profile (PP) document.

TOE: {toe.name} ({toe.toe_type})
Document: {file.original_filename}
Section to extract: {section_name}

CRITICAL INSTRUCTIONS:
1. Extract the COMPLETE content related to "{section_name}" from the text below
2. Do NOT summarize - copy the EXACT text as it appears in the document
3. Preserve the original document language exactly. Do NOT translate, rewrite, or paraphrase the extracted text
4. If the section spans multiple paragraphs or subsections, include ALL of them
5. Only return the extracted content, remove section numbers/headers if they are just formatting
6. If you CANNOT find content related to "{section_name}", return null

--- DOCUMENT TEXT (relevant sections) ---
{doc_section}
--- END ---

Return as JSON (return null if not found, otherwise return the full extracted text):
{{"content": "<extracted text or null>"}}"""
        
        try:
            extracted = await ai.chat_json(prompt, max_tokens=8000)
            content = extracted.get("content") if extracted else None
            if content and str(content).strip() and str(content).lower() != "null":
                result[section_key] = str(content).strip()
            else:
                result[section_key] = None
        except Exception as e:
            result[section_key] = f"[Extraction failed: {str(e)[:100]}]"
    
    return result


async def _extract_manual_sections(full_text: str, toe, file, ai, task_id: str, language: str = "en") -> dict:
    """
    Extract three fields from Manual/Specification documents.

    Optimization: only pass the document segments relevant to each field instead of the entire document.
    """
    from app.core.database import AsyncSessionLocal
    from app.models.ai_task import AITask
    from sqlmodel import select
    
    sections = [
        ("toe_usage", "TOE Usage - typical use scenarios and deployment"),
        ("hw_interfaces", "Hardware Interfaces - hardware interfaces and connectors"),
        ("sw_interfaces", "Software Interfaces - software interfaces, APIs and management"),
    ]
    
    result = {}
    
    for idx, (section_key, section_name) in enumerate(sections, 1):
        # Update progress
        async with AsyncSessionLocal() as db:
            task_result = await db.exec(select(AITask).where(AITask.id == task_id))
            task = task_result.first()
            if task:
                task.progress_message = f"Extracting ({idx}/{len(sections)}): {section_name}..."
                db.add(task)
                await db.commit()
        
        # For each field, extract only relevant passages from document
        field_keywords = _FIELD_KEYWORDS_MANUAL.get(section_key, [])
        doc_section = _extract_section_by_keywords(full_text, field_keywords, max_chars=15000)
        
        prompt = f"""You are a CC security evaluation expert analyzing a TOE user manual or specification.

TOE: {toe.name} ({toe.toe_type})
Document: {file.original_filename}
Section to extract: {section_name}

CRITICAL INSTRUCTIONS:
1. Extract the COMPLETE content related to "{section_name}" from the text below
2. Do NOT summarize - copy the EXACT text as it appears in the document
3. Preserve the original document language exactly. Do NOT translate, rewrite, or paraphrase the extracted text
4. Include all relevant information, details, and subsections
5. Only return the extracted content
6. If this section is not found, return null

--- DOCUMENT TEXT (relevant sections) ---
{doc_section}
--- END ---

Return as JSON:
{{"content": "<extracted text or null>"}}"""
        
        try:
            extracted = await ai.chat_json(prompt, max_tokens=6000)
            content = extracted.get("content") if extracted else None
            if content and str(content).strip() and str(content).lower() != "null":
                result[section_key] = str(content).strip()
            else:
                result[section_key] = None
        except Exception as e:
            result[section_key] = f"[Extraction failed: {str(e)[:100]}]"
    
    return result


# ═══════════════════════════════════════════════════════════════
# AI consolidate Overview field (dedup and merge)
# ═══════════════════════════════════════════════════════════════

@router.post("/{toe_id}/ai-consolidate")
async def ai_consolidate(
    toe_id: str,
    payload: dict | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Consolidate accumulated overview field content with AI.
    Repeated or duplicated fragments are merged into one coherent professional paragraph.
    Only non-empty fields are processed.
    """
    language = ((payload or {}).get("language") or "en").lower()
    if language not in ("zh", "en"):
        language = "en"

    toe = await _get_user_toe(toe_id, current_user, db)

    ai = await get_ai_service(db, current_user.id)
    if not ai:
        raise HTTPException(400, "Please configure and verify an AI model first")

    FIELDS = [
        "toe_type_desc",
        "toe_usage",
        "major_security_features",
        "required_non_toe_hw_sw_fw",
        "physical_scope",
        "logical_scope",
        "hw_interfaces",
        "sw_interfaces",
    ]

    # Collect non-empty fields
    to_consolidate = {}
    for field in FIELDS:
        val = getattr(toe, field, None)
        if val and val.strip():
            to_consolidate[field] = val.strip()

    if not to_consolidate:
        raise HTTPException(400, "All overview fields are empty, nothing to consolidate")

    fields_json = "\n".join(
        f'  "{k}": {repr(v[:2000])}' for k, v in to_consolidate.items()
    )

    output_language = "Chinese" if language == "zh" else "English"
    prompt = f"""You are a CC (Common Criteria) security evaluation expert.

The following TOE overview fields may contain duplicate or repetitive content accumulated from multiple sources (separated by "---").
For EACH field: merge all content into a single coherent, non-redundant paragraph in professional {output_language}.
Preserve all unique facts. Remove exact duplicates and redundant restatements.
Keep the result concise but complete — do not lose important details.
Return ONLY the fields that were provided. Do not add new fields.

TOE: {toe.name} ({toe.toe_type})

Current field values:
{{
{fields_json}
}}

Return JSON with the same field keys, each containing the consolidated text:"""

    try:
        result = await ai.chat_json(prompt, max_tokens=3000)
    except Exception as e:
        logger.warning("AI call failed: %s", e)
        raise HTTPException(400, "AI call failed: unable to get a response from the model")

    # Only return fields that were sent and have a non-empty result
    consolidated = {k: v for k, v in result.items() if k in to_consolidate and v and str(v).strip()}
    return ok(data=consolidated)


@router.post("/{toe_id}/ai-consolidate-fields")
async def ai_consolidate_fields(
    toe_id: str,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Consolidate selected overview fields with AI.
    payload should include 'fields': ['field1', 'field2', ...]
    """
    toe = await _get_user_toe(toe_id, current_user, db)
    language = (payload.get("language") or "en").lower()
    if language not in ("zh", "en"):
        language = "en"

    ai = await get_ai_service(db, current_user.id)
    if not ai:
        raise HTTPException(400, "Please configure and verify an AI model first")

    ALL_FIELDS = [
        "toe_type_desc",
        "toe_usage",
        "major_security_features",
        "required_non_toe_hw_sw_fw",
        "physical_scope",
        "logical_scope",
        "hw_interfaces",
        "sw_interfaces",
    ]

    # Get list of fields to process
    fields_to_process = payload.get("fields", [])
    if not fields_to_process:
        raise HTTPException(400, "You must specify at least one field to consolidate")

    # Validate field legitimacy
    fields_to_process = [f for f in fields_to_process if f in ALL_FIELDS]
    if not fields_to_process:
        raise HTTPException(400, "All specified fields are invalid")

    # Collect values of fields to process
    to_consolidate = {}
    for field in fields_to_process:
        val = getattr(toe, field, None)
        if val and str(val).strip():
            to_consolidate[field] = str(val).strip()

    if not to_consolidate:
        raise HTTPException(400, "All specified fields are empty, nothing to consolidate")

    fields_json = "\n".join(
        f'  "{k}": {repr(v[:2000])}' for k, v in to_consolidate.items()
    )

    output_language = "Chinese" if language == "zh" else "English"
    prompt = f"""You are a CC (Common Criteria) security evaluation expert.

The following TOE overview fields may contain duplicate or repetitive content accumulated from multiple sources (separated by "---").
For EACH field: merge all content into a single coherent, non-redundant paragraph in professional {output_language}.
Preserve all unique facts. Remove exact duplicates and redundant restatements.
Keep the result concise but complete — do not lose important details.
Return ONLY the fields that were provided. Do not add new fields.

TOE: {toe.name} ({toe.toe_type})

Current field values:
{{
{fields_json}
}}

Return JSON with the same field keys, each containing the consolidated text:"""

    try:
        result = await ai.chat_json(prompt, max_tokens=3000)
    except Exception as e:
        logger.warning("AI call failed: %s", e)
        raise HTTPException(400, "AI call failed: unable to get a response from the model")

    # Only return fields that were sent and have a non-empty result
    consolidated = {k: v for k, v in result.items() if k in to_consolidate and v and str(v).strip()}
    return ok(data=consolidated)


# ═══════════════════════════════════════════════════════════════
# B2-8  Cascading delete sub-data statistics (for frontend deletion confirmation popup)
# ═══════════════════════════════════════════════════════════════

@router.get("/{toe_id}/cascade-counts")
async def get_cascade_counts(
    toe_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get the number of each child data type that would be cascaded when deleting a TOE."""
    await _get_user_toe(toe_id, current_user, db, writable=False)

    asset_cnt = (await db.exec(
        select(func.count()).where(TOEAsset.toe_id == toe_id, TOEAsset.deleted_at.is_(None))
    )).one()
    file_cnt = (await db.exec(
        select(func.count()).where(TOEFile.toe_id == toe_id, TOEFile.deleted_at.is_(None))
    )).one()

    # Models in subsequent phases may not be ready, safe to get
    counts = {"asset_count": asset_cnt, "file_count": file_cnt}

    for model_path, key in [
        ("app.models.threat:Threat", "threat_count"),
        ("app.models.threat:Assumption", "assumption_count"),
        ("app.models.threat:OSP", "osp_count"),
        ("app.models.security:SecurityObjective", "objective_count"),
        ("app.models.security:SFR", "sfr_count"),
        ("app.models.test_case:TestCase", "test_count"),
        ("app.models.risk:RiskAssessment", "risk_count"),
    ]:
        try:
            module_name, class_name = model_path.split(":")
            import importlib
            mod = importlib.import_module(module_name)
            Model = getattr(mod, class_name)
            cnt = (await db.exec(
                select(func.count()).where(Model.toe_id == toe_id, Model.deleted_at.is_(None))
            )).one()
            counts[key] = cnt
        except Exception:
            counts[key] = 0

    return ok(data=counts)


# ═══════════════════════════════════════════════════════════════
# B2-X  TOE package export / import
# ═══════════════════════════════════════════════════════════════

def _json_ready(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _json_ready(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_ready(v) for v in value]
    return value


def _serialize_model(instance, exclude: Optional[set[str]] = None) -> dict:
    data = instance.model_dump()
    for key in exclude or set():
        data.pop(key, None)
    return _json_ready(data)


def _annotation_contains_type(annotation, target_type) -> bool:
    if annotation is target_type:
        return True
    origin = get_origin(annotation)
    if origin is None:
        return False
    return any(
        _annotation_contains_type(arg, target_type)
        for arg in get_args(annotation)
        if arg is not type(None)
    )


def _coerce_datetime_value(value: str):
    normalized = value.strip()
    if not normalized:
        return value
    try:
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError:
        return value
    if parsed.tzinfo is not None:
        return parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _coerce_date_value(value: str):
    normalized = value.strip()
    if not normalized:
        return value
    try:
        return date.fromisoformat(normalized)
    except ValueError:
        return value


def _filter_model_payload(model_cls, payload: dict, exclude: Optional[set[str]] = None) -> dict:
    allowed = set(model_cls.model_fields.keys()) - (exclude or set())
    filtered = {}
    for key in allowed:
        if key not in payload:
            continue
        value = payload[key]
        annotation = model_cls.model_fields[key].annotation
        if isinstance(value, str):
            if _annotation_contains_type(annotation, datetime):
                value = _coerce_datetime_value(value)
            elif _annotation_contains_type(annotation, date):
                value = _coerce_date_value(value)
        filtered[key] = value
    return filtered


def _safe_export_filename(name: Optional[str]) -> str:
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", (name or "toe_export").strip()).strip("._")
    if not safe_name:
        safe_name = "toe_export"
    return f"{safe_name}.toe"


def _store_dir_for_file(user_id: str, toe_id: str, file_type: str) -> str:
    return os.path.join(
        settings.storage_path,
        user_id,
        toe_id,
        {"document": "docs", "image": "images", "video": "videos"}.get(file_type, "others"),
    )


async def _resolve_imported_toe_name(name: Optional[str], user_id: str, db: AsyncSession) -> str:
    base_name = (name or "Imported TOE").strip() or "Imported TOE"
    candidate = base_name
    index = 1
    while True:
        result = await db.exec(
            select(TOE.id).where(
                TOE.user_id == user_id,
                TOE.deleted_at.is_(None),
                TOE.name == candidate,
            )
        )
        if not result.first():
            return candidate
        suffix = "Imported" if index == 1 else f"Imported {index}"
        candidate = f"{base_name} ({suffix})"
        index += 1


async def _resolve_import_sfr_library_id(imported_sfr: dict, db: AsyncSession) -> Optional[str]:
    sfr_code = (imported_sfr.get("sfr_id") or "").strip().upper()
    if not sfr_code:
        return None
    result = await db.exec(select(SFRLibrary).where(col(SFRLibrary.sfr_component) == sfr_code))
    library = result.first()
    return library.id if library else None


def _cleanup_imported_paths(paths: list[str]):
    for path in reversed(paths):
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception:
            pass


@router.get("/{toe_id}/package/export")
async def export_toe_package(
    toe_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    toe = await _get_user_toe(toe_id, current_user, db, writable=False)

    assets = (await db.exec(select(TOEAsset).where(TOEAsset.toe_id == toe_id, TOEAsset.deleted_at.is_(None)))).all()
    assumptions = (await db.exec(select(Assumption).where(Assumption.toe_id == toe_id, Assumption.deleted_at.is_(None)))).all()
    osps = (await db.exec(select(OSP).where(OSP.toe_id == toe_id, OSP.deleted_at.is_(None)))).all()
    threats = (await db.exec(select(Threat).where(Threat.toe_id == toe_id, Threat.deleted_at.is_(None)))).all()
    objectives = (await db.exec(select(SecurityObjective).where(SecurityObjective.toe_id == toe_id, SecurityObjective.deleted_at.is_(None)))).all()
    sfrs = (await db.exec(select(SFR).where(SFR.toe_id == toe_id, SFR.deleted_at.is_(None)))).all()
    tests = (await db.exec(select(TestCase).where(TestCase.toe_id == toe_id, TestCase.deleted_at.is_(None)))).all()
    risks = (await db.exec(select(RiskAssessment).where(RiskAssessment.toe_id == toe_id, RiskAssessment.deleted_at.is_(None)))).all()
    files = (await db.exec(select(TOEFile).where(TOEFile.toe_id == toe_id, TOEFile.deleted_at.is_(None)))).all()

    threat_ids = [item.id for item in threats]
    assumption_ids = [item.id for item in assumptions]
    osp_ids = [item.id for item in osps]
    objective_ids = [item.id for item in objectives]

    threat_asset_links = []
    if threat_ids:
        threat_asset_links = (await db.exec(select(ThreatAssetLink).where(ThreatAssetLink.threat_id.in_(threat_ids)))).all()

    threat_objectives = []
    if threat_ids:
        threat_objectives = (await db.exec(select(ThreatObjective).where(ThreatObjective.threat_id.in_(threat_ids)))).all()

    assumption_objectives = []
    if assumption_ids:
        assumption_objectives = (await db.exec(select(AssumptionObjective).where(AssumptionObjective.assumption_id.in_(assumption_ids)))).all()

    osp_objectives = []
    if osp_ids:
        osp_objectives = (await db.exec(select(OSPObjective).where(OSPObjective.osp_id.in_(osp_ids)))).all()

    objective_sfrs = []
    if objective_ids:
        objective_sfrs = (await db.exec(select(ObjectiveSFR).where(ObjectiveSFR.objective_id.in_(objective_ids)))).all()

    manifest = {
        "package_version": PACKAGE_VERSION,
        "exported_at": datetime.utcnow().isoformat(),
        "toe": _serialize_model(toe, {"user_id", "deleted_at"}),
        "assets": [_serialize_model(item, {"toe_id", "deleted_at"}) for item in assets],
        "assumptions": [_serialize_model(item, {"toe_id", "deleted_at"}) for item in assumptions],
        "osps": [_serialize_model(item, {"toe_id", "deleted_at"}) for item in osps],
        "threats": [_serialize_model(item, {"toe_id", "deleted_at"}) for item in threats],
        "threat_asset_links": [_serialize_model(item) for item in threat_asset_links],
        "security_objectives": [_serialize_model(item, {"toe_id", "deleted_at"}) for item in objectives],
        "threat_objectives": [_serialize_model(item) for item in threat_objectives],
        "assumption_objectives": [_serialize_model(item) for item in assumption_objectives],
        "osp_objectives": [_serialize_model(item) for item in osp_objectives],
        "sfrs": [_serialize_model(item, {"toe_id", "deleted_at"}) for item in sfrs],
        "objective_sfrs": [_serialize_model(item) for item in objective_sfrs],
        "test_cases": [_serialize_model(item, {"toe_id", "deleted_at"}) for item in tests],
        "risk_assessments": [_serialize_model(item, {"toe_id", "deleted_at"}) for item in risks],
        "files": [],
    }

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for toe_file in files:
            file_payload = _serialize_model(toe_file, {"toe_id", "deleted_at", "file_path", "extracted_text_path"})
            file_payload["archive_path"] = None
            file_payload["extracted_text_archive_path"] = None

            if toe_file.file_path and os.path.exists(toe_file.file_path):
                archive_path = f"files/{toe_file.id}/{toe_file.filename}"
                archive.write(toe_file.file_path, archive_path)
                file_payload["archive_path"] = archive_path

            if toe_file.extracted_text_path and os.path.exists(toe_file.extracted_text_path):
                extracted_name = os.path.basename(toe_file.extracted_text_path)
                extracted_archive_path = f"files/{toe_file.id}/{extracted_name}"
                archive.write(toe_file.extracted_text_path, extracted_archive_path)
                file_payload["extracted_text_archive_path"] = extracted_archive_path

            manifest["files"].append(file_payload)

        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))

    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{_safe_export_filename(toe.name)}"'},
    )


@router.post("/package/import")
async def import_toe_package(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    content = await file.read()
    if len(content) > settings.upload_max_bytes * 2:
        raise HTTPException(400, f"Import package exceeds the size limit ({settings.max_upload_size_mb * 2}MB)")

    buffer = io.BytesIO(content)
    if not zipfile.is_zipfile(buffer):
        raise HTTPException(400, "Invalid TOE import package")

    created_paths: list[str] = []
    summary = {
        "assets": 0,
        "assumptions": 0,
        "osps": 0,
        "threats": 0,
        "security_objectives": 0,
        "sfrs": 0,
        "test_cases": 0,
        "risk_assessments": 0,
        "files": 0,
    }

    try:
        buffer.seek(0)
        with zipfile.ZipFile(buffer) as archive:
            if "manifest.json" not in archive.namelist():
                raise HTTPException(400, "The import package is missing manifest.json")

            manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
            toe_source = manifest.get("toe") or {}
            toe_payload = _filter_model_payload(TOE, toe_source, {"id", "user_id", "deleted_at"})
            toe_payload["name"] = await _resolve_imported_toe_name(toe_payload.get("name"), current_user.id, db)
            toe_payload["toe_type"] = (toe_payload.get("toe_type") or "").strip()
            if toe_payload["toe_type"] not in ("hardware", "software", "system"):
                raise HTTPException(400, "The TOE type in the import package is invalid")
            toe_payload["id"] = new_uuid()
            toe_payload["user_id"] = current_user.id

            imported_toe = TOE(**toe_payload)
            db.add(imported_toe)
            await db.flush()

            asset_id_map: dict[str, str] = {}
            assumption_id_map: dict[str, str] = {}
            osp_id_map: dict[str, str] = {}
            threat_id_map: dict[str, str] = {}
            objective_id_map: dict[str, str] = {}
            sfr_id_map: dict[str, str] = {}

            for record in manifest.get("assets", []):
                payload = _filter_model_payload(TOEAsset, record, {"id", "toe_id", "deleted_at"})
                asset = TOEAsset(id=new_uuid(), toe_id=imported_toe.id, **payload)
                db.add(asset)
                if record.get("id"):
                    asset_id_map[record["id"]] = asset.id
                summary["assets"] += 1

            for record in manifest.get("assumptions", []):
                payload = _filter_model_payload(Assumption, record, {"id", "toe_id", "deleted_at"})
                assumption = Assumption(id=new_uuid(), toe_id=imported_toe.id, **payload)
                db.add(assumption)
                if record.get("id"):
                    assumption_id_map[record["id"]] = assumption.id
                summary["assumptions"] += 1

            for record in manifest.get("osps", []):
                payload = _filter_model_payload(OSP, record, {"id", "toe_id", "deleted_at"})
                osp = OSP(id=new_uuid(), toe_id=imported_toe.id, **payload)
                db.add(osp)
                if record.get("id"):
                    osp_id_map[record["id"]] = osp.id
                summary["osps"] += 1

            for record in manifest.get("threats", []):
                payload = _filter_model_payload(Threat, record, {"id", "toe_id", "deleted_at"})
                threat = Threat(id=new_uuid(), toe_id=imported_toe.id, **payload)
                db.add(threat)
                if record.get("id"):
                    threat_id_map[record["id"]] = threat.id
                summary["threats"] += 1

            for record in manifest.get("security_objectives", []):
                payload = _filter_model_payload(SecurityObjective, record, {"id", "toe_id", "deleted_at"})
                objective = SecurityObjective(id=new_uuid(), toe_id=imported_toe.id, **payload)
                db.add(objective)
                if record.get("id"):
                    objective_id_map[record["id"]] = objective.id
                summary["security_objectives"] += 1

            for record in manifest.get("sfrs", []):
                payload = _filter_model_payload(SFR, record, {"id", "toe_id", "deleted_at", "sfr_library_id"})
                payload["sfr_library_id"] = await _resolve_import_sfr_library_id(record, db)
                sfr = SFR(id=new_uuid(), toe_id=imported_toe.id, **payload)
                db.add(sfr)
                if record.get("id"):
                    sfr_id_map[record["id"]] = sfr.id
                summary["sfrs"] += 1

            await db.flush()

            for record in manifest.get("threat_asset_links", []):
                threat_id = threat_id_map.get(record.get("threat_id"))
                asset_id = asset_id_map.get(record.get("asset_id"))
                if threat_id and asset_id:
                    db.add(ThreatAssetLink(threat_id=threat_id, asset_id=asset_id))

            for record in manifest.get("threat_objectives", []):
                threat_id = threat_id_map.get(record.get("threat_id"))
                objective_id = objective_id_map.get(record.get("objective_id"))
                if threat_id and objective_id:
                    db.add(ThreatObjective(threat_id=threat_id, objective_id=objective_id))

            for record in manifest.get("assumption_objectives", []):
                assumption_id = assumption_id_map.get(record.get("assumption_id"))
                objective_id = objective_id_map.get(record.get("objective_id"))
                if assumption_id and objective_id:
                    db.add(AssumptionObjective(assumption_id=assumption_id, objective_id=objective_id))

            for record in manifest.get("osp_objectives", []):
                osp_id = osp_id_map.get(record.get("osp_id"))
                objective_id = objective_id_map.get(record.get("objective_id"))
                if osp_id and objective_id:
                    db.add(OSPObjective(osp_id=osp_id, objective_id=objective_id))

            for record in manifest.get("objective_sfrs", []):
                objective_id = objective_id_map.get(record.get("objective_id"))
                sfr_id = sfr_id_map.get(record.get("sfr_id"))
                if objective_id and sfr_id:
                    payload = _filter_model_payload(ObjectiveSFR, record, {"objective_id", "sfr_id"})
                    db.add(ObjectiveSFR(objective_id=objective_id, sfr_id=sfr_id, **payload))

            for record in manifest.get("test_cases", []):
                primary_sfr_id = sfr_id_map.get(record.get("primary_sfr_id"))
                if not primary_sfr_id:
                    continue

                payload = _filter_model_payload(TestCase, record, {"id", "toe_id", "primary_sfr_id", "related_sfr_ids", "deleted_at"})
                related_ids = None
                raw_related_ids = record.get("related_sfr_ids")
                if raw_related_ids:
                    try:
                        parsed_related_ids = json.loads(raw_related_ids) if isinstance(raw_related_ids, str) else list(raw_related_ids)
                    except Exception:
                        parsed_related_ids = []
                    remapped_related_ids = [sfr_id_map[item] for item in parsed_related_ids if item in sfr_id_map]
                    related_ids = json.dumps(remapped_related_ids, ensure_ascii=False) if remapped_related_ids else None
                if related_ids is not None:
                    payload["related_sfr_ids"] = related_ids

                test_case = TestCase(id=new_uuid(), toe_id=imported_toe.id, primary_sfr_id=primary_sfr_id, **payload)
                db.add(test_case)
                summary["test_cases"] += 1

            for record in manifest.get("risk_assessments", []):
                threat_id = threat_id_map.get(record.get("threat_id"))
                if not threat_id:
                    continue
                payload = _filter_model_payload(RiskAssessment, record, {"id", "toe_id", "threat_id", "deleted_at"})
                risk = RiskAssessment(id=new_uuid(), toe_id=imported_toe.id, threat_id=threat_id, **payload)
                db.add(risk)
                summary["risk_assessments"] += 1

            for record in manifest.get("files", []):
                archive_path = record.get("archive_path")
                if not archive_path or archive_path not in archive.namelist():
                    continue

                file_type = (record.get("file_type") or "other").strip() or "other"
                file_bytes = archive.read(archive_path)
                original_filename = record.get("original_filename") or record.get("filename") or "imported-file"
                ext = os.path.splitext(original_filename)[1] or os.path.splitext(record.get("filename") or "")[1]
                stored_name = f"{uuid.uuid4().hex}{ext}"
                store_dir = _store_dir_for_file(current_user.id, imported_toe.id, file_type)
                os.makedirs(store_dir, exist_ok=True)
                file_path = os.path.join(store_dir, stored_name)

                with open(file_path, "wb") as handle:
                    handle.write(file_bytes)
                created_paths.append(file_path)

                extracted_text_path = None
                extracted_archive_path = record.get("extracted_text_archive_path")
                if extracted_archive_path and extracted_archive_path in archive.namelist():
                    text_filename = os.path.splitext(stored_name)[0] + ".extracted.txt"
                    extracted_text_path = os.path.join(store_dir, text_filename)
                    with open(extracted_text_path, "wb") as handle:
                        handle.write(archive.read(extracted_archive_path))
                    created_paths.append(extracted_text_path)

                payload = _filter_model_payload(TOEFile, record, {"id", "toe_id", "deleted_at", "filename", "file_path", "extracted_text_path", "file_size", "archive_path", "extracted_text_archive_path"})
                toe_file = TOEFile(
                    id=new_uuid(),
                    toe_id=imported_toe.id,
                    filename=stored_name,
                    file_path=file_path,
                    extracted_text_path=extracted_text_path,
                    file_size=len(file_bytes),
                    **payload,
                )
                db.add(toe_file)
                summary["files"] += 1

        return ok(data={"id": imported_toe.id, "name": imported_toe.name, "summary": summary}, msg="Import successful")
    except HTTPException:
        _cleanup_imported_paths(created_paths)
        raise
    except zipfile.BadZipFile:
        _cleanup_imported_paths(created_paths)
        raise HTTPException(400, "Invalid TOE import package")
    except Exception as exc:
        _cleanup_imported_paths(created_paths)
        raise HTTPException(400, f"Import failed: {str(exc)}")


# ═══════════════════════════════════════════════════════════════
# Serialization helpers
# ═══════════════════════════════════════════════════════════════

def _toe_dict(t: TOE) -> dict:
    return {
        "id": t.id,
        "name": t.name,
        "toe_type": t.toe_type,
        "version": t.version,
        "brief_intro": t.brief_intro,
        "toe_type_desc": t.toe_type_desc,
        "toe_usage": t.toe_usage,
        "major_security_features": t.major_security_features,
        "required_non_toe_hw_sw_fw": t.required_non_toe_hw_sw_fw,
        "physical_scope": t.physical_scope,
        "logical_scope": t.logical_scope,
        "hw_interfaces": t.hw_interfaces,
        "sw_interfaces": t.sw_interfaces,
        "ai_generated_at": t.ai_generated_at.isoformat() if t.ai_generated_at else None,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
    }


def _asset_dict(a: TOEAsset) -> dict:
    return {
        "id": a.id,
        "toe_id": a.toe_id,
        "name": a.name,
        "description": a.description,
        "asset_type": a.asset_type,
        "importance": a.importance,
        "importance_reason": a.importance_reason,
        "ai_generated": a.ai_generated,
        "weak_coverage_ignored": a.weak_coverage_ignored,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


def _file_dict(f: TOEFile) -> dict:
    return {
        "id": f.id,
        "toe_id": f.toe_id,
        "original_filename": f.original_filename,
        "file_type": f.file_type,
        "file_category": f.file_category,
        "mime_type": f.mime_type,
        "file_size": f.file_size,
        "process_status": f.process_status,
        "process_error": f.process_error,
        "created_at": f.created_at.isoformat() if f.created_at else None,
    }


# ═══════════════════════════════════════════════════════════════
# B2-X  AI Translation
# ═══════════════════════════════════════════════════════════════

@router.post("/ai/translate-to-english")
async def translate_to_english(
    content: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Translate non-English content to English using AI, keeping existing English text unchanged"""
    ai = await get_ai_service(db, current_user.id)
    if not ai:
        raise HTTPException(400, "AI model not configured")

    # Filter non-empty values
    to_translate = {k: v for k, v in content.items() if v and isinstance(v, str) and v.strip()}
    if not to_translate:
        return ok(data={})

    # Prepare content for translation with instruction to preserve English
    content_str = "\n".join([f"{k}: {v}" for k, v in to_translate.items()])

    prompt = f"""You are a translator. Translate the following content to English.
IMPORTANT RULES:
1. Only translate non-English (especially Chinese) text
2. Keep any existing English text unchanged
3. Preserve the structure and formatting
4. If text is already in English, return it as-is
5. For mixed Chinese-English text, translate only the Chinese parts
6. Return ONLY valid JSON with the same keys as input

Original content:
{content_str}

Return ONLY valid JSON like:
{{"key1": "translated value1", "key2": "translated value2"}}
"""

    try:
        result = await ai.chat_json(prompt, max_tokens=2000)
        # Ensure result contains translations for all input keys
        translated = {}
        for key in to_translate.keys():
            translated[key] = result.get(key, to_translate[key])
        return ok(data=translated)
    except Exception as e:
        raise HTTPException(400, f"Translation failed: {str(e)}")
