"""
Phase 4: Security function management routes
- SecurityObjective CRUD + AI generation + review
- Threat/Assumption/OSP ↔ Objective many-to-many mapping
- SFR library browsing (read-only)
- TOE SFR instance CRUD + AI matching
- Objective ↔ SFR mapping management
"""
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from sqlmodel import select
from app.core.database import AsyncSessionLocal
from app.core.database import get_db
from app.core.auth import get_current_user, get_current_admin
from app.core.toe_permissions import get_accessible_toe
from app.core.config import settings
from app.core.response import ok, validate_batch_ids
from app.models.user import User
from app.models.toe import TOE
from app.models.security import (
    SecurityObjective, SFR, SFRLibrary,
    ThreatObjective, AssumptionObjective, OSPObjective, ObjectiveSFR,
)
from app.models.threat import Threat, Assumption, OSP
from app.models.test_case import TestCase
from app.models.ai_task import AITask
from app.services.ai_service import get_ai_service
from pydantic import BaseModel
from datetime import datetime, timezone
from app.models.base import new_uuid
import asyncio
import json
import os
import tempfile
import csv
import io
import re

router = APIRouter(prefix="/api", tags=["Security Management"])

_SFR_CLASS_NAME_DEFAULTS = {
    "FAU": "Security Audit",
    "FCO": "Communication",
    "FCS": "Cryptographic Support",
    "FDP": "User Data Protection",
    "FIA": "Identification and Authentication",
    "FMT": "Security Management",
    "FPR": "Privacy",
    "FPT": "Protection of the TSF",
    "FRU": "Resource Utilisation",
    "FTA": "TOE Access",
    "FTP": "Trusted Path/Channels",
}

_SFR_DEPENDENCY_ID_RE = re.compile(r"\b[A-Z]{3}_[A-Z0-9]+(?:\.[A-Z0-9]+)+\b", re.IGNORECASE)
_SFR_DEPENDENCY_TOKEN_RE = re.compile(r"\[|\]|\(|\)|\bOR\b|[\n,;；，]+|\b[A-Z]{3}_[A-Z0-9]+(?:\.[A-Z0-9]+)+\b", re.IGNORECASE)


# ══════════════════════════════════════════════
#  Helper
# ══════════════════════════════════════════════

async def _get_toe(toe_id: str, user: User, db, writable: bool = True) -> TOE:
    return await get_accessible_toe(toe_id, user, db, writable=writable)


async def _get_objective(objective_id: str, toe_id: str, db) -> SecurityObjective:
    res = await db.exec(
        select(SecurityObjective).where(
            SecurityObjective.id == objective_id,
            SecurityObjective.toe_id == toe_id,
            SecurityObjective.deleted_at.is_(None),
        )
    )
    obj = res.first()
    if not obj:
        raise HTTPException(404, "Security objective not found")
    return obj


async def _get_sfr(sfr_id: str, toe_id: str, db) -> SFR:
    res = await db.exec(
        select(SFR).where(
            SFR.id == sfr_id,
            SFR.toe_id == toe_id,
            SFR.deleted_at.is_(None),
        )
    )
    sfr = res.first()
    if not sfr:
        raise HTTPException(404, "SFR not found")
    return sfr


def _build_metric(key: str, covered: int, total: int) -> dict:
    covered = max(0, covered)
    total = max(0, total)
    if total == 0:
        percent = 100
        status = "not_applicable"
    else:
        percent = int(round((covered / total) * 100))
        if percent >= 85:
            status = "good"
        elif percent >= 60:
            status = "attention"
        else:
            status = "weak"
    return {
        "key": key,
        "covered": covered,
        "total": total,
        "percent": percent,
        "status": status,
    }


def _weighted_score(metrics: List[dict]) -> int:
    applicable = [item["percent"] for item in metrics if item["status"] != "not_applicable"]
    if not applicable:
        return 100
    return int(round(sum(applicable) / len(applicable)))


def _build_finding(key: str, severity: str, items: List[dict]) -> dict:
    visible = items[:8]
    return {
        "key": key,
        "severity": severity,
        "count": len(items),
        "items": visible,
        "overflow": max(0, len(items) - len(visible)),
    }


def _compact_text(value: Optional[str], limit: int = 100) -> str:
    if not value:
        return "-"
    compact = " ".join(value.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3] + "..."


def _normalize_optional_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_sfr_component(value: str) -> str:
    return (value or "").strip().upper()


def _derive_sfr_hierarchy(sfr_component: str) -> tuple[str, str]:
    normalized = _normalize_sfr_component(sfr_component)
    family = normalized.split(".", 1)[0] if "." in normalized else normalized
    sfr_class = family.split("_", 1)[0] if "_" in family else family
    return sfr_class, family


async def _get_sfr_library_item(library_id: str, db) -> SFRLibrary:
    res = await db.exec(select(SFRLibrary).where(SFRLibrary.id == library_id))
    item = res.first()
    if not item:
        raise HTTPException(404, "SFR library item not found")
    return item


async def _build_sfr_library_name_maps(db) -> tuple[dict[str, str], dict[str, str]]:
    rows = (await db.exec(select(SFRLibrary))).all()
    class_name_map: dict[str, str] = dict(_SFR_CLASS_NAME_DEFAULTS)
    family_name_map: dict[str, str] = {}
    for item in rows:
        if item.sfr_class and item.sfr_class_name and item.sfr_class not in class_name_map:
            class_name_map[item.sfr_class] = item.sfr_class_name
        if item.sfr_family and item.sfr_family_name and item.sfr_family not in family_name_map:
            family_name_map[item.sfr_family] = item.sfr_family_name
    return class_name_map, family_name_map


class SFRLibraryUpdate(BaseModel):
    sfr_component: str
    sfr_component_name: Optional[str] = None
    description: Optional[str] = None
    dependencies: Optional[str] = None


@router.post("/sfr-library")
async def create_sfr_library_item(
    body: SFRLibraryUpdate,
    current_user: User = Depends(get_current_admin),
    db=Depends(get_db),
):
    _ = current_user
    normalized_component = _normalize_sfr_component(body.sfr_component)
    if not normalized_component:
        raise HTTPException(400, "SFR ID is required")

    duplicate = (await db.exec(
        select(SFRLibrary).where(SFRLibrary.sfr_component == normalized_component)
    )).first()
    if duplicate:
        raise HTTPException(400, f"SFR ID already exists: {normalized_component}")

    class_name_map, family_name_map = await _build_sfr_library_name_maps(db)
    sfr_class, sfr_family = _derive_sfr_hierarchy(normalized_component)

    item = SFRLibrary(
        sfr_component=normalized_component,
        sfr_component_name=_normalize_optional_text(body.sfr_component_name) or normalized_component,
        description=_normalize_optional_text(body.description),
        dependencies=_normalize_dependency_expression(body.dependencies),
        sfr_class=sfr_class,
        sfr_family=sfr_family,
        sfr_class_name=class_name_map.get(sfr_class) or sfr_class,
        sfr_family_name=family_name_map.get(sfr_family) or sfr_family,
    )

    db.add(item)
    await db.commit()
    await db.refresh(item)
    return ok(data=item)


class SFRLibraryBatchDeleteBody(BaseModel):
    ids: List[str]


class SFRLibraryImportError(BaseModel):
    row: int
    sfr_id: Optional[str] = None
    reason: str


def _parse_related_sfr_ids(value: Optional[str]) -> List[str]:
    if not value:
        return []
    try:
        import json
        parsed = json.loads(value)
    except Exception:
        return []
    if not isinstance(parsed, list):
        return []
    return [item for item in parsed if isinstance(item, str) and item]


def _normalize_sfr_source(value: Optional[str]) -> str:
    normalized = (value or "manual").strip().lower()
    if normalized in {"ai", "st_pp", "manual"}:
        return normalized
    if normalized in {"st/pp", "stpp", "st-pp"}:
        return "st_pp"
    if normalized in {"standard", "custom", "manual"}:
        return "manual"
    return "manual"


async def _get_sfr_library_by_component(sfr_id: str, db) -> Optional[SFRLibrary]:
    res = await db.exec(
        select(SFRLibrary).where(SFRLibrary.sfr_component == sfr_id.upper())
    )
    return res.first()

