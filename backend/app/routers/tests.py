"""
Test management routes.
- TestCase CRUD
- Review actions
- Basic AI generation fallback without worker dependencies
- Test completeness report
"""
import json
from collections import defaultdict
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.auth import get_current_user
from app.core.database import get_db, AsyncSessionLocal
from app.core.response import NotFoundError, ok, validate_batch_ids
from app.core.toe_permissions import get_accessible_toe
from app.models.ai_task import AITask
from app.models.base import utcnow
from app.models.security import ObjectiveSFR, SFR, SecurityObjective
from app.models.test_case import TestCase
from app.models.toe import TOE
from app.models.user import User
from app.services.ai_service import get_ai_service

router = APIRouter(prefix="/api/toes/{toe_id}", tags=["Test Management"])


async def _get_user_toe(toe_id: str, user: User, db: AsyncSession, writable: bool = True) -> TOE:
    return await get_accessible_toe(toe_id, user, db, writable=writable)


async def _get_test_case(test_case_id: str, toe_id: str, db: AsyncSession) -> TestCase:
    item = (
        await db.exec(
            select(TestCase).where(
                TestCase.id == test_case_id,
                TestCase.toe_id == toe_id,
                TestCase.deleted_at.is_(None),
            )
        )
    ).first()
    if not item:
            raise NotFoundError("Test case not found")
    return item


def _parse_related_ids(raw_value: Optional[str]) -> list[str]:
    if not raw_value:
        return []
    try:
        parsed = json.loads(raw_value)
    except Exception:
        return []
    if not isinstance(parsed, list):
        return []
    return [item for item in parsed if isinstance(item, str) and item]


def _normalize_related_ids(raw_value: object) -> str:
    if raw_value is None:
        return "[]"
    if isinstance(raw_value, str):
        value = raw_value.strip()
        if not value:
            return "[]"
        try:
            parsed = json.loads(value)
        except Exception as exc:
            raise HTTPException(400, f"Invalid related_sfr_ids format: {exc}") from exc
    elif isinstance(raw_value, list):
        parsed = raw_value
    else:
        raise HTTPException(400, "related_sfr_ids must be a JSON array")

    if not isinstance(parsed, list):
        raise HTTPException(400, "related_sfr_ids must be a JSON array")

    normalized = []
    seen: set[str] = set()
    for item in parsed:
        if not isinstance(item, str):
            continue
        candidate = item.strip()
        if candidate and candidate not in seen:
            normalized.append(candidate)
            seen.add(candidate)
    return json.dumps(normalized, ensure_ascii=True)


def _compact_text(value: Optional[str], limit: int = 100) -> str:
    if not value:
        return "-"
    compact = " ".join(value.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3] + "..."


VALID_TEST_TYPES = {"coverage", "depth", "independent"}


def _normalize_test_type(raw_value: object) -> str:
    """Accept a JSON array, a comma-separated string, or a single value.
    Always return a JSON array string like '["coverage","independent"]'.
    """
    if raw_value is None:
        return json.dumps(["independent"])

    items: list[str] = []
    if isinstance(raw_value, list):
        items = raw_value
    elif isinstance(raw_value, str):
        value = raw_value.strip()
        if not value:
            return json.dumps(["independent"])
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                items = parsed
            else:
                items = [value]
        except Exception:
            items = [v.strip() for v in value.split(",")]
    else:
        raise HTTPException(400, "Invalid test_type format")

    normalized = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, str):
            continue
        candidate = item.strip().lower()
        if candidate and candidate in VALID_TEST_TYPES and candidate not in seen:
            normalized.append(candidate)
            seen.add(candidate)

    if not normalized:
        return json.dumps(["independent"])
    return json.dumps(normalized, ensure_ascii=True)


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


def _build_finding(key: str, severity: str, items: list[dict]) -> dict:
    visible = items[:8]
    return {
        "key": key,
        "severity": severity,
        "count": len(items),
        "items": visible,
        "overflow": max(0, len(items) - len(visible)),
    }


def _weighted_score(metrics: list[dict]) -> int:
    applicable = [item["percent"] for item in metrics if item["status"] != "not_applicable"]
    if not applicable:
        return 100
    return int(round(sum(applicable) / len(applicable)))


