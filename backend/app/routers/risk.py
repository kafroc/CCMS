"""
Phase 5: Risk assessment routes.
"""
import re
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from sqlmodel import select, func
from app.core.database import get_db
from app.core.auth import get_current_user
from app.core.toe_permissions import get_accessible_toe
from app.models.user import User
from app.models.toe import TOE
from app.models.threat import Threat
from app.models.risk import RiskAssessment, TOERiskCache
from app.models.ai_task import AITask
from pydantic import BaseModel
from datetime import datetime, timezone

router = APIRouter(prefix="/api", tags=["risk"])

RISK_MATRIX = {
    "low":    {"low": "low",    "medium": "low",    "high": "medium"},
    "medium": {"low": "medium", "medium": "medium", "high": "high"},
    "high":   {"low": "medium", "medium": "high",   "high": "critical"},
}


async def _get_toe(toe_id: str, user: User, db, writable: bool = True) -> TOE:
    return await get_accessible_toe(toe_id, user, db, writable=writable)


# ── Risk assessment CRUD ──

class RiskAssessmentCreate(BaseModel):
    threat_id: str
    residual_risk: str   # accepted|mitigated|transferred|avoided
    mitigation_notes: Optional[str] = None
    assessor: Optional[str] = None


class RiskAssessmentUpdate(BaseModel):
    residual_risk: Optional[str] = None
    mitigation_notes: Optional[str] = None
    assessor: Optional[str] = None