def _extract_dependency_groups(value: Optional[str]) -> List[List[str]]:
    text = _normalize_optional_text(value)
    if not text:
        return []
    tokens = [match.group(0) for match in _SFR_DEPENDENCY_TOKEN_RE.finditer(text.upper())]
    if not tokens:
        return []

    groups: list[list[str]] = []
    current_group: list[str] = []
    inside_brackets = False
    pending_or = False

    def flush_group() -> None:
        nonlocal current_group, pending_or
        if current_group:
            groups.append(current_group)
            current_group = []
        pending_or = False

    for token in tokens:
        if token in {"[", "("}:
            flush_group()
            inside_brackets = True
            continue
        if token in {"]", ")"}:
            flush_group()
            inside_brackets = False
            continue
        if token == "OR":
            pending_or = True
            continue
        if token in {",", ";", "；", "，", "\n", "\r\n"} or any(ch in token for ch in "\n,;；，"):
            if not inside_brackets:
                flush_group()
            continue
        if _SFR_DEPENDENCY_ID_RE.fullmatch(token):
            dependency_id = token.upper()
            if inside_brackets:
                if dependency_id not in current_group:
                    current_group.append(dependency_id)
                pending_or = False
                continue
            if not current_group:
                current_group = [dependency_id]
            elif pending_or:
                if dependency_id not in current_group:
                    current_group.append(dependency_id)
            else:
                flush_group()
                current_group = [dependency_id]
            pending_or = False

    flush_group()
    return groups


def _normalize_dependency_expression(value: Optional[str]) -> Optional[str]:
    groups = _extract_dependency_groups(value)
    if not groups:
        return None
    if len(groups) == 1:
        return f"({' OR '.join(groups[0])})" if len(groups[0]) > 1 else groups[0][0]
    formatted_groups = []
    for group in groups:
        if len(group) == 1:
            formatted_groups.append(group[0])
        else:
            formatted_groups.append(f"({' OR '.join(group)})")
    return " AND ".join(formatted_groups)


def _parse_dependency_groups(value: Optional[str]) -> List[List[str]]:
    return _extract_dependency_groups(value)


async def _build_dependency_warning(toe_id: str, dependency: Optional[str], db, current_sfr_db_id: Optional[str] = None) -> Optional[str]:
    dependency_groups = _parse_dependency_groups(dependency)
    if not dependency_groups:
        return None

    existing_sfrs = (await db.exec(
        select(SFR).where(
            SFR.toe_id == toe_id,
            SFR.deleted_at.is_(None),
        )
    )).all()
    existing_ids = {
        item.sfr_id.upper()
        for item in existing_sfrs
        if not current_sfr_db_id or item.id != current_sfr_db_id
    }

    if all(any(dep in existing_ids for dep in group) for group in dependency_groups):
        return None

    missing_groups: list[str] = []
    for group in dependency_groups:
        if any(dep in existing_ids for dep in group):
            continue
        if len(group) == 1:
            missing_groups.append(group[0])
        else:
            missing_groups.append(f"({' OR '.join(group)})")
    return f"Missing dependencies: {' AND '.join(missing_groups)}" if missing_groups else None


async def _resolve_sfr_library(sfr: SFR, db) -> Optional[SFRLibrary]:
    if sfr.sfr_library_id:
        return (await db.exec(select(SFRLibrary).where(SFRLibrary.id == sfr.sfr_library_id))).first()
    return await _get_sfr_library_by_component(sfr.sfr_id, db)


async def _refresh_sfr_dependency_state(toe_id: str, db) -> dict[str, int]:
    sfrs = (await db.exec(
        select(SFR).where(
            SFR.toe_id == toe_id,
            SFR.deleted_at.is_(None),
        )
    )).all()

    updated = 0
    for sfr in sfrs:
        lib = await _resolve_sfr_library(sfr, db)
        normalized_dependency = _normalize_dependency_expression(sfr.dependency or (lib.dependencies if lib else None))
        dependency_warning = await _build_dependency_warning(toe_id, normalized_dependency, db, sfr.id)

        changed = False
        if sfr.dependency != normalized_dependency:
            sfr.dependency = normalized_dependency
            changed = True
        if sfr.dependency_warning != dependency_warning:
            sfr.dependency_warning = dependency_warning
            changed = True

        if changed:
            db.add(sfr)
            updated += 1

    return {"checked": len(sfrs), "updated": updated}


def _resolve_sfr_display_fields(sfr: SFR, library: Optional[SFRLibrary]) -> dict:
    return {
        "sfr_name": sfr.sfr_name or (library.sfr_component_name if library else None),
        "sfr_detail": sfr.sfr_detail or (library.description if library else None),
        "dependency": _normalize_dependency_expression(sfr.dependency or (library.dependencies if library else None)),
    }


# ══════════════════════════════════════════════
#  F4-2: SecurityObjective CRUD
# ══════════════════════════════════════════════

class ObjectiveCreate(BaseModel):
    code: str
    obj_type: str = "O"
    description: Optional[str] = None
    rationale: Optional[str] = None


class ObjectiveUpdate(BaseModel):
    code: Optional[str] = None
    obj_type: Optional[str] = None
    description: Optional[str] = None
    rationale: Optional[str] = None