def _review_summary(status: str) -> tuple[str, Optional[str]]:
    if status == "confirmed":
        return "Confirmed", "success"
    if status == "rejected":
        return "Rejected", "error"
    return "Pending review", None


def _serialize_test_case(item: TestCase, sfr_label_map: dict[str, str]) -> dict:
    related_ids = _parse_related_ids(item.related_sfr_ids)
    review_label, _ = _review_summary(item.review_status)
    return {
        "id": item.id,
        "case_number": item.case_number,
        "toe_id": item.toe_id,
        "primary_sfr_id": item.primary_sfr_id,
        "primary_sfr_label": sfr_label_map.get(item.primary_sfr_id, item.primary_sfr_id),
        "related_sfr_ids": item.related_sfr_ids or "[]",
        "related_sfr_labels": [sfr_label_map.get(sfr_id, sfr_id) for sfr_id in related_ids],
        "test_type": item.test_type,
        "title": item.title,
        "objective": item.objective,
        "test_target": item.test_target,
        "test_scenario": item.test_scenario,
        "precondition": item.precondition,
        "test_steps": item.test_steps,
        "expected_result": item.expected_result,
        "review_status": item.review_status,
        "review_status_label": review_label,
        "ai_generated": item.ai_generated,
        "reviewed_at": item.reviewed_at.isoformat() if item.reviewed_at else None,
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


async def _load_sfrs(toe_id: str, db: AsyncSession) -> list[SFR]:
    return (
        await db.exec(
            select(SFR).where(
                SFR.toe_id == toe_id,
                SFR.deleted_at.is_(None),
            ).order_by(SFR.created_at)
        )
    ).all()


async def _load_test_cases(toe_id: str, db: AsyncSession) -> list[TestCase]:
    return (
        await db.exec(
            select(TestCase).where(
                TestCase.toe_id == toe_id,
                TestCase.deleted_at.is_(None),
            ).order_by(TestCase.created_at.desc())
        )
    ).all()


@router.get("/test-cases")
async def list_test_cases(
    toe_id: str,
    sfr_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_user_toe(toe_id, current_user, db, writable=False)
    sfrs = await _load_sfrs(toe_id, db)
    sfr_label_map = {item.id: item.sfr_id for item in sfrs}
    items = await _load_test_cases(toe_id, db)

    if sfr_id:
        filtered: list[TestCase] = []
        for item in items:
            related_ids = _parse_related_ids(item.related_sfr_ids)
            if item.primary_sfr_id == sfr_id or sfr_id in related_ids:
                filtered.append(item)
        items = filtered

    return ok(data=[_serialize_test_case(item, sfr_label_map) for item in items])


@router.post("/test-cases")
async def create_test_case(
    toe_id: str,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_user_toe(toe_id, current_user, db, writable=True)
    title = (payload.get("title") or "").strip()
    primary_sfr_id = (payload.get("primary_sfr_id") or "").strip()
    raw_test_type = payload.get("test_type")
    test_type = _normalize_test_type(raw_test_type)

    if not title:
        raise HTTPException(400, "Test title cannot be empty")
    if not primary_sfr_id:
        raise HTTPException(400, "A primary SFR must be selected")

    sfr = (
        await db.exec(
            select(SFR).where(
                SFR.id == primary_sfr_id,
                SFR.toe_id == toe_id,
                SFR.deleted_at.is_(None),
            )
        )
    ).first()
    if not sfr:
        raise HTTPException(400, "Primary SFR not found")

    item = TestCase(
        toe_id=toe_id,
        case_number=(payload.get("case_number") or None),
        primary_sfr_id=primary_sfr_id,
        related_sfr_ids=_normalize_related_ids(payload.get("related_sfr_ids")),
        test_type=test_type,
        title=title,
        objective=(payload.get("objective") or None),
        test_target=(payload.get("test_target") or None),
        test_scenario=(payload.get("test_scenario") or None),
        precondition=(payload.get("precondition") or None),
        test_steps=(payload.get("test_steps") or None),
        expected_result=(payload.get("expected_result") or None),
        review_status=payload.get("review_status") or "draft",
        ai_generated=bool(payload.get("ai_generated", False)),
    )
    db.add(item)
    await db.flush()

    return ok(data=_serialize_test_case(item, {sfr.id: sfr.sfr_id}), msg="Created successfully")


@router.put("/test-cases/{test_case_id}")
async def update_test_case(
    toe_id: str,
    test_case_id: str,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_user_toe(toe_id, current_user, db, writable=True)
    item = await _get_test_case(test_case_id, toe_id, db)

    if "title" in payload:
        title = (payload.get("title") or "").strip()
        if not title:
            raise HTTPException(400, "Test title cannot be empty")
        item.title = title

    if "primary_sfr_id" in payload:
        primary_sfr_id = (payload.get("primary_sfr_id") or "").strip()
        sfr = (
            await db.exec(
                select(SFR).where(
                    SFR.id == primary_sfr_id,
                    SFR.toe_id == toe_id,
                    SFR.deleted_at.is_(None),
                )
            )
        ).first()
        if not sfr:
                raise HTTPException(400, "Primary SFR not found")
        item.primary_sfr_id = primary_sfr_id

    if "test_type" in payload:
        item.test_type = _normalize_test_type(payload.get("test_type"))

    if "case_number" in payload:
        item.case_number = (payload.get("case_number") or "").strip() or None

    if "related_sfr_ids" in payload:
        item.related_sfr_ids = _normalize_related_ids(payload.get("related_sfr_ids"))

    for field in ["objective", "test_target", "test_scenario", "precondition", "test_steps", "expected_result"]:
        if field in payload:
            setattr(item, field, payload.get(field) or None)

    item.updated_at = utcnow()
    db.add(item)

    sfrs = await _load_sfrs(toe_id, db)
    sfr_label_map = {sfr.id: sfr.sfr_id for sfr in sfrs}
    return ok(data=_serialize_test_case(item, sfr_label_map), msg="Updated successfully")


@router.delete("/test-cases/{test_case_id}")
async def delete_test_case(
    toe_id: str,
    test_case_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_user_toe(toe_id, current_user, db, writable=True)
    item = await _get_test_case(test_case_id, toe_id, db)
    item.soft_delete()
    db.add(item)
    return ok(msg="Deleted successfully")


async def _update_review_status(toe_id: str, test_case_id: str, review_status: str, db: AsyncSession) -> dict:
    item = await _get_test_case(test_case_id, toe_id, db)
    item.review_status = review_status
    item.reviewed_at = utcnow() if review_status != "draft" else None
    item.updated_at = utcnow()
    db.add(item)
    sfrs = await _load_sfrs(toe_id, db)
    return _serialize_test_case(item, {sfr.id: sfr.sfr_id for sfr in sfrs})


@router.post("/test-cases/{test_case_id}/confirm")
async def confirm_test_case(
    toe_id: str,
    test_case_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_user_toe(toe_id, current_user, db, writable=True)
    return ok(data=await _update_review_status(toe_id, test_case_id, "confirmed", db))


@router.post("/test-cases/{test_case_id}/reject")
async def reject_test_case(
    toe_id: str,
    test_case_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_user_toe(toe_id, current_user, db, writable=True)
    return ok(data=await _update_review_status(toe_id, test_case_id, "rejected", db))


@router.post("/test-cases/batch-confirm")
async def batch_confirm_test_cases(
    toe_id: str,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_user_toe(toe_id, current_user, db, writable=True)
    ids = validate_batch_ids(payload.get("ids") or [])
    if not ids:
        raise HTTPException(400, "ids cannot be empty")
    sfrs = await _load_sfrs(toe_id, db)
    sfr_label_map = {sfr.id: sfr.sfr_id for sfr in sfrs}
    updated = []
    for test_case_id in ids:
        item = (await db.exec(
            select(TestCase).where(
                TestCase.id == test_case_id,
                TestCase.toe_id == toe_id,
                TestCase.deleted_at.is_(None),
            )
        )).first()
        if item:
            item.review_status = "confirmed"
            item.reviewed_at = utcnow()
            item.updated_at = utcnow()
            db.add(item)
            updated.append(_serialize_test_case(item, sfr_label_map))
            return ok(data=updated, msg=f"Confirmed {len(updated)} test cases")


@router.post("/test-cases/batch-delete")
async def batch_delete_test_cases(
    toe_id: str,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_user_toe(toe_id, current_user, db, writable=True)
    ids = validate_batch_ids(payload.get("ids") or [])
    if not ids:
        raise HTTPException(400, "ids cannot be empty")
    deleted_count = 0
    for test_case_id in ids:
        item = (await db.exec(
            select(TestCase).where(
                TestCase.id == test_case_id,
                TestCase.toe_id == toe_id,
                TestCase.deleted_at.is_(None),
            )
        )).first()
        if item:
            item.soft_delete()
            db.add(item)
            deleted_count += 1
    return ok(msg=f"Deleted {deleted_count} test cases")


@router.post("/test-cases/{test_case_id}/revert")
async def revert_test_case(
    toe_id: str,
    test_case_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_user_toe(toe_id, current_user, db, writable=True)
    return ok(data=await _update_review_status(toe_id, test_case_id, "draft", db))


@router.post("/test-cases/ai-generate")
async def ai_generate_test_cases(
    toe_id: str,
    payload: dict,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_user_toe(toe_id, current_user, db, writable=True)
    sfr_ids = payload.get("sfr_ids") or []
    language = (payload.get("language") or "en").lower()
    if language not in ("zh", "en"):
        language = "en"
    if not isinstance(sfr_ids, list):
        sfr_ids = []

    task = AITask(
        user_id=current_user.id,
        toe_id=toe_id,
        task_type="test_gen",
        status="pending",
        progress_message="Starting...",
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    task_id = task.id

    background_tasks.add_task(
        _background_generate_test_cases,
        task_id=task_id,
        toe_id=toe_id,
        user_id=current_user.id,
        sfr_ids=sfr_ids,
        language=language,
    )
    return ok(data={"task_id": task_id})


async def _background_generate_test_cases(
    task_id: str,
    toe_id: str,
    user_id: str,
    sfr_ids: list,
    language: str = "en",
):
    async with AsyncSessionLocal() as db:
        async def _set_progress(msg: str):
            t = (await db.exec(select(AITask).where(AITask.id == task_id))).first()
            if t:
                t.progress_message = msg
                db.add(t)
                await db.commit()

        try:
            sfrs = await _load_sfrs(toe_id, db)
            items = await _load_test_cases(toe_id, db)

            covered_ids: set[str] = set()
            for item in items:
                covered_ids.add(item.primary_sfr_id)
                covered_ids.update(_parse_related_ids(item.related_sfr_ids))

            targets = [sfr for sfr in sfrs if not sfr_ids or sfr.id in sfr_ids]
            uncovered = [sfr for sfr in targets if sfr.id not in covered_ids]

            total = len(uncovered)
            created_count = 0

            # Fetch user record for AI service
            from app.models.user import User as UserModel
            user = (await db.exec(select(UserModel).where(UserModel.id == user_id))).first()
            if not user:
                raise Exception("User not found")

            ai = await get_ai_service(db, user_id)

            for i, sfr in enumerate(uncovered):
                await _set_progress(f"{i + 1}/{total}: {sfr.sfr_id}")

                if ai:
                    output_language = "Chinese" if language == "zh" else "English"
                    prompt = f"""You are a CC (Common Criteria) security testing expert. Generate 1-2 appropriate test cases for the following SFR.

SFR ID: {sfr.sfr_id}
Description: {sfr.sfr_detail or '(no description)'}
Rationale: {sfr.ai_rationale or '(none)'}

For each test case, provide:
- title: a descriptive test case name
- objective: the test purpose (1-2 sentences)
- test_target: what specific component or function is being tested
- test_scenario: the testing context and environment
- precondition: preconditions before the test
- test_steps: numbered test steps (1. ... 2. ... 3. ...)
- expected_result: what the expected outcome is

Return a JSON array:
[{{
  "title": "...",
  "objective": "...",
  "test_target": "...",
  "test_scenario": "...",
  "precondition": "...",
  "test_steps": "...",
  "expected_result": "..."
}}]

Return ONLY the JSON array.
All user-facing text fields must be written in {output_language}."""
                    try:
                        results = await ai.chat_json(prompt, max_tokens=2048)
                        if not isinstance(results, list):
                            results = []
                    except Exception:
                        results = []

                    for tc_data in results:
                        if not isinstance(tc_data, dict):
                            continue
                        title = (tc_data.get("title") or "").strip() or f"Test {sfr.sfr_id}"
                        tc = TestCase(
                            toe_id=toe_id,
                            primary_sfr_id=sfr.id,
                            related_sfr_ids=json.dumps([sfr.id]),
                            test_type="independent",
                            title=title,
                            objective=tc_data.get("objective") or None,
                            test_target=tc_data.get("test_target") or None,
                            test_scenario=tc_data.get("test_scenario") or None,
                            precondition=tc_data.get("precondition") or None,
                            test_steps=tc_data.get("test_steps") or None,
                            expected_result=tc_data.get("expected_result") or None,
                            review_status="draft",
                            ai_generated=True,
                        )
                        db.add(tc)
                        created_count += 1
                    await db.commit()
                else:
                    # Fallback: template when no AI configured
                    tc = TestCase(
                        toe_id=toe_id,
                        primary_sfr_id=sfr.id,
                        related_sfr_ids=json.dumps([sfr.id]),
                        test_type="independent",
                        title=f"Test {sfr.sfr_id} implementation",
                        objective=f"Verify that the TOE correctly implements {sfr.sfr_id}.",
                        test_target=f"The TOE's enforcement of {sfr.sfr_id}.",
                        test_scenario="Standard operational environment with the security function active.",
                        precondition="TOE is installed and operational. All prerequisites for the security function are met.",
                        test_steps=(
                            f"1. Configure the test environment for {sfr.sfr_id}.\n"
                            "2. Trigger the relevant security function.\n"
                            "3. Observe the TOE response and collect evidence."
                        ),
                        expected_result=f"The TOE behavior conforms to {sfr.sfr_id}.",
                        review_status="draft",
                        ai_generated=True,
                    )
                    db.add(tc)
                    created_count += 1
                    await db.commit()

            t = (await db.exec(select(AITask).where(AITask.id == task_id))).first()
            if t:
                t.status = "done"
                t.progress_message = f"Completed {total} SFR(s)"
                t.result_summary = f"Generated {created_count} test case(s)"
                t.finished_at = utcnow()
                db.add(t)
                await db.commit()

        except Exception as exc:
            async with AsyncSessionLocal() as db2:
                t = (await db2.exec(select(AITask).where(AITask.id == task_id))).first()
                if t:
                    t.status = "failed"
                    t.error_message = str(exc)
                    t.finished_at = utcnow()
                    db2.add(t)
                    await db2.commit()


@router.get("/test-cases/completeness-report")
async def get_test_completeness_report(
    toe_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _get_user_toe(toe_id, current_user, db, writable=False)
    sfrs = await _load_sfrs(toe_id, db)
    tests = await _load_test_cases(toe_id, db)

    sfr_label_map = {sfr.id: sfr.sfr_id for sfr in sfrs}
    all_sfr_ids = [sfr.id for sfr in sfrs]
    coverage_map: dict[str, list[TestCase]] = defaultdict(list)
    confirmed_coverage_map: dict[str, list[TestCase]] = defaultdict(list)

    for test_case in tests:
        linked_ids = [test_case.primary_sfr_id, *_parse_related_ids(test_case.related_sfr_ids)]
        for sfr_id in linked_ids:
            coverage_map[sfr_id].append(test_case)
            if test_case.review_status == "confirmed":
                confirmed_coverage_map[sfr_id].append(test_case)

    covered_sfr_count = sum(1 for sfr_id in all_sfr_ids if coverage_map.get(sfr_id))
    confirmed_covered_sfr_count = sum(1 for sfr_id in all_sfr_ids if confirmed_coverage_map.get(sfr_id))

    metrics = [
        _build_metric("sfr_test_coverage", covered_sfr_count, len(all_sfr_ids)),
        _build_metric("confirmed_sfr_test_coverage", confirmed_covered_sfr_count, len(all_sfr_ids)),
    ]

    sfrs_without_tests = [
        {"id": sfr.id, "label": sfr.sfr_id, "detail": "No linked test case."}
        for sfr in sfrs
        if not coverage_map.get(sfr.id)
    ]
    sfrs_without_confirmed_tests = [
        {"id": sfr.id, "label": sfr.sfr_id, "detail": "No confirmed test case."}
        for sfr in sfrs
        if not confirmed_coverage_map.get(sfr.id)
    ]
    tests_without_steps = [
        {"id": test_case.id, "label": test_case.title, "detail": _compact_text(test_case.objective)}
        for test_case in tests
        if not (test_case.test_steps or "").strip()
    ]

    objective_rows = (
        await db.exec(
            select(ObjectiveSFR, SecurityObjective).join(
                SecurityObjective,
                ObjectiveSFR.objective_id == SecurityObjective.id,
            ).where(
                SecurityObjective.toe_id == toe_id,
                SecurityObjective.deleted_at.is_(None),
            )
        )
    ).all()

    objective_type_to_sfr_ids: dict[str, set[str]] = {"O": set(), "OE": set()}
    for objective_sfr, objective in objective_rows:
        objective_type_to_sfr_ids.setdefault(objective.obj_type, set()).add(objective_sfr.sfr_id)

    mapping_gap_sections = []
    for objective_type in ["O", "OE"]:
        scoped_ids = objective_type_to_sfr_ids.get(objective_type, set())
        gap_items = [
            {"id": sfr_id, "label": sfr_label_map.get(sfr_id, sfr_id), "detail": "No linked test case."}
            for sfr_id in sorted(scoped_ids, key=lambda item: sfr_label_map.get(item, item))
            if not coverage_map.get(sfr_id)
        ]
        confirmed_gap_items = [
            {"id": sfr_id, "label": sfr_label_map.get(sfr_id, sfr_id), "detail": "No confirmed test case."}
            for sfr_id in sorted(scoped_ids, key=lambda item: sfr_label_map.get(item, item))
            if not confirmed_coverage_map.get(sfr_id)
        ]
        mapping_gap_sections.append({
            "key": "sfr_to_tests",
            "source_type": "sfr",
            "objective_type": objective_type,
            "covered": len(scoped_ids) - len(gap_items),
            "total": len(scoped_ids),
            "gaps": gap_items[:8],
            "overflow": max(0, len(gap_items) - 8),
        })
        mapping_gap_sections.append({
            "key": "sfr_to_confirmed_tests",
            "source_type": "sfr",
            "objective_type": objective_type,
            "covered": len(scoped_ids) - len(confirmed_gap_items),
            "total": len(scoped_ids),
            "gaps": confirmed_gap_items[:8],
            "overflow": max(0, len(confirmed_gap_items) - 8),
        })

    findings = [
        _build_finding("sfrs_without_tests", "high", sfrs_without_tests),
        _build_finding("sfrs_without_confirmed_tests", "medium", sfrs_without_confirmed_tests),
        _build_finding("tests_without_steps", "medium", tests_without_steps),
    ]
    total_findings = sum(item["count"] for item in findings)
    high_findings = sum(item["count"] for item in findings if item["severity"] == "high")
    score = _weighted_score(metrics)
    if score >= 85:
        status = "good"
    elif score >= 60:
        status = "attention"
    else:
        status = "weak"

    next_actions: list[str] = []
    if sfrs_without_tests:
        next_actions.append("Generate or add tests for uncovered SFRs.")
    if sfrs_without_confirmed_tests:
        next_actions.append("Review and confirm at least one test for each SFR.")
    if tests_without_steps:
        next_actions.append("Fill in missing test steps for incomplete test cases.")
    if not next_actions:
        next_actions.append("Current test coverage is complete for the tracked SFR set.")

    return ok(data={
        "summary": {
            "score": score,
            "status": status,
            "total_findings": total_findings,
            "high_findings": high_findings,
            "generated_at": utcnow().isoformat(),
            "basis_note": "Based on SFR coverage, confirmed review status, and test step completeness.",
        },
        "basis": {
            "sfr_count": len(sfrs),
            "test_count": len(tests),
            "confirmed_test_count": sum(1 for item in tests if item.review_status == "confirmed"),
        },
        "metrics": metrics,
        "mapping_gap_sections": mapping_gap_sections,
        "findings": findings,
        "next_actions": next_actions,
    })