@router.get("/toes/{toe_id}/risk-assessments")
async def list_risk_assessments(
    toe_id: str,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    await get_accessible_toe(toe_id, current_user, db, writable=True)
    res = await db.exec(
        select(RiskAssessment).where(RiskAssessment.toe_id == toe_id)
    )
    return {"code": 0, "data": res.all()}


@router.put("/toes/{toe_id}/risk-assessments/{threat_id}")
async def upsert_risk_assessment(
    toe_id: str,
    threat_id: str,
    body: RiskAssessmentUpdate,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    await get_accessible_toe(toe_id, current_user, db, writable=True)
    res = await db.exec(
        select(RiskAssessment).where(
            RiskAssessment.toe_id == toe_id,
            RiskAssessment.threat_id == threat_id,
        )
    )
    ra = res.first()
    if ra:
        if body.residual_risk is not None:
            ra.residual_risk = body.residual_risk
        if body.mitigation_notes is not None:
            ra.mitigation_notes = body.mitigation_notes
        if body.assessor is not None:
            ra.assessor = body.assessor
    else:
        # Auto-determine mitigation status based on chain completeness
        from app.models.security import SecurityObjective, ObjectiveSFR, ThreatObjective
        from app.models.test_case import TestCase

        threat_res = await db.exec(select(Threat).where(Threat.id == threat_id))
        threat = threat_res.first()

        # Compute chain status for auto-mitigation
        auto_residual = body.residual_risk
        if auto_residual is None and threat and threat.review_status != "false_positive":
            # Get objectives linked to this threat
            to_res = await db.exec(
                select(ThreatObjective).where(ThreatObjective.threat_id == threat_id)
            )
            threat_objs = to_res.all()

            if threat_objs:
                obj_ids = {link.objective_id for link in threat_objs}

                # Get SFRs linked to these objectives
                os_res = await db.exec(
                    select(ObjectiveSFR).where(
                        ObjectiveSFR.objective_id.in_(list(obj_ids))
                    )
                )
                sfr_links = os_res.all()

                if sfr_links:
                    sfr_ids = {link.sfr_id for link in sfr_links}

                    # Get tests for these SFRs
                    tc_res = await db.exec(
                        select(TestCase).where(
                            TestCase.toe_id == toe_id,
                            TestCase.primary_sfr_id.in_(list(sfr_ids))
                        )
                    )
                    tests = tc_res.all()

                    # Treat a basic Threat -> Objective -> SFR -> Test chain as mitigated by default.
                    if len(tests) > 0:
                        auto_residual = "mitigated"

        ra = RiskAssessment(
            toe_id=toe_id,
            threat_id=threat_id,
            residual_risk=auto_residual or "accepted",
            mitigation_notes=body.mitigation_notes,
            assessor=body.assessor,
        )
    db.add(ra)

    # Mark cache stale
    cache_res = await db.exec(
        select(TOERiskCache).where(TOERiskCache.toe_id == toe_id)
    )
    cache = cache_res.first()
    if cache:
        cache.is_stale = True
        db.add(cache)

    await db.commit()
    await db.refresh(ra)
    return {"code": 0, "data": ra}


# ── Risk dashboard ──

@router.get("/toes/{toe_id}/risk-dashboard")
async def get_risk_dashboard(
    toe_id: str,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    from app.models.security import SecurityObjective, SFR, ObjectiveSFR, ThreatObjective
    from app.models.threat import Assumption, OSP
    from app.models.test_case import TestCase

    await _get_toe(toe_id, current_user, db, writable=False)

    # All security problems (Threats, Assumptions, OSPs)
    threats_res = await db.exec(
        select(Threat).where(
            Threat.toe_id == toe_id,
            Threat.deleted_at.is_(None),
        )
    )
    threats = threats_res.all()
    threat_ids = [t.id for t in threats]

    assumptions_res = await db.exec(
        select(Assumption).where(Assumption.toe_id == toe_id, Assumption.deleted_at.is_(None))
    )
    assumptions = assumptions_res.all()
    assumption_ids = [a.id for a in assumptions]

    osps_res = await db.exec(
        select(OSP).where(OSP.toe_id == toe_id, OSP.deleted_at.is_(None))
    )
    osps = osps_res.all()
    osp_ids = [o.id for o in osps]

    # Risk assessments
    ra_res = await db.exec(
        select(RiskAssessment).where(RiskAssessment.toe_id == toe_id)
    )
    assessments = {ra.threat_id: ra for ra in ra_res.all()}

    # ── CC Chain data for all security problems ──
    from app.models.security import AssumptionObjective, OSPObjective

    # Threat → Objectives
    threat_obj_map: dict[str, set[str]] = {}
    if threat_ids:
        to_res = await db.exec(
            select(ThreatObjective).where(
                ThreatObjective.threat_id.in_(threat_ids)  # type: ignore
            )
        )
        for link in to_res.all():
            threat_obj_map.setdefault(link.threat_id, set()).add(link.objective_id)

    # Assumption → Objectives
    assumption_obj_map: dict[str, set[str]] = {}
    if assumption_ids:
        ao_res = await db.exec(
            select(AssumptionObjective).where(
                AssumptionObjective.assumption_id.in_(assumption_ids)  # type: ignore
            )
        )
        for link in ao_res.all():
            assumption_obj_map.setdefault(link.assumption_id, set()).add(link.objective_id)

    # OSP → Objectives
    osp_obj_map: dict[str, set[str]] = {}
    if osp_ids:
        oo_res = await db.exec(
            select(OSPObjective).where(
                OSPObjective.osp_id.in_(osp_ids)  # type: ignore
            )
        )
        for link in oo_res.all():
            osp_obj_map.setdefault(link.osp_id, set()).add(link.objective_id)

    # Objective → SFRs
    obj_ids_in_scope = set()
    for oids in threat_obj_map.values():
        obj_ids_in_scope.update(oids)
    for oids in assumption_obj_map.values():
        obj_ids_in_scope.update(oids)
    for oids in osp_obj_map.values():
        obj_ids_in_scope.update(oids)
    obj_sfr_map: dict[str, set[str]] = {}
    if obj_ids_in_scope:
        os_res = await db.exec(
            select(ObjectiveSFR).where(
                ObjectiveSFR.objective_id.in_(list(obj_ids_in_scope))  # type: ignore
            )
        )
        for link in os_res.all():
            obj_sfr_map.setdefault(link.objective_id, set()).add(link.sfr_id)

    # SFR → Tests
    sfr_ids_in_scope = set()
    for sids in obj_sfr_map.values():
        sfr_ids_in_scope.update(sids)
    sfr_test_map: dict[str, list[str]] = {}  # sfr_id → [test statuses]
    if sfr_ids_in_scope:
        tc_res = await db.exec(
            select(TestCase).where(
                TestCase.toe_id == toe_id,
                TestCase.deleted_at.is_(None),
                TestCase.primary_sfr_id.in_(list(sfr_ids_in_scope)),  # type: ignore
            )
        )
        for tc in tc_res.all():
            sfr_test_map.setdefault(tc.primary_sfr_id, []).append(tc.review_status)

    # Helper function to compute chain status
    def compute_chain_status(problem_id: str, obj_map: dict) -> str:
        obj_ids = obj_map.get(problem_id, set())
        obj_count = len(obj_ids)
        sfr_ids: set[str] = set()
        for oid in obj_ids:
            sfr_ids.update(obj_sfr_map.get(oid, set()))
        sfr_count = len(sfr_ids)
        test_statuses: list[str] = []
        for sid in sfr_ids:
            test_statuses.extend(sfr_test_map.get(sid, []))
        test_count = len(test_statuses)
        confirmed_tests = sum(1 for s in test_statuses if s == "confirmed")

        if obj_count == 0:
            return "no_objective"
        elif sfr_count == 0:
            return "no_sfr"
        elif test_count == 0:
            return "no_test"
        elif confirmed_tests == 0:
            return "tests_unconfirmed"
        elif confirmed_tests < sfr_count:
            return "partially_tested"
        else:
            return "fully_assured"

    def compute_auto_residual_risk(review_status: str, obj_count: int, sfr_count: int, test_count: int) -> str:
        if review_status == "false_positive":
            return "unassessed"
        if obj_count > 0 and sfr_count > 0 and test_count > 0:
            return "mitigated"
        return "unassessed"

    # ── Build security problem details with chain info ──
    risk_dist = {"low": 0, "medium": 0, "high": 0, "critical": 0}
    status_dist = {"pending": 0, "confirmed": 0, "false_positive": 0}
    residual_dist = {"accepted": 0, "mitigated": 0, "transferred": 0, "avoided": 0, "unassessed": 0}

    threat_details = []
    for t in threats:
        risk_dist[t.risk_level] = risk_dist.get(t.risk_level, 0) + 1
        status_dist[t.review_status] = status_dist.get(t.review_status, 0) + 1

        # Compute chain coverage for this threat
        obj_ids = threat_obj_map.get(t.id, set())
        obj_count = len(obj_ids)
        sfr_ids: set[str] = set()
        for oid in obj_ids:
            sfr_ids.update(obj_sfr_map.get(oid, set()))
        sfr_count = len(sfr_ids)
        test_statuses: list[str] = []
        for sid in sfr_ids:
            test_statuses.extend(sfr_test_map.get(sid, []))
        test_count = len(test_statuses)
        confirmed_tests = sum(1 for s in test_statuses if s == "confirmed")

        chain_status = compute_chain_status(t.id, threat_obj_map)
        ra = assessments.get(t.id)
        effective_residual = ra.residual_risk if ra else compute_auto_residual_risk(
            t.review_status,
            obj_count,
            sfr_count,
            test_count,
        )
        residual_dist[effective_residual] = residual_dist.get(effective_residual, 0) + 1

        threat_details.append({
            "type": "threat",
            "id": t.id,
            "code": t.code,
            "risk_level": t.risk_level,
            "review_status": t.review_status,
            "objectives": obj_count,
            "sfrs": sfr_count,
            "tests": test_count,
            "confirmed_tests": confirmed_tests,
            "chain_status": chain_status,
            "effective_residual_risk": effective_residual,
        })

    # Build assumption details
    assumption_details = []
    for a in assumptions:
        status_dist[a.review_status] = status_dist.get(a.review_status, 0) + 1
        chain_status = compute_chain_status(a.id, assumption_obj_map)

        obj_ids = assumption_obj_map.get(a.id, set())
        obj_count = len(obj_ids)
        sfr_ids: set[str] = set()
        for oid in obj_ids:
            sfr_ids.update(obj_sfr_map.get(oid, set()))
        sfr_count = len(sfr_ids)
        test_statuses: list[str] = []
        for sid in sfr_ids:
            test_statuses.extend(sfr_test_map.get(sid, []))
        test_count = len(test_statuses)
        confirmed_tests = sum(1 for s in test_statuses if s == "confirmed")

        assumption_details.append({
            "type": "assumption",
            "id": a.id,
            "code": a.code,
            "review_status": a.review_status,
            "objectives": obj_count,
            "sfrs": sfr_count,
            "tests": test_count,
            "confirmed_tests": confirmed_tests,
            "chain_status": chain_status,
        })

    # Build OSP details
    osp_details = []
    for o in osps:
        status_dist[o.review_status] = status_dist.get(o.review_status, 0) + 1
        chain_status = compute_chain_status(o.id, osp_obj_map)

        obj_ids = osp_obj_map.get(o.id, set())
        obj_count = len(obj_ids)
        sfr_ids: set[str] = set()
        for oid in obj_ids:
            sfr_ids.update(obj_sfr_map.get(oid, set()))
        sfr_count = len(sfr_ids)
        test_statuses: list[str] = []
        for sid in sfr_ids:
            test_statuses.extend(sfr_test_map.get(sid, []))
        test_count = len(test_statuses)
        confirmed_tests = sum(1 for s in test_statuses if s == "confirmed")

        osp_details.append({
            "type": "osp",
            "id": o.id,
            "code": o.code,
            "review_status": o.review_status,
            "objectives": obj_count,
            "sfrs": sfr_count,
            "tests": test_count,
            "confirmed_tests": confirmed_tests,
            "chain_status": chain_status,
        })

    # Combine all security problems
    all_problems = threat_details + assumption_details + osp_details

    # Total risk score (critical=4, high=3, medium=2, low=1)
    weights = {"critical": 4, "high": 3, "medium": 2, "low": 1}
    score = sum(weights.get(t.risk_level, 1) for t in threats if t.review_status == "confirmed")
    confirmed_count = status_dist.get("confirmed", 0)
    overall_level = (
        "critical" if score >= confirmed_count * 3.5
        else "high" if score >= confirmed_count * 2.5
        else "medium" if score >= confirmed_count * 1.5
        else "low"
    ) if confirmed_count > 0 else "low"

    # Cache
    cache_res = await db.exec(
        select(TOERiskCache).where(TOERiskCache.toe_id == toe_id)
    )
    cache = cache_res.first()
    ai_summary = cache.ai_summary if cache else None

    return {
        "code": 0,
        "data": {
            "risk_distribution": risk_dist,
            "status_distribution": status_dist,
            "residual_distribution": residual_dist,
            "total_threats": len(threats),
            "total_assumptions": len(assumptions),
            "total_osps": len(osps),
            "risk_score": score,
            "overall_risk_level": overall_level,
            "ai_summary": ai_summary,
            "security_problems": all_problems,
        },
    }


# ── Assurance Chain Tree ──

@router.get("/toes/{toe_id}/assurance-chain-tree")
async def get_assurance_chain_tree(
    toe_id: str,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    """
    Return a 5-level tree:
      Asset → Threat/Assumption/OSP → Objective → SFR → TestCase
    with full link information so the frontend can draw connecting lines
    and highlight related nodes on click.
    """
    from app.models.toe import TOEAsset
    from app.models.threat import Assumption, OSP, ThreatAssetLink
    from app.models.security import (
        SecurityObjective, SFR, ObjectiveSFR,
        ThreatObjective, AssumptionObjective, OSPObjective,
    )
    from app.models.test_case import TestCase

    await _get_toe(toe_id, current_user, db, writable=False)

    # ── 1. Fetch all entities ──
    assets = (await db.exec(
        select(TOEAsset).where(TOEAsset.toe_id == toe_id, TOEAsset.deleted_at.is_(None))
    )).all()
    threats = (await db.exec(
        select(Threat).where(Threat.toe_id == toe_id, Threat.deleted_at.is_(None))
    )).all()
    assumptions = (await db.exec(
        select(Assumption).where(Assumption.toe_id == toe_id, Assumption.deleted_at.is_(None))
    )).all()
    osps = (await db.exec(
        select(OSP).where(OSP.toe_id == toe_id, OSP.deleted_at.is_(None))
    )).all()
    objectives = (await db.exec(
        select(SecurityObjective).where(
            SecurityObjective.toe_id == toe_id,
            SecurityObjective.deleted_at.is_(None),
        )
    )).all()
    sfrs = (await db.exec(
        select(SFR).where(SFR.toe_id == toe_id, SFR.deleted_at.is_(None))
    )).all()
    tests = (await db.exec(
        select(TestCase).where(TestCase.toe_id == toe_id, TestCase.deleted_at.is_(None))
    )).all()

    # ── 2. Fetch all link tables ──
    threat_ids = [t.id for t in threats]
    assumption_ids = [a.id for a in assumptions]
    osp_ids = [o.id for o in osps]
    objective_ids = [o.id for o in objectives]

    # Asset ↔ Threat
    asset_threat_links = []
    if threat_ids:
        asset_threat_links = (await db.exec(
            select(ThreatAssetLink).where(
                ThreatAssetLink.threat_id.in_(threat_ids)  # type: ignore
            )
        )).all()

    # Threat → Objective
    threat_obj_links = []
    if threat_ids:
        threat_obj_links = (await db.exec(
            select(ThreatObjective).where(
                ThreatObjective.threat_id.in_(threat_ids)  # type: ignore
            )
        )).all()

    # Assumption → Objective
    assumption_obj_links = []
    if assumption_ids:
        assumption_obj_links = (await db.exec(
            select(AssumptionObjective).where(
                AssumptionObjective.assumption_id.in_(assumption_ids)  # type: ignore
            )
        )).all()

    # OSP → Objective
    osp_obj_links = []
    if osp_ids:
        osp_obj_links = (await db.exec(
            select(OSPObjective).where(
                OSPObjective.osp_id.in_(osp_ids)  # type: ignore
            )
        )).all()

    # Objective → SFR
    obj_sfr_links = []
    if objective_ids:
        obj_sfr_links = (await db.exec(
            select(ObjectiveSFR).where(
                ObjectiveSFR.objective_id.in_(objective_ids)  # type: ignore
            )
        )).all()

    # SFR → Test (via primary_sfr_id)
    sfr_ids = [s.id for s in sfrs]
    sfr_test_links = []
    for tc in tests:
        if tc.primary_sfr_id in sfr_ids:
            sfr_test_links.append({"sfr_id": tc.primary_sfr_id, "test_id": tc.id})

    # ── 3. Build node lists ──
    asset_nodes = [{"id": a.id, "label": a.name, "type": "asset"} for a in assets]

    problem_nodes = []
    for t in threats:
        problem_nodes.append({
            "id": t.id, "label": t.code, "type": "threat",
            "risk_level": t.risk_level, "review_status": t.review_status,
        })
    for a in assumptions:
        problem_nodes.append({
            "id": a.id, "label": a.code, "type": "assumption",
            "review_status": a.review_status,
        })
    for o in osps:
        problem_nodes.append({
            "id": o.id, "label": o.code, "type": "osp",
            "review_status": o.review_status,
        })

    objective_nodes = [
        {"id": o.id, "label": o.code, "type": "objective", "obj_type": o.obj_type}
        for o in objectives
    ]
    sfr_nodes = [
        {"id": s.id, "label": s.sfr_id, "type": "sfr", "review_status": s.review_status}
        for s in sfrs
    ]
    test_nodes = [
        {"id": tc.id, "label": tc.case_number or tc.id[:8], "type": "test",
         "review_status": tc.review_status}
        for tc in tests
    ]

    # ── 4. Build edges ──
    edges = []
    for link in asset_threat_links:
        edges.append({"from": link.asset_id, "to": link.threat_id, "type": "asset_problem"})
    for link in threat_obj_links:
        edges.append({"from": link.threat_id, "to": link.objective_id, "type": "problem_objective"})
    for link in assumption_obj_links:
        edges.append({"from": link.assumption_id, "to": link.objective_id, "type": "problem_objective"})
    for link in osp_obj_links:
        edges.append({"from": link.osp_id, "to": link.objective_id, "type": "problem_objective"})
    for link in obj_sfr_links:
        edges.append({"from": link.objective_id, "to": link.sfr_id, "type": "objective_sfr"})
    for link in sfr_test_links:
        edges.append({"from": link["sfr_id"], "to": link["test_id"], "type": "sfr_test"})

    # SFR → SFR (dependency relationships)
    _sfr_id_re = re.compile(r'[A-Za-z]{2,4}_[A-Za-z]{2,4}(?:\.\d+)+')
    sfr_id_to_uuid = {s.sfr_id.upper(): s.id for s in sfrs if s.sfr_id}
    for s in sfrs:
        if not s.dependency:
            continue
        dep_ids = _sfr_id_re.findall(s.dependency)
        for dep_id in dep_ids:
            dep_uuid = sfr_id_to_uuid.get(dep_id.upper())
            if dep_uuid and dep_uuid != s.id:
                edges.append({"from": s.id, "to": dep_uuid, "type": "sfr_dependency"})

    return {
        "code": 0,
        "data": {
            "layers": [
                {"key": "asset", "nodes": asset_nodes},
                {"key": "problem", "nodes": problem_nodes},
                {"key": "objective", "nodes": objective_nodes},
                {"key": "sfr", "nodes": sfr_nodes},
                {"key": "test", "nodes": test_nodes},
            ],
            "edges": edges,
        },
    }


# ── Risk blind spots (quality-based risk indicators) ──

@router.get("/toes/{toe_id}/risk-blind-spots")
async def get_risk_blind_spots(
    toe_id: str,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    """
    Compute quality-based risk indicators that chain completeness cannot reveal.
    These highlight potential blind spots: missed assets, shallow threat coverage,
    insufficient SFRs, etc.
    """
    from app.models.toe import TOEAsset
    from app.models.threat import Threat, ThreatAssetLink, STReference
    from app.models.security import SecurityObjective, SFR, ObjectiveSFR
    from app.models.test_case import TestCase
    import json

    await _get_toe(toe_id, current_user, db, writable=False)

    # ── Gather raw data ──
    assets_res = await db.exec(
        select(TOEAsset).where(TOEAsset.toe_id == toe_id, TOEAsset.deleted_at.is_(None))
    )
    assets = assets_res.all()

    threats_res = await db.exec(
        select(Threat).where(Threat.toe_id == toe_id, Threat.deleted_at.is_(None))
    )
    threats = threats_res.all()

    links_res = await db.exec(
        select(ThreatAssetLink).where(
            ThreatAssetLink.threat_id.in_([t.id for t in threats])  # type: ignore
        )
    ) if threats else None
    threat_asset_links = links_res.all() if links_res else []

    objectives_res = await db.exec(
        select(SecurityObjective).where(
            SecurityObjective.toe_id == toe_id,
            SecurityObjective.deleted_at.is_(None),
        )
    )
    objectives = objectives_res.all()

    sfrs_res = await db.exec(
        select(SFR).where(SFR.toe_id == toe_id, SFR.deleted_at.is_(None))
    )
    sfrs = sfrs_res.all()

    obj_sfr_res = await db.exec(
        select(ObjectiveSFR).where(
            ObjectiveSFR.objective_id.in_([o.id for o in objectives])  # type: ignore
        )
    ) if objectives else None
    obj_sfr_links = obj_sfr_res.all() if obj_sfr_res else []

    tests_res = await db.exec(
        select(TestCase).where(TestCase.toe_id == toe_id, TestCase.deleted_at.is_(None))
    )
    tests = tests_res.all()

    st_refs_res = await db.exec(
        select(STReference).where(
            STReference.toe_id == toe_id,
            STReference.parse_status == "done",
        )
    )
    st_refs = st_refs_res.all()

    # ── 1. Asset Identification Risk ──
    asset_types_present = set(a.asset_type for a in assets)
    expected_types = {"data", "function", "privacy", "config"}
    missing_types = expected_types - asset_types_present
    high_importance_assets = [a for a in assets if a.importance >= 4]

    # Count threats per asset
    asset_threat_count: dict[str, int] = {}
    for link in threat_asset_links:
        asset_threat_count[link.asset_id] = asset_threat_count.get(link.asset_id, 0) + 1

    high_assets_shallow = [
        a for a in high_importance_assets
        if asset_threat_count.get(a.id, 0) < 2
    ]

    asset_indicators = []
    if len(assets) == 0:
        asset_indicators.append({
            "level": "critical",
            "message": "no_assets_identified",
        })
    else:
        if missing_types:
            asset_indicators.append({
                "level": "high" if len(missing_types) >= 3 else "medium",
                "message": "missing_asset_types",
                "detail": sorted(missing_types),
            })
        if high_assets_shallow:
            asset_indicators.append({
                "level": "high",
                "message": "high_importance_shallow_coverage",
                "detail": [{"name": a.name, "importance": a.importance, "threat_count": asset_threat_count.get(a.id, 0)} for a in high_assets_shallow[:5]],
            })

    # ── 2. Threat Identification Risk ──
    confirmed_threats = [t for t in threats if t.review_status == "confirmed"]
    false_positive_threats = [t for t in threats if t.review_status == "false_positive"]
    pending_threats = [t for t in threats if t.review_status == "pending"]

    threats_per_asset = (len(threats) / len(assets)) if assets else 0

    # Reference comparison
    ref_threat_count = 0
    for ref in st_refs:
        if ref.threats_extracted:
            try:
                extracted = json.loads(ref.threats_extracted)
                if isinstance(extracted, list):
                    ref_threat_count += len(extracted)
            except (json.JSONDecodeError, TypeError):
                pass
    avg_ref_threats = (ref_threat_count / len(st_refs)) if st_refs else None

    threat_indicators = []
    if len(threats) == 0:
        threat_indicators.append({
            "level": "critical",
            "message": "no_threats_identified",
        })
    else:
        if threats_per_asset < 1.5 and len(assets) > 0:
            threat_indicators.append({
                "level": "medium",
                "message": "low_threat_density",
                "detail": {"threats_per_asset": round(threats_per_asset, 1)},
            })
        if len(pending_threats) > 0:
            pending_pct = round(len(pending_threats) / len(threats) * 100)
            if pending_pct >= 30:
                threat_indicators.append({
                    "level": "high" if pending_pct >= 60 else "medium",
                    "message": "high_pending_ratio",
                    "detail": {"pending_count": len(pending_threats), "pending_pct": pending_pct},
                })
        if len(false_positive_threats) > 0:
            fp_pct = round(len(false_positive_threats) / len(threats) * 100)
            if fp_pct >= 30:
                threat_indicators.append({
                    "level": "high" if fp_pct >= 50 else "medium",
                    "message": "high_false_positive_ratio",
                    "detail": {"fp_count": len(false_positive_threats), "fp_pct": fp_pct},
                })
        if avg_ref_threats is not None and len(confirmed_threats) < avg_ref_threats * 0.5:
            threat_indicators.append({
                "level": "medium",
                "message": "below_reference_benchmark",
                "detail": {
                    "current_threats": len(confirmed_threats),
                    "avg_reference": round(avg_ref_threats),
                },
            })

    # ── 3. SFR Adequacy Risk ──
    o_objectives = [o for o in objectives if o.obj_type == "O"]
    sfr_per_obj: dict[str, int] = {}
    for link in obj_sfr_links:
        sfr_per_obj[link.objective_id] = sfr_per_obj.get(link.objective_id, 0) + 1

    objectives_single_sfr = [
        o for o in o_objectives if sfr_per_obj.get(o.id, 0) == 1
    ]
    objectives_no_sfr = [
        o for o in o_objectives if sfr_per_obj.get(o.id, 0) == 0
    ]
    custom_sfrs = [s for s in sfrs if s.source == "custom"]
    sfrs_with_dep_warning = [s for s in sfrs if s.dependency_warning]
    draft_sfrs = [s for s in sfrs if s.review_status == "draft"]

    sfr_indicators = []
    if len(sfrs) == 0 and len(o_objectives) > 0:
        sfr_indicators.append({
            "level": "critical",
            "message": "no_sfrs_defined",
        })
    else:
        if objectives_single_sfr and len(o_objectives) > 0:
            pct = round(len(objectives_single_sfr) / len(o_objectives) * 100)
            if pct >= 50:
                sfr_indicators.append({
                    "level": "medium",
                    "message": "objectives_single_sfr",
                    "detail": {
                        "count": len(objectives_single_sfr),
                        "pct": pct,
                        "examples": [o.code for o in objectives_single_sfr[:3]],
                    },
                })
        if custom_sfrs:
            custom_pct = round(len(custom_sfrs) / len(sfrs) * 100) if sfrs else 0
            if custom_pct >= 30:
                sfr_indicators.append({
                    "level": "medium",
                    "message": "high_custom_sfr_ratio",
                    "detail": {"custom_count": len(custom_sfrs), "custom_pct": custom_pct},
                })
        if sfrs_with_dep_warning:
            sfr_indicators.append({
                "level": "medium",
                "message": "sfrs_dependency_warnings",
                "detail": {"count": len(sfrs_with_dep_warning)},
            })
        if draft_sfrs:
            draft_pct = round(len(draft_sfrs) / len(sfrs) * 100) if sfrs else 0
            if draft_pct >= 40:
                sfr_indicators.append({
                    "level": "high" if draft_pct >= 70 else "medium",
                    "message": "high_draft_sfr_ratio",
                    "detail": {"draft_count": len(draft_sfrs), "draft_pct": draft_pct},
                })

    # ── 4. Test Depth Risk ──
    test_types_present: set[str] = set()
    for tc in tests:
        try:
            parsed = json.loads(tc.test_type) if tc.test_type else []
            if isinstance(parsed, list):
                test_types_present.update(parsed)
            else:
                test_types_present.add(tc.test_type)
        except Exception:
            test_types_present.add(tc.test_type)
    expected_test_types = {"coverage", "depth", "independent"}
    missing_test_types = expected_test_types - test_types_present
    confirmed_tests = [tc for tc in tests if tc.review_status == "confirmed"]
    tests_no_steps = [tc for tc in tests if not tc.test_steps or not tc.expected_result]
    sfr_ids_with_tests = set(tc.primary_sfr_id for tc in tests)
    sfrs_without_any_test = [s for s in sfrs if s.id not in sfr_ids_with_tests]

    test_indicators = []
    if len(tests) == 0 and len(sfrs) > 0:
        test_indicators.append({
            "level": "critical",
            "message": "no_tests_defined",
        })
    else:
        if missing_test_types and len(tests) > 0:
            test_indicators.append({
                "level": "low" if len(missing_test_types) == 1 else "medium",
                "message": "missing_test_types",
                "detail": sorted(missing_test_types),
            })
        if len(tests) > 0 and len(sfrs) > 0:
            tests_per_sfr = len(tests) / len(sfrs)
            if tests_per_sfr < 1.0:
                test_indicators.append({
                    "level": "high",
                    "message": "low_test_sfr_ratio",
                    "detail": {"ratio": round(tests_per_sfr, 1)},
                })
        if tests_no_steps:
            test_indicators.append({
                "level": "medium",
                "message": "tests_missing_detail",
                "detail": {"count": len(tests_no_steps)},
            })

    # ── Aggregate confidence ──
    all_indicators = asset_indicators + threat_indicators + sfr_indicators + test_indicators
    critical_count = sum(1 for i in all_indicators if i["level"] == "critical")
    high_count = sum(1 for i in all_indicators if i["level"] == "high")
    medium_count = sum(1 for i in all_indicators if i["level"] == "medium")

    if critical_count > 0:
        overall_confidence = "low"
    elif high_count >= 2:
        overall_confidence = "low"
    elif high_count >= 1 or medium_count >= 3:
        overall_confidence = "medium"
    elif medium_count >= 1:
        overall_confidence = "high"
    else:
        overall_confidence = "very_high"

    return {
        "code": 0,
        "data": {
            "overall_confidence": overall_confidence,
            "dimensions": {
                "asset_identification": {
                    "indicators": asset_indicators,
                    "stats": {
                        "total_assets": len(assets),
                        "type_coverage": f"{len(asset_types_present)}/{len(expected_types)}",
                        "high_importance_count": len(high_importance_assets),
                    },
                },
                "threat_identification": {
                    "indicators": threat_indicators,
                    "stats": {
                        "total_threats": len(threats),
                        "confirmed": len(confirmed_threats),
                        "pending": len(pending_threats),
                        "false_positive": len(false_positive_threats),
                        "threats_per_asset": round(threats_per_asset, 1),
                        "reference_benchmark": round(avg_ref_threats) if avg_ref_threats else None,
                    },
                },
                "sfr_adequacy": {
                    "indicators": sfr_indicators,
                    "stats": {
                        "total_sfrs": len(sfrs),
                        "custom_sfrs": len(custom_sfrs),
                        "objectives_with_single_sfr": len(objectives_single_sfr),
                        "dep_warnings": len(sfrs_with_dep_warning),
                    },
                },
                "test_depth": {
                    "indicators": test_indicators,
                    "stats": {
                        "total_tests": len(tests),
                        "confirmed_tests": len(confirmed_tests),
                        "test_type_coverage": f"{len(test_types_present)}/{len(expected_test_types)}",
                        "sfrs_without_tests": len(sfrs_without_any_test),
                    },
                },
            },
        },
    }


@router.post("/toes/{toe_id}/risk-summary/generate")
async def generate_risk_summary(
    toe_id: str,
    payload: dict = {},
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    await _get_toe(toe_id, current_user, db)
    language = ((payload or {}).get("language") or "en").lower()
    if language not in ("zh", "en"):
        language = "en"
    task = AITask(
        user_id=current_user.id,
        toe_id=toe_id,
        task_type="risk_summary",
        status="pending",
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)

    from app.worker.worker import arq_pool
    await arq_pool.enqueue_job("risk_summary_task", toe_id, task.id, language)
    return {"code": 0, "data": {"task_id": task.id}}


# ── Blind Spot AI Suggestions ──

@router.get("/toes/{toe_id}/blind-spot-suggestions")
async def list_blind_spot_suggestions(
    toe_id: str,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    from app.models.risk import BlindSpotSuggestion
    await _get_toe(toe_id, current_user, db, writable=False)
    results = (await db.exec(
        select(BlindSpotSuggestion).where(
            BlindSpotSuggestion.toe_id == toe_id,
            BlindSpotSuggestion.deleted_at.is_(None),
        ).order_by(BlindSpotSuggestion.created_at)
    )).all()
    return {
        "code": 0,
        "data": [
            {"id": s.id, "category": s.category, "content": s.content, "is_ignored": s.is_ignored}
            for s in results
        ],
    }


@router.post("/toes/{toe_id}/blind-spot-suggestions/generate")
async def generate_blind_spot_suggestions(
    toe_id: str,
    payload: dict = {},
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    await _get_toe(toe_id, current_user, db)
    language = ((payload or {}).get("language") or "en").lower()
    if language not in ("zh", "en"):
        language = "en"
    task = AITask(
        user_id=current_user.id,
        toe_id=toe_id,
        task_type="blind_spot_suggestions",
        status="pending",
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)

    from app.worker.worker import arq_pool
    await arq_pool.enqueue_job("blind_spot_suggestions_task", toe_id, task.id, current_user.id, language)
    return {"code": 0, "data": {"task_id": task.id}}


@router.patch("/toes/{toe_id}/blind-spot-suggestions/{suggestion_id}/ignore")
async def toggle_ignore_suggestion(
    toe_id: str,
    suggestion_id: str,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    from app.models.risk import BlindSpotSuggestion
    await _get_toe(toe_id, current_user, db)
    result = await db.exec(
        select(BlindSpotSuggestion).where(
            BlindSpotSuggestion.id == suggestion_id,
            BlindSpotSuggestion.toe_id == toe_id,
            BlindSpotSuggestion.deleted_at.is_(None),
        )
    )
    suggestion = result.first()
    if not suggestion:
        raise HTTPException(status_code=404, detail="Suggestion not found")
    suggestion.is_ignored = not suggestion.is_ignored
    db.add(suggestion)
    await db.commit()
    return {"code": 0, "data": {"id": suggestion.id, "is_ignored": suggestion.is_ignored}}