@router.get("/toes/{toe_id}/objectives")
async def list_objectives(
    toe_id: str,
    obj_type: Optional[str] = None,
    review_status: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    await get_accessible_toe(toe_id, current_user, db, writable=False)
    stmt = select(SecurityObjective).where(
        SecurityObjective.toe_id == toe_id,
        SecurityObjective.deleted_at.is_(None),
    )
    if obj_type:
        stmt = stmt.where(SecurityObjective.obj_type == obj_type)
    if review_status:
        stmt = stmt.where(SecurityObjective.review_status == review_status)
    stmt = stmt.order_by(SecurityObjective.code)
    res = await db.exec(stmt)
    return {"code": 0, "data": res.all()}


@router.post("/toes/{toe_id}/objectives/ai-suggest")
async def ai_suggest_objectives(
    toe_id: str,
    current_user: User = Depends(get_current_user), db=Depends(get_db),
):
    """Suggest security objectives for threats using AI."""
    await get_accessible_toe(toe_id, current_user, db, writable=True)
    # Temporarily return empty list, actual implementation requires AI service
    return {"code": 0, "data": []}


@router.post("/toes/{toe_id}/objectives/import-from-docs")
async def import_objectives_from_docs(
    toe_id: str,
    current_user: User = Depends(get_current_user), db=Depends(get_db),
):
    """Import security objectives and SFRs from ST/PP documents."""
    await get_accessible_toe(toe_id, current_user, db, writable=True)

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
        raise HTTPException(400, "No processed ST/PP documents are available for this TOE. Upload one and wait for processing to finish.")

    task = AITask(
        user_id=current_user.id,
        toe_id=toe_id,
        task_type="objective_import",
        status="pending",
        progress_message="objective_import.stage_1",
    )
    db.add(task)
    await db.flush()
    await db.commit()

    from app.worker.worker import arq_pool
    if arq_pool:
        await arq_pool.enqueue_job("objective_import_task", toe_id, task.id)
    else:
        from app.worker.tasks import objective_import_task
        asyncio.create_task(objective_import_task({}, toe_id, task.id))

    return {"code": 0, "data": {"task_id": task.id}}


@router.post("/toes/{toe_id}/objectives")
async def create_objective(
    toe_id: str,
    body: ObjectiveCreate,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    await get_accessible_toe(toe_id, current_user, db, writable=True)
    obj = SecurityObjective(
        toe_id=toe_id,
        code=body.code.strip().upper(),
        obj_type=body.obj_type,
        description=body.description,
        rationale=body.rationale,
        review_status="draft",
        ai_generated=False,
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return {"code": 0, "data": obj}


@router.put("/toes/{toe_id}/objectives/{objective_id}")
async def update_objective(
    toe_id: str,
    objective_id: str,
    body: ObjectiveUpdate,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    await get_accessible_toe(toe_id, current_user, db, writable=True)
    obj = await _get_objective(objective_id, toe_id, db)
    if body.code is not None:
        obj.code = body.code.strip().upper()
    if body.obj_type is not None:
        obj.obj_type = body.obj_type
    if body.description is not None:
        obj.description = body.description
    if body.rationale is not None:
        obj.rationale = body.rationale
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return {"code": 0, "data": obj}


@router.delete("/toes/{toe_id}/objectives/{objective_id}")
async def delete_objective(
    toe_id: str,
    objective_id: str,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    await _get_toe(toe_id, current_user, db, writable=True)
    obj = await _get_objective(objective_id, toe_id, db)
    obj.deleted_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.add(obj)
    await db.commit()
    return {"code": 0, "data": None}


@router.post("/toes/{toe_id}/objectives/{objective_id}/confirm")
async def confirm_objective(
    toe_id: str,
    objective_id: str,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    await _get_toe(toe_id, current_user, db, writable=True)
    obj = await _get_objective(objective_id, toe_id, db)
    obj.review_status = "confirmed"
    obj.reviewed_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.add(obj)
    await db.commit()
    return {"code": 0, "data": obj}


@router.post("/toes/{toe_id}/objectives/{objective_id}/reject")
async def reject_objective(
    toe_id: str,
    objective_id: str,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    await _get_toe(toe_id, current_user, db, writable=True)
    obj = await _get_objective(objective_id, toe_id, db)
    obj.review_status = "rejected"
    obj.reviewed_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.add(obj)
    await db.commit()
    return {"code": 0, "data": obj}


@router.post("/toes/{toe_id}/objectives/{objective_id}/revert")
async def revert_objective(
    toe_id: str,
    objective_id: str,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    await _get_toe(toe_id, current_user, db, writable=True)
    obj = await _get_objective(objective_id, toe_id, db)
    obj.review_status = "draft"
    obj.reviewed_at = None
    db.add(obj)
    await db.commit()
    return {"code": 0, "data": obj}


# ══════════════════════════════════════════════
#  F4-3: Source → Objective mapping
# ══════════════════════════════════════════════

class SourceMapBody(BaseModel):
    source_type: str   # threat | assumption | osp
    source_id: str


@router.get("/toes/{toe_id}/objectives/{objective_id}/sources")
async def list_objective_sources(
    toe_id: str,
    objective_id: str,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    await _get_toe(toe_id, current_user, db, writable=False)
    await _get_objective(objective_id, toe_id, db)

    threat_res = await db.exec(
        select(ThreatObjective).where(ThreatObjective.objective_id == objective_id)
    )
    threat_ids = [r.threat_id for r in threat_res.all()]
    if threat_ids:
        valid_threat_ids = set((await db.exec(
            select(Threat.id).where(
                Threat.id.in_(threat_ids),
                Threat.toe_id == toe_id,
                Threat.deleted_at.is_(None),
            )
        )).all())
        threat_ids = [item_id for item_id in threat_ids if item_id in valid_threat_ids]

    assumption_res = await db.exec(
        select(AssumptionObjective).where(AssumptionObjective.objective_id == objective_id)
    )
    assumption_ids = [r.assumption_id for r in assumption_res.all()]
    if assumption_ids:
        valid_assumption_ids = set((await db.exec(
            select(Assumption.id).where(
                Assumption.id.in_(assumption_ids),
                Assumption.toe_id == toe_id,
                Assumption.deleted_at.is_(None),
            )
        )).all())
        assumption_ids = [item_id for item_id in assumption_ids if item_id in valid_assumption_ids]

    osp_res = await db.exec(
        select(OSPObjective).where(OSPObjective.objective_id == objective_id)
    )
    osp_ids = [r.osp_id for r in osp_res.all()]
    if osp_ids:
        valid_osp_ids = set((await db.exec(
            select(OSP.id).where(
                OSP.id.in_(osp_ids),
                OSP.toe_id == toe_id,
                OSP.deleted_at.is_(None),
            )
        )).all())
        osp_ids = [item_id for item_id in osp_ids if item_id in valid_osp_ids]

    return {
        "code": 0,
        "data": {
            "threat_ids": threat_ids,
            "assumption_ids": assumption_ids,
            "osp_ids": osp_ids,
        },
    }


@router.post("/toes/{toe_id}/objectives/{objective_id}/map-source")
async def add_source_mapping(
    toe_id: str,
    objective_id: str,
    body: SourceMapBody,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    await _get_toe(toe_id, current_user, db)
    objective = await _get_objective(objective_id, toe_id, db)

    if body.source_type == "threat":
        res = await db.exec(
            select(ThreatObjective).where(
                ThreatObjective.threat_id == body.source_id,
                ThreatObjective.objective_id == objective_id,
            )
        )
        if not res.first():
            db.add(ThreatObjective(threat_id=body.source_id, objective_id=objective_id))
    elif body.source_type == "assumption":
        if objective.obj_type != "OE":
            raise HTTPException(400, "Assumptions can only be mapped to OE objectives")
        res = await db.exec(
            select(AssumptionObjective).where(
                AssumptionObjective.assumption_id == body.source_id,
                AssumptionObjective.objective_id == objective_id,
            )
        )
        if not res.first():
            db.add(AssumptionObjective(assumption_id=body.source_id, objective_id=objective_id))
    elif body.source_type == "osp":
        res = await db.exec(
            select(OSPObjective).where(
                OSPObjective.osp_id == body.source_id,
                OSPObjective.objective_id == objective_id,
            )
        )
        if not res.first():
            db.add(OSPObjective(osp_id=body.source_id, objective_id=objective_id))
    else:
        raise HTTPException(400, "source_type must be threat, assumption, or osp")

    await db.commit()
    return {"code": 0, "data": None}


@router.delete("/toes/{toe_id}/objectives/{objective_id}/map-source/{source_type}/{source_id}")
async def remove_source_mapping(
    toe_id: str,
    objective_id: str,
    source_type: str,
    source_id: str,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    await _get_toe(toe_id, current_user, db)

    if source_type == "threat":
        res = await db.exec(
            select(ThreatObjective).where(
                ThreatObjective.threat_id == source_id,
                ThreatObjective.objective_id == objective_id,
            )
        )
        row = res.first()
        if row:
            await db.delete(row)
    elif source_type == "assumption":
        res = await db.exec(
            select(AssumptionObjective).where(
                AssumptionObjective.assumption_id == source_id,
                AssumptionObjective.objective_id == objective_id,
            )
        )
        row = res.first()
        if row:
            await db.delete(row)
    elif source_type == "osp":
        res = await db.exec(
            select(OSPObjective).where(
                OSPObjective.osp_id == source_id,
                OSPObjective.objective_id == objective_id,
            )
        )
        row = res.first()
        if row:
            await db.delete(row)

    await db.commit()
    return {"code": 0, "data": None}


@router.get("/toes/{toe_id}/security/completeness-report")
async def get_security_completeness_report(
    toe_id: str,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    await _get_toe(toe_id, current_user, db, writable=False)

    threats = (await db.exec(
        select(Threat).where(
            Threat.toe_id == toe_id,
            Threat.deleted_at.is_(None),
        )
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
        ).order_by(SecurityObjective.code)
    )).all()
    sfrs = (await db.exec(
        select(SFR).where(
            SFR.toe_id == toe_id,
            SFR.deleted_at.is_(None),
        ).order_by(SFR.sfr_id)
    )).all()
    objective_ids = [item.id for item in objectives]
    sfr_ids = [item.id for item in sfrs]
    threat_ids = [item.id for item in threats]
    assumption_ids = [item.id for item in assumptions]
    osp_ids = [item.id for item in osps]

    objective_sfr_rows = (await db.exec(
        select(ObjectiveSFR).where(
            ObjectiveSFR.objective_id.in_(objective_ids),
            ObjectiveSFR.sfr_id.in_(sfr_ids),
        )
    )).all() if objective_ids and sfr_ids else []

    threat_objective_rows = (await db.exec(
        select(ThreatObjective).where(
            ThreatObjective.objective_id.in_(objective_ids),
            ThreatObjective.threat_id.in_(threat_ids),
        )
    )).all() if objective_ids and threat_ids else []
    assumption_objective_rows = (await db.exec(
        select(AssumptionObjective).where(
            AssumptionObjective.objective_id.in_(objective_ids),
            AssumptionObjective.assumption_id.in_(assumption_ids),
        )
    )).all() if objective_ids and assumption_ids else []
    osp_objective_rows = (await db.exec(
        select(OSPObjective).where(
            OSPObjective.objective_id.in_(objective_ids),
            OSPObjective.osp_id.in_(osp_ids),
        )
    )).all() if objective_ids and osp_ids else []

    mapped_objective_ids = {row.objective_id for row in objective_sfr_rows}
    mapped_sfr_ids = {row.sfr_id for row in objective_sfr_rows if row.sfr_id in sfr_ids}
    sfr_by_code = {item.sfr_id.upper(): item for item in sfrs}
    dependency_referrers_by_sfr_id: dict[str, list[dict]] = {}
    referenced_sfr_ids: set[str] = set()
    for sfr in sfrs:
        for group in _parse_dependency_groups(sfr.dependency):
            for dependency_id in group:
                dependency_sfr = sfr_by_code.get(dependency_id)
                if not dependency_sfr or dependency_sfr.id == sfr.id:
                    continue
                dependency_referrers_by_sfr_id.setdefault(dependency_sfr.id, []).append({
                    "id": sfr.id,
                    "sfr_id": sfr.sfr_id,
                    "sfr_name": sfr.sfr_name,
                })
                referenced_sfr_ids.add(dependency_sfr.id)
    covered_security_problem_ids = {
        *(f"threat:{row.threat_id}" for row in threat_objective_rows),
        *(f"assumption:{row.assumption_id}" for row in assumption_objective_rows),
        *(f"osp:{row.osp_id}" for row in osp_objective_rows),
    }
    security_problem_count = len(threats) + len(assumptions) + len(osps)
    covered_security_problem_count = len(covered_security_problem_ids)

    o_objectives = [item for item in objectives if item.obj_type == "O"]
    oe_objectives = [item for item in objectives if item.obj_type == "OE"]

    objectives_without_sfrs = [
        {
            "id": item.id,
            "label": item.code,
            "detail": _compact_text(item.description),
        }
        for item in o_objectives
        if item.id not in mapped_objective_ids
    ]
    o_objectives_without_sfrs = [
        {
            "id": item.id,
            "label": item.code,
            "detail": _compact_text(item.description),
        }
        for item in o_objectives
        if item.id not in mapped_objective_ids
    ]
    oe_objectives_without_sfrs = []
    redundant_sfrs = [
        {
            "id": item.id,
            "label": item.sfr_id,
            "detail": _compact_text(item.sfr_name or item.sfr_detail or item.dependency_warning),
        }
        for item in sfrs
        if item.id not in mapped_sfr_ids and item.id not in referenced_sfr_ids
    ]
    sfr_dependency_checks = []
    for item in sfrs:
        normalized_dependency = _normalize_dependency_expression(item.dependency)
        if not normalized_dependency:
            continue
        dependency_warning = await _build_dependency_warning(toe_id, normalized_dependency, db, item.id)
        sfr_dependency_checks.append({
            "sfr": item,
            "warning": dependency_warning,
        })
    sfrs_with_dependencies = [entry["sfr"] for entry in sfr_dependency_checks]
    sfrs_missing_dependencies = [
        {
            "id": entry["sfr"].id,
            "label": entry["sfr"].sfr_id,
            "detail": _compact_text(entry["warning"] or entry["sfr"].dependency or entry["sfr"].dependency_warning),
        }
        for entry in sfr_dependency_checks
        if entry["warning"]
    ]
    metrics = [
        _build_metric("security_problem_objective_coverage", covered_security_problem_count, security_problem_count),
        _build_metric("objective_sfr_coverage", len(o_objectives) - len(objectives_without_sfrs), len(o_objectives)),
        _build_metric("sfr_dependency_coverage", len(sfrs_with_dependencies) - len(sfrs_missing_dependencies), len(sfrs_with_dependencies)),
    ]
    score = _weighted_score(metrics)

    findings = [
        {
            "key": "objectives_without_sfrs",
            "severity": "high",
            "count": len(objectives_without_sfrs),
            "items": objectives_without_sfrs,
            "overflow": 0,
        },
        {
            "key": "redundant_sfrs",
            "severity": "medium",
            "count": len(redundant_sfrs),
            "items": redundant_sfrs,
            "overflow": 0,
        },
        {
            "key": "sfrs_missing_dependencies",
            "severity": "high",
            "count": len(sfrs_missing_dependencies),
            "items": sfrs_missing_dependencies[:8],
            "overflow": max(0, len(sfrs_missing_dependencies) - 8),
        },
    ]

    mapping_gap_sections = [
        {
            "key": "security_problem_to_objective",
            "source_type": "objective",
            "objective_type": "O",
            "covered": covered_security_problem_count,
            "total": security_problem_count,
            "gaps": [],
            "overflow": 0,
        },
        {
            "key": "objective_o_to_sfr",
            "source_type": "objective",
            "objective_type": "O",
            "covered": len(o_objectives) - len(o_objectives_without_sfrs),
            "total": len(o_objectives),
            "gaps": o_objectives_without_sfrs[:8],
            "overflow": max(0, len(o_objectives_without_sfrs) - 8),
        },
        {
            "key": "objective_oe_to_sfr",
            "source_type": "objective",
            "objective_type": "OE",
            "covered": 0,
            "total": 0,
            "gaps": [],
            "overflow": 0,
        },
    ]

    next_actions = []
    if objectives_without_sfrs:
        next_actions.append("action_sfr_objectives")
    if sfrs_missing_dependencies:
        next_actions.append("action_sfr_dependencies")
    if redundant_sfrs:
        next_actions.append("action_redundant_sfrs")
    if not next_actions:
        next_actions.append("action_no_gaps")

    total_findings = sum(item["count"] for item in findings)
    high_findings = sum(1 for item in findings if item["severity"] == "high" and item["count"] > 0)
    summary_status = "good" if score >= 85 and high_findings == 0 else "attention" if score >= 60 else "weak"

    return {
        "code": 0,
        "data": {
            "summary": {
                "score": score,
                "status": summary_status,
                "total_findings": total_findings,
                "high_findings": high_findings,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "basis_note": "basis_note_security",
            },
            "basis": {
                "covered_security_problem_count": covered_security_problem_count,
                "security_problem_count": security_problem_count,
                "objective_count": len(o_objectives),
                "sfr_count": len(sfrs),
                "o_objective_count": len(o_objectives),
                "oe_objective_count": len(oe_objectives),
            },
            "metrics": metrics,
            "mapping_gap_sections": mapping_gap_sections,
            "findings": findings,
            "next_actions": next_actions,
        },
    }


# ══════════════════════════════════════════════
#  F4-7: AI generate security objectives
# ══════════════════════════════════════════════

class AIGenObjectiveBody(BaseModel):
    mode: str = "full"   # full | incremental
    language: str = "en"


@router.post("/toes/{toe_id}/objectives/ai-generate")
async def ai_generate_objectives(
    toe_id: str,
    body: AIGenObjectiveBody,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    await _get_toe(toe_id, current_user, db)
    language = (body.language or "en").lower()
    if language not in ("zh", "en"):
        language = "en"
    task = AITask(
        user_id=current_user.id,
        toe_id=toe_id,
        task_type="objective_gen",
        status="pending",
        progress_message="Stage 1/4: Reading TOE information...",
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)

    from app.worker.worker import arq_pool
    if arq_pool:
        await arq_pool.enqueue_job(
            "objective_gen_task",
            toe_id,
            body.mode,
            task.id,
            language,
        )
    else:
        from app.worker.tasks import objective_gen_task
        asyncio.create_task(objective_gen_task({}, toe_id, body.mode, task.id, language))
    return {"code": 0, "data": {"task_id": task.id}}


# ══════════════════════════════════════════════
#  F4-4: SFR Library browse (read-only)
# ══════════════════════════════════════════════

@router.get("/sfr-library")
async def list_sfr_library(
    sfr_class: Optional[str] = None,
    sfr_family: Optional[str] = None,
    keyword: Optional[str] = None,
    page: int = 1,
    page_size: Optional[int] = None,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    _ = current_user
    stmt = select(SFRLibrary)
    if sfr_class:
        stmt = stmt.where(SFRLibrary.sfr_class == sfr_class.upper())
    if sfr_family:
        stmt = stmt.where(SFRLibrary.sfr_family == sfr_family.upper())
    if keyword:
        _escaped = keyword.replace("%", "\\%").replace("_", "\\_")
        kw = f"%{_escaped}%"
        stmt = stmt.where(
            (SFRLibrary.sfr_component.ilike(kw))
            | (SFRLibrary.sfr_component_name.ilike(kw))
            | (SFRLibrary.description.ilike(kw))
        )
    stmt = stmt.order_by(SFRLibrary.sfr_component)

    # Count
    count_stmt = select(SFRLibrary)
    if sfr_class:
        count_stmt = count_stmt.where(SFRLibrary.sfr_class == sfr_class.upper())
    if sfr_family:
        count_stmt = count_stmt.where(SFRLibrary.sfr_family == sfr_family.upper())
    if keyword:
        _escaped = keyword.replace("%", "\\%").replace("_", "\\_")
        kw = f"%{_escaped}%"
        count_stmt = count_stmt.where(
            (SFRLibrary.sfr_component.ilike(kw))
            | (SFRLibrary.sfr_component_name.ilike(kw))
            | (SFRLibrary.description.ilike(kw))
        )
    count_res = await db.exec(count_stmt)
    total = len(count_res.all())

    if page_size and page_size > 0:
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    res = await db.exec(stmt)
    items = res.all()
    serialized_items = []
    for item in items:
        item_data = item.model_dump()
        item_data["dependencies"] = _normalize_dependency_expression(item.dependencies)
        serialized_items.append(item_data)

    # Distinct classes
    class_name_map, _ = await _build_sfr_library_name_maps(db)
    class_res = await db.exec(select(SFRLibrary.sfr_class).distinct())
    classes = []
    for row in class_res.all():
        class_code = row[0] if isinstance(row, (tuple, list)) else row
        class_code = str(class_code or "").strip().upper()
        if not class_code:
            continue
        class_name = class_name_map.get(class_code) or class_code
        classes.append({"value": class_code, "label": f"{class_code} - {class_name}"})
    classes.sort(key=lambda item: item["value"])

    return {"code": 0, "data": {"items": serialized_items, "total": total, "classes": classes}}


@router.get("/sfr-library/{sfr_component}")
async def get_sfr_library_detail(
    sfr_component: str,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    res = await db.exec(
        select(SFRLibrary).where(SFRLibrary.sfr_component == sfr_component.upper())
    )
    lib = res.first()
    if not lib:
        raise HTTPException(404, "SFR component not found")
    return {"code": 0, "data": lib}


@router.put("/sfr-library/{library_id}")
async def update_sfr_library_item(
    library_id: str,
    body: SFRLibraryUpdate,
    current_user: User = Depends(get_current_admin),
    db=Depends(get_db),
):
    _ = current_user
    item = await _get_sfr_library_item(library_id, db)
    normalized_component = _normalize_sfr_component(body.sfr_component)
    if not normalized_component:
        raise HTTPException(400, "SFR ID is required")

    duplicate = (await db.exec(
        select(SFRLibrary).where(
            SFRLibrary.sfr_component == normalized_component,
            SFRLibrary.id != library_id,
        )
    )).first()
    if duplicate:
        raise HTTPException(400, f"SFR ID already exists: {normalized_component}")

    class_name_map, family_name_map = await _build_sfr_library_name_maps(db)
    sfr_class, sfr_family = _derive_sfr_hierarchy(normalized_component)

    item.sfr_component = normalized_component
    item.sfr_component_name = _normalize_optional_text(body.sfr_component_name) or normalized_component
    item.description = _normalize_optional_text(body.description)
    item.dependencies = _normalize_dependency_expression(body.dependencies)
    item.sfr_class = sfr_class
    item.sfr_family = sfr_family
    item.sfr_class_name = class_name_map.get(sfr_class) or item.sfr_class_name or sfr_class
    item.sfr_family_name = family_name_map.get(sfr_family) or item.sfr_family_name or sfr_family

    db.add(item)
    await db.commit()
    await db.refresh(item)
    return ok(data=item)


@router.delete("/sfr-library/{library_id}")
async def delete_sfr_library_item(
    library_id: str,
    current_user: User = Depends(get_current_admin),
    db=Depends(get_db),
):
    _ = current_user
    item = await _get_sfr_library_item(library_id, db)
    linked_sfrs = (await db.exec(
        select(SFR).where(SFR.sfr_library_id == library_id)
    )).all()
    for sfr in linked_sfrs:
        sfr.sfr_library_id = None
        db.add(sfr)
    await db.delete(item)
    await db.commit()
    return ok(msg="deleted")


@router.post("/sfr-library/batch-delete")
async def batch_delete_sfr_library_items(
    body: SFRLibraryBatchDeleteBody,
    current_user: User = Depends(get_current_admin),
    db=Depends(get_db),
):
    _ = current_user
    ids = validate_batch_ids([item for item in body.ids if item])
    if not ids:
        return ok(data={"deleted": 0})

    rows = (await db.exec(select(SFRLibrary).where(SFRLibrary.id.in_(ids)))).all()
    linked_sfrs = (await db.exec(select(SFR).where(SFR.sfr_library_id.in_(ids)))).all()
    for sfr in linked_sfrs:
        sfr.sfr_library_id = None
        db.add(sfr)
    for item in rows:
        await db.delete(item)
    await db.commit()
    return ok(data={"deleted": len(rows)})


@router.post("/sfr-library/import-from-doc")
async def import_sfr_library_from_doc(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_admin),
    db=Depends(get_db),
):
    _ = current_user
    from app.core.uploads import sanitize_filename, get_safe_extension, validate_size, ALLOWED_EXT_SFR_LIBRARY
    content = await file.read()
    if not content:
        raise HTTPException(400, "Empty document")
    validate_size(len(content))
    safe_name = sanitize_filename(file.filename)
    get_safe_extension(safe_name, ALLOWED_EXT_SFR_LIBRARY)
    filename = safe_name.lower()

    decoded_text = None
    for encoding in ("utf-8-sig", "utf-8", "gbk", "gb18030"):
        try:
            decoded_text = content.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if decoded_text is None:
        raise HTTPException(400, "CSV encoding is not supported")

    reader = csv.DictReader(io.StringIO(decoded_text))
    required_headers = ["SFR ID", "SFR Name", "SFR Detail", "Dependencies"]
    actual_headers = reader.fieldnames or []
    if actual_headers != required_headers:
        raise HTTPException(400, "CSV headers must be exactly: SFR ID,SFR Name,SFR Detail,Dependencies")

    class_name_map, family_name_map = await _build_sfr_library_name_maps(db)
    imported = 0
    updated = 0
    normalized_items: list[SFRLibrary] = []
    errors: list[dict] = []

    for index, row in enumerate(reader, start=2):
        sfr_component = _normalize_sfr_component(row.get("SFR ID") or "")
        if not sfr_component:
            errors.append({"row": index, "sfr_id": None, "reason": "SFR ID is required"})
            continue
        sfr_class, sfr_family = _derive_sfr_hierarchy(sfr_component)
        sfr_name = _normalize_optional_text(row.get("SFR Name")) or sfr_component
        sfr_detail = _normalize_optional_text(row.get("SFR Detail"))
        dependencies = _normalize_dependency_expression(row.get("Dependencies"))

        if len(sfr_component) > 32:
            errors.append({"row": index, "sfr_id": sfr_component, "reason": "SFR ID is too long"})
            continue
        if sfr_name and len(sfr_name) > 256:
            errors.append({"row": index, "sfr_id": sfr_component, "reason": "SFR Name is too long"})
            continue

        try:
            existing = (await db.exec(select(SFRLibrary).where(SFRLibrary.sfr_component == sfr_component))).first()
            if existing:
                existing.sfr_class = sfr_class
                existing.sfr_class_name = class_name_map.get(sfr_class) or existing.sfr_class_name or sfr_class
                existing.sfr_family = sfr_family
                existing.sfr_family_name = family_name_map.get(sfr_family) or existing.sfr_family_name or sfr_family
                existing.sfr_component_name = sfr_name
                existing.description = sfr_detail
                existing.dependencies = dependencies
                db.add(existing)
                normalized_items.append(existing)
                updated += 1
            else:
                item = SFRLibrary(
                    sfr_class=sfr_class,
                    sfr_class_name=class_name_map.get(sfr_class) or sfr_class,
                    sfr_family=sfr_family,
                    sfr_family_name=family_name_map.get(sfr_family) or sfr_family,
                    sfr_component=sfr_component,
                    sfr_component_name=sfr_name,
                    description=sfr_detail,
                    dependencies=dependencies,
                )
                db.add(item)
                normalized_items.append(item)
                imported += 1
        except Exception as exc:
            errors.append({"row": index, "sfr_id": sfr_component, "reason": str(exc)[:200]})

    await db.commit()
    for item in normalized_items:
        await db.refresh(item)
    return ok(data={"imported": imported, "updated": updated, "items": normalized_items, "errors": errors})


# ══════════════════════════════════════════════
#  F4-5: TOE SFR instance CRUD
# ══════════════════════════════════════════════

class SFRCreate(BaseModel):
    sfr_id: str                       # FDP_ACC.1 or CUSTOM.xxx
    sfr_library_id: Optional[str] = None
    sfr_name: Optional[str] = None
    sfr_detail: Optional[str] = None
    dependency: Optional[str] = None
    source: str = "manual"            # manual | ai | st_pp
    customization_note: Optional[str] = None
    ai_rationale: Optional[str] = None


class SFRUpdate(BaseModel):
    sfr_id: Optional[str] = None
    sfr_name: Optional[str] = None
    sfr_detail: Optional[str] = None
    dependency: Optional[str] = None
    source: Optional[str] = None
    customization_note: Optional[str] = None
    ai_rationale: Optional[str] = None


class SFRAICompleteBody(BaseModel):
    sfr_id: str
    current_objective_ids: List[str] = []
    current_test_ids: List[str] = []


@router.post("/toes/{toe_id}/sfrs/auto-manage")
async def auto_manage_sfrs(
    toe_id: str,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    await _get_toe(toe_id, current_user, db)
    result = await _refresh_sfr_dependency_state(toe_id, db)
    await db.commit()
    return ok(data=result)


@router.get("/toes/{toe_id}/sfrs")
async def list_sfrs(
    toe_id: str,
    review_status: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    await _get_toe(toe_id, current_user, db, writable=False)
    stmt = select(SFR).where(SFR.toe_id == toe_id, SFR.deleted_at.is_(None))
    if review_status:
        stmt = stmt.where(SFR.review_status == review_status)
    stmt = stmt.order_by(SFR.sfr_id)
    res = await db.exec(stmt)
    sfrs = res.all()

    sfr_ids = [item.id for item in sfrs]
    objective_sfr_rows = (await db.exec(
        select(ObjectiveSFR).where(ObjectiveSFR.sfr_id.in_(sfr_ids))
    )).all() if sfr_ids else []
    objective_ids = sorted({row.objective_id for row in objective_sfr_rows})
    objectives = (await db.exec(
        select(SecurityObjective).where(
            SecurityObjective.id.in_(objective_ids),
            SecurityObjective.deleted_at.is_(None),
        )
    )).all() if objective_ids else []
    objective_map = {item.id: item for item in objectives}
    objective_map_by_sfr: dict[str, list[dict]] = {}
    for row in objective_sfr_rows:
        objective = objective_map.get(row.objective_id)
        if not objective:
            continue
        objective_map_by_sfr.setdefault(row.sfr_id, []).append({
            "id": objective.id,
            "code": objective.code,
            "obj_type": objective.obj_type,
            "mapping_rationale": row.mapping_rationale,
        })
    test_cases = (await db.exec(
        select(TestCase).where(
            TestCase.toe_id == toe_id,
            TestCase.deleted_at.is_(None),
        )
    )).all()
    linked_tests_by_sfr: dict[str, list[dict]] = {}
    for test_case in test_cases:
        if test_case.related_sfr_ids is None:
            linked_sfr_ids = [test_case.primary_sfr_id]
        else:
            linked_sfr_ids = _parse_related_sfr_ids(test_case.related_sfr_ids)
        for linked_sfr_id in linked_sfr_ids:
            if linked_sfr_id not in sfr_ids:
                continue
            linked_tests_by_sfr.setdefault(linked_sfr_id, []).append({
                "id": test_case.id,
                "case_number": test_case.case_number,
                "title": test_case.title,
                "review_status": test_case.review_status,
            })
    sfr_by_code = {item.sfr_id.upper(): item for item in sfrs}
    linked_dependency_sfrs_by_sfr: dict[str, list[dict]] = {}
    for sfr in sfrs:
        for group in _parse_dependency_groups(sfr.dependency):
            for dependency_id in group:
                dependency_sfr = sfr_by_code.get(dependency_id)
                if not dependency_sfr or dependency_sfr.id == sfr.id:
                    continue
                linked_dependency_sfrs_by_sfr.setdefault(dependency_sfr.id, []).append({
                    "id": sfr.id,
                    "sfr_id": sfr.sfr_id,
                    "sfr_name": sfr.sfr_name,
                })

    # Enrich with library info
    result = []
    for sfr in sfrs:
        item = sfr.model_dump()
        item["source"] = _normalize_sfr_source(sfr.source)
        if sfr.sfr_library_id:
            lib_res = await db.exec(
                select(SFRLibrary).where(SFRLibrary.id == sfr.sfr_library_id)
            )
            lib = lib_res.first()
            if lib:
                library_data = lib.model_dump()
                library_data["dependencies"] = _normalize_dependency_expression(lib.dependencies)
                item["library"] = library_data
            else:
                item["library"] = None
        else:
            lib = await _get_sfr_library_by_component(sfr.sfr_id, db)
            if lib:
                library_data = lib.model_dump()
                library_data["dependencies"] = _normalize_dependency_expression(lib.dependencies)
                item["library"] = library_data
            else:
                item["library"] = None
        item.update(_resolve_sfr_display_fields(sfr, lib))
        linked_objectives = sorted(
            objective_map_by_sfr.get(sfr.id, []),
            key=lambda objective: objective["code"],
        )
        linked_dependency_sfrs = sorted(
            linked_dependency_sfrs_by_sfr.get(sfr.id, []),
            key=lambda dependency_sfr: dependency_sfr["sfr_id"],
        )
        item["objective_ids"] = [objective["id"] for objective in linked_objectives]
        item["linked_objectives"] = linked_objectives
        item["linked_dependency_sfrs"] = linked_dependency_sfrs
        item["linked_tests"] = linked_tests_by_sfr.get(sfr.id, [])
        result.append(item)
    return {"code": 0, "data": result}


@router.post("/toes/{toe_id}/sfrs")
async def create_sfr(
    toe_id: str,
    body: SFRCreate,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    await _get_toe(toe_id, current_user, db)

    # Resolve library id if not provided
    source = _normalize_sfr_source(body.source)
    sfr_library_id = body.sfr_library_id
    sfr_id = body.sfr_id.upper()
    if not sfr_library_id:
        lib = await _get_sfr_library_by_component(sfr_id, db)
        if lib:
            sfr_library_id = lib.id
    else:
        lib_res = await db.exec(select(SFRLibrary).where(SFRLibrary.id == sfr_library_id))
        lib = lib_res.first()

    sfr_name = _normalize_optional_text(body.sfr_name) or (lib.sfr_component_name if lib else None)
    sfr_detail = _normalize_optional_text(body.sfr_detail) or (lib.description if lib else None)
    dependency = _normalize_dependency_expression(_normalize_optional_text(body.dependency) or (lib.dependencies if lib else None))
    dependency_warning = await _build_dependency_warning(toe_id, dependency, db)

    sfr = SFR(
        toe_id=toe_id,
        sfr_library_id=sfr_library_id,
        sfr_id=sfr_id,
        sfr_name=sfr_name,
        sfr_detail=sfr_detail,
        dependency=dependency,
        source=source,
        customization_note=body.customization_note,
        ai_rationale=body.ai_rationale,
        dependency_warning=dependency_warning,
        review_status="draft",
    )
    db.add(sfr)
    await db.flush()
    await _refresh_sfr_dependency_state(toe_id, db)
    await db.commit()
    await db.refresh(sfr)
    return {"code": 0, "data": sfr}


@router.put("/toes/{toe_id}/sfrs/{sfr_id}")
async def update_sfr(
    toe_id: str,
    sfr_id: str,
    body: SFRUpdate,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    await _get_toe(toe_id, current_user, db)
    sfr = await _get_sfr(sfr_id, toe_id, db)
    next_sfr_id = body.sfr_id.upper() if body.sfr_id is not None else sfr.sfr_id
    next_library = await _get_sfr_library_by_component(next_sfr_id, db)
    if body.sfr_id is not None:
        sfr.sfr_id = next_sfr_id
        sfr.sfr_library_id = next_library.id if next_library else None
    if body.sfr_name is not None:
        sfr.sfr_name = _normalize_optional_text(body.sfr_name)
    elif body.sfr_id is not None and next_library and not sfr.sfr_name:
        sfr.sfr_name = next_library.sfr_component_name
    if body.sfr_detail is not None:
        sfr.sfr_detail = _normalize_optional_text(body.sfr_detail)
    elif body.sfr_id is not None and next_library and not sfr.sfr_detail:
        sfr.sfr_detail = next_library.description
    if body.dependency is not None:
        sfr.dependency = _normalize_dependency_expression(body.dependency)
    elif body.sfr_id is not None and next_library and not sfr.dependency:
        sfr.dependency = _normalize_dependency_expression(next_library.dependencies)
    if body.source is not None:
        sfr.source = _normalize_sfr_source(body.source)
    if body.customization_note is not None:
        sfr.customization_note = body.customization_note
    if body.ai_rationale is not None:
        sfr.ai_rationale = body.ai_rationale
    sfr.dependency_warning = await _build_dependency_warning(toe_id, sfr.dependency, db, sfr.id)
    db.add(sfr)
    await db.flush()
    await _refresh_sfr_dependency_state(toe_id, db)
    await db.commit()
    await db.refresh(sfr)
    return {"code": 0, "data": sfr}


@router.post("/toes/{toe_id}/sfrs/{sfr_id}/fill-dependencies")
async def fill_sfr_dependencies(
    toe_id: str,
    sfr_id: str,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    await _get_toe(toe_id, current_user, db)
    root_sfr = await _get_sfr(sfr_id, toe_id, db)

    existing_sfrs = (await db.exec(
        select(SFR).where(
            SFR.toe_id == toe_id,
            SFR.deleted_at.is_(None),
        )
    )).all()
    existing_by_code = {item.sfr_id.upper(): item for item in existing_sfrs}

    objective_rows = (await db.exec(
        select(ObjectiveSFR).where(ObjectiveSFR.sfr_id.in_([item.id for item in existing_sfrs]))
    )).all() if existing_sfrs else []
    objective_ids_by_sfr: dict[str, list[str]] = {}
    existing_mapping_pairs: set[tuple[str, str]] = set()
    for row in objective_rows:
        objective_ids_by_sfr.setdefault(row.sfr_id, []).append(row.objective_id)
        existing_mapping_pairs.add((row.objective_id, row.sfr_id))

    queue: list[SFR] = [root_sfr]
    visited: set[str] = set()
    created_sfrs: list[dict[str, str]] = []
    linked_objective_mappings = 0

    while queue:
        current = queue.pop(0)
        if current.id in visited:
            continue
        visited.add(current.id)

        current_lib = await _resolve_sfr_library(current, db)
        current_dependency = _normalize_dependency_expression(current.dependency or (current_lib.dependencies if current_lib else None))
        current_objective_ids = objective_ids_by_sfr.get(current.id, [])

        for group in _parse_dependency_groups(current_dependency):
            existing_dependency = next(
                (existing_by_code[dependency_id] for dependency_id in group if dependency_id in existing_by_code and existing_by_code[dependency_id].id != current.id),
                None,
            )
            if existing_dependency:
                queue.append(existing_dependency)
                continue

            dependency_id = group[0]
            dependency_lib = await _get_sfr_library_by_component(dependency_id, db)
            dependency_sfr = SFR(
                toe_id=toe_id,
                sfr_library_id=dependency_lib.id if dependency_lib else None,
                sfr_id=dependency_id,
                sfr_name=dependency_lib.sfr_component_name if dependency_lib else None,
                sfr_detail=dependency_lib.description if dependency_lib else None,
                dependency=_normalize_dependency_expression(dependency_lib.dependencies if dependency_lib else None),
                source="manual",
                dependency_warning=None,
                review_status="draft",
                ai_rationale=f"Auto-added as a dependency of {current.sfr_id}",
            )
            db.add(dependency_sfr)
            await db.flush()

            existing_by_code[dependency_id] = dependency_sfr
            objective_ids_by_sfr.setdefault(dependency_sfr.id, [])
            created_sfrs.append({"id": dependency_sfr.id, "sfr_id": dependency_sfr.sfr_id})

            for objective_id in current_objective_ids:
                pair = (objective_id, dependency_sfr.id)
                if pair in existing_mapping_pairs:
                    continue
                db.add(ObjectiveSFR(
                    objective_id=objective_id,
                    sfr_id=dependency_sfr.id,
                    mapping_rationale=f"Inherited from dependency relationship of {current.sfr_id}",
                ))
                existing_mapping_pairs.add(pair)
                objective_ids_by_sfr[dependency_sfr.id].append(objective_id)
                linked_objective_mappings += 1

            queue.append(dependency_sfr)

    refresh_result = await _refresh_sfr_dependency_state(toe_id, db)
    await db.commit()
    return ok(data={
        "created_count": len(created_sfrs),
        "created_sfrs": created_sfrs,
        "linked_objective_mappings": linked_objective_mappings,
        "dependency_state": refresh_result,
    })


@router.delete("/toes/{toe_id}/sfrs/{sfr_id}")
async def delete_sfr(
    toe_id: str,
    sfr_id: str,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    await _get_toe(toe_id, current_user, db)
    sfr = await _get_sfr(sfr_id, toe_id, db)
    mapping_rows = (await db.exec(
        select(ObjectiveSFR).where(ObjectiveSFR.sfr_id == sfr.id)
    )).all()
    for row in mapping_rows:
        await db.delete(row)
    sfr.deleted_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.add(sfr)
    await db.flush()
    await _refresh_sfr_dependency_state(toe_id, db)
    await db.commit()
    return {"code": 0, "data": None}


@router.post("/toes/{toe_id}/sfrs/{sfr_id}/confirm")
async def confirm_sfr(
    toe_id: str, sfr_id: str,
    current_user: User = Depends(get_current_user), db=Depends(get_db),
):
    await _get_toe(toe_id, current_user, db)
    sfr = await _get_sfr(sfr_id, toe_id, db)
    sfr.review_status = "confirmed"
    sfr.reviewed_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.add(sfr)
    await db.commit()
    return {"code": 0, "data": sfr}


@router.post("/toes/{toe_id}/sfrs/{sfr_id}/reject")
async def reject_sfr(
    toe_id: str, sfr_id: str,
    current_user: User = Depends(get_current_user), db=Depends(get_db),
):
    await _get_toe(toe_id, current_user, db)
    sfr = await _get_sfr(sfr_id, toe_id, db)
    sfr.review_status = "rejected"
    sfr.reviewed_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.add(sfr)
    await db.commit()
    return {"code": 0, "data": sfr}


@router.post("/toes/{toe_id}/sfrs/{sfr_id}/revert")
async def revert_sfr(
    toe_id: str, sfr_id: str,
    current_user: User = Depends(get_current_user), db=Depends(get_db),
):
    await _get_toe(toe_id, current_user, db)
    sfr = await _get_sfr(sfr_id, toe_id, db)
    sfr.review_status = "draft"
    sfr.reviewed_at = None
    db.add(sfr)
    await db.commit()
    return {"code": 0, "data": sfr}


# ══════════════════════════════════════════════
#  F4-6: Objective ↔ SFR mapping
# ══════════════════════════════════════════════

class ObjectiveSFRMap(BaseModel):
    sfr_id: str
    mapping_rationale: Optional[str] = None


@router.get("/toes/{toe_id}/objectives/{objective_id}/sfrs")
async def list_objective_sfrs(
    toe_id: str,
    objective_id: str,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    await _get_toe(toe_id, current_user, db, writable=False)
    await _get_objective(objective_id, toe_id, db)
    res = await db.exec(
        select(ObjectiveSFR).where(ObjectiveSFR.objective_id == objective_id)
    )
    mappings = res.all()
    result = []
    for m in mappings:
        sfr_res = await db.exec(
            select(SFR).where(SFR.id == m.sfr_id, SFR.deleted_at.is_(None))
        )
        sfr = sfr_res.first()
        if sfr:
            result.append({"sfr_id": m.sfr_id, "mapping_rationale": m.mapping_rationale, "sfr": sfr})
    return {"code": 0, "data": result}


@router.post("/toes/{toe_id}/objectives/{objective_id}/map-sfr")
async def add_objective_sfr(
    toe_id: str,
    objective_id: str,
    body: ObjectiveSFRMap,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    await _get_toe(toe_id, current_user, db)
    await _get_objective(objective_id, toe_id, db)
    # Verify SFR belongs to this TOE
    await _get_sfr(body.sfr_id, toe_id, db)

    res = await db.exec(
        select(ObjectiveSFR).where(
            ObjectiveSFR.objective_id == objective_id,
            ObjectiveSFR.sfr_id == body.sfr_id,
        )
    )
    existing = res.first()
    if existing:
        existing.mapping_rationale = body.mapping_rationale
        db.add(existing)
    else:
        db.add(ObjectiveSFR(
            objective_id=objective_id,
            sfr_id=body.sfr_id,
            mapping_rationale=body.mapping_rationale,
        ))
    await db.commit()
    return {"code": 0, "data": None}


@router.delete("/toes/{toe_id}/objectives/{objective_id}/map-sfr/{sfr_id}")
async def remove_objective_sfr(
    toe_id: str,
    objective_id: str,
    sfr_id: str,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    await _get_toe(toe_id, current_user, db)
    res = await db.exec(
        select(ObjectiveSFR).where(
            ObjectiveSFR.objective_id == objective_id,
            ObjectiveSFR.sfr_id == sfr_id,
        )
    )
    row = res.first()
    if row:
        await db.delete(row)
        await db.commit()
    return {"code": 0, "data": None}


@router.post("/toes/{toe_id}/sfrs/ai-complete")
async def ai_complete_sfr(
    toe_id: str,
    body: SFRAICompleteBody,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    toe = await _get_toe(toe_id, current_user, db)
    sfr_id = body.sfr_id.strip().upper()
    if not sfr_id:
        raise HTTPException(400, "SFR ID is required")

    library = await _get_sfr_library_by_component(sfr_id, db)
    objectives = (await db.exec(
        select(SecurityObjective).where(
            SecurityObjective.toe_id == toe_id,
            SecurityObjective.deleted_at.is_(None),
        ).order_by(SecurityObjective.code)
    )).all()
    tests = (await db.exec(
        select(TestCase).where(
            TestCase.toe_id == toe_id,
            TestCase.deleted_at.is_(None),
        ).order_by(TestCase.created_at)
    )).all()

    suggested_name = library.sfr_component_name if library else None
    suggested_detail = library.description if library else None
    suggested_dependency = _normalize_dependency_expression(library.dependencies if library else None)
    suggested_objective_ids: List[str] = []
    suggested_test_ids: List[str] = []

    ai = await get_ai_service(db, toe.user_id)
    if ai:
        objective_catalog = "\n".join(
            f"- {item.code}: {_compact_text(item.description, 160)}"
            for item in objectives[:80]
        ) or "-"
        test_catalog = "\n".join(
            f"- {item.title}"
            for item in tests[:80]
        ) or "-"
        prompt = f"""You are a CC security expert. Complete SFR metadata and suggest relevant linked objectives and linked tests for the TOE.

SFR ID:
{sfr_id}

Known CC library information:
- Name: {suggested_name or '-'}
- Detail: {suggested_detail or '-'}
- Dependency: {suggested_dependency or '-'}

Available Security Objectives:
{objective_catalog}

Available Tests:
{test_catalog}

Return strict JSON:
{{
  "sfr_name": "...",
  "sfr_detail": "...",
  "dependency": "...",
  "objective_codes": ["O.EXAMPLE"],
  "test_titles": ["Example test title"]
}}

Rules:
- Prefer the exact CC Part 2 meaning of the SFR.
- If library information is already exact, keep it.
- Only suggest objective codes and test titles from the provided lists.
- If there is no confident suggestion, return an empty array for that field."""
        try:
            ai_result = await ai.chat_json(prompt, max_tokens=2048)
        except Exception as exc:
            if not library:
                raise HTTPException(400, f"AI completion failed: {exc}")
            ai_result = {}

        if isinstance(ai_result, dict):
            suggested_name = _normalize_optional_text(ai_result.get("sfr_name")) or suggested_name
            suggested_detail = _normalize_optional_text(ai_result.get("sfr_detail")) or suggested_detail
            suggested_dependency = _normalize_dependency_expression(ai_result.get("dependency")) or suggested_dependency
            objective_codes = {
                str(code).strip().upper()
                for code in (ai_result.get("objective_codes") or [])
                if str(code).strip()
            }
            test_titles = {
                str(title).strip()
                for title in (ai_result.get("test_titles") or [])
                if str(title).strip()
            }
            suggested_objective_ids = [item.id for item in objectives if item.code.strip().upper() in objective_codes]
            suggested_test_ids = [item.id for item in tests if item.title in test_titles]

    if not suggested_name and not suggested_detail and not suggested_dependency:
        raise HTTPException(400, "No SFR information was found for completion")

    return {
        "code": 0,
        "data": {
            "sfr_id": sfr_id,
            "sfr_name": suggested_name,
            "sfr_detail": suggested_detail,
            "dependency": suggested_dependency,
            "suggested_objective_ids": suggested_objective_ids,
            "suggested_test_ids": suggested_test_ids,
            "available_objectives": [
                {"id": item.id, "code": item.code, "obj_type": item.obj_type}
                for item in objectives
            ],
            "available_tests": [
                {"id": item.id, "title": item.title}
                for item in tests
            ],
        },
    }


# ══════════════════════════════════════════════
#  F4-8: AI SFR matching
# ══════════════════════════════════════════════

class AISFRMatchBody(BaseModel):
    mode: str = "full"
    language: str = "en"


@router.post("/toes/{toe_id}/sfrs/ai-match")
async def ai_match_sfrs(
    toe_id: str,
    body: AISFRMatchBody,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    await _get_toe(toe_id, current_user, db)
    language = (body.language or "en").lower()
    if language not in ("zh", "en"):
        language = "en"
    task = AITask(
        user_id=current_user.id,
        toe_id=toe_id,
        task_type="sfr_match",
        status="pending",
        progress_message="Phase 1/5: Reading security objectives...",
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)

    from app.worker.worker import arq_pool
    if arq_pool:
        await arq_pool.enqueue_job("sfr_match_task", toe_id, body.mode, task.id, language)
    else:
        from app.worker.tasks import sfr_match_task
        asyncio.create_task(sfr_match_task({}, toe_id, body.mode, task.id, language))
    return {"code": 0, "data": {"task_id": task.id}}


@router.post("/toes/{toe_id}/sfrs/st-pp-validate")
async def validate_sfrs_from_st_pp(
    toe_id: str,
    body: dict = {},
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    await _get_toe(toe_id, current_user, db)
    language = (body or {}).get("language", "en")
    if language not in ("zh", "en"):
        language = "en"
    task = AITask(
        user_id=current_user.id,
        toe_id=toe_id,
        task_type="sfr_stpp_validate",
        status="pending",
        progress_message="Phase 1/5: Reading ST/PP documents...",
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)

    from app.worker.worker import arq_pool
    if arq_pool:
        await arq_pool.enqueue_job("sfr_stpp_validate_task", toe_id, task.id, language)
    else:
        from app.worker.tasks import sfr_stpp_validate_task
        asyncio.create_task(sfr_stpp_validate_task({}, toe_id, task.id, language))
    return {"code": 0, "data": {"task_id": task.id}}
