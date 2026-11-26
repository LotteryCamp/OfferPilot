"""Candidate plan persistence and read models."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from datetime import date, datetime
from typing import Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import func, insert, select, update
from sqlalchemy.orm import Session

from backend.basis import (
    CRITICAL_BASIS_GAP_TYPES,
    build_basis_input,
    compute_basis_version,
    is_source_basis_usable,
)
from backend.errors import ApiError
from backend.identity import CurrentUser
from backend.schemas import CandidatePlanCreate, CandidatePlanItemInput
from backend.services import facts as fact_service
from backend.services.common import (
    iso,
    require_matter,
    serialize_task_row,
    transaction,
    uuid_text,
)
from backend.tables import (
    candidate_plan,
    candidate_plan_decision,
    candidate_plan_item,
    candidate_plan_item_source,
    matter,
    requirement,
    requirement_self_check,
    snapshot,
    source,
    task,
    v_plan_detail,
)


def create_plan(
    session: Session,
    current_user: CurrentUser,
    matter_id: UUID,
    body: CandidatePlanCreate,
    *,
    now: datetime,
    timezone: ZoneInfo,
    expected_fact_versions: Mapping[str, int | None] | None = None,
) -> dict[str, Any]:
    with transaction(session, current_user):
        require_matter(session, current_user, matter_id, for_update=True)
        fact_service.assert_fact_versions(session, matter_id, expected_fact_versions)
        _normalize_deadlines(body.items, timezone)
        _validate_requirements(session, matter_id, body.items)
        _validate_sources(session, body.items)

        next_version = (
            session.execute(
                select(func.max(candidate_plan.c.version_no)).where(
                    candidate_plan.c.matter_id == matter_id
                )
            ).scalar_one_or_none()
            or 0
        ) + 1
        plan_id = uuid4()
        session.execute(
            insert(candidate_plan).values(
                id=plan_id,
                matter_id=matter_id,
                version_no=next_version,
                status="draft",
                basis_version="0" * 64,
                basis_input={},
                generated_at=now,
                confirmed_at=None,
                expired_at=None,
                confirmed_by=None,
                op_id=None,
            )
        )

        item_ids = {item.client_item_id: uuid4() for item in body.items}
        for seq, item in enumerate(body.items, start=1):
            session.execute(
                insert(candidate_plan_item).values(
                    id=item_ids[item.client_item_id],
                    plan_id=plan_id,
                    seq=seq,
                    title=item.title,
                    detail=item.detail,
                    obligation_nature=item.obligation_nature,
                    official_deadline_date=item.official_deadline_date,
                    official_deadline_at=item.official_deadline_at,
                    suggested_date=item.suggested_date,
                    depends_on_item_ids=[],
                    evidence_required=item.evidence_required,
                    requirement_id=item.requirement_id,
                    created_at=now,
                )
            )
        for item in body.items:
            session.execute(
                update(candidate_plan_item)
                .where(candidate_plan_item.c.id == item_ids[item.client_item_id])
                .values(
                    depends_on_item_ids=[
                        item_ids[dependency] for dependency in item.depends_on
                    ]
                )
            )
        for item in body.items:
            for item_source in item.sources:
                session.execute(
                    insert(candidate_plan_item_source).values(
                        id=uuid4(),
                        plan_item_id=item_ids[item.client_item_id],
                        source_id=item_source.source_id,
                        snapshot_id=item_source.snapshot_id,
                        locator_kind=item_source.locator_kind,
                        locator=item_source.locator,
                        quote=item_source.quote,
                    )
                )
        session.flush()

        basis_input = collect_basis_input(session, matter_id, plan_id)
        session.execute(
            update(candidate_plan)
            .where(candidate_plan.c.id == plan_id)
            .values(
                basis_version=compute_basis_version(basis_input),
                basis_input=basis_input,
                status="pending",
            )
        )
        return _plan_detail(
            session,
            plan_id,
            current_user.workspace_id,
        )


def list_plans(
    session: Session, current_user: CurrentUser, matter_id: UUID
) -> dict[str, Any]:
    with transaction(session, current_user):
        require_matter(session, current_user, matter_id)
        rows = (
            session.execute(
                select(
                    v_plan_detail,
                    candidate_plan.c.basis_input,
                    candidate_plan_decision.c.decision.label("decision_value"),
                    candidate_plan_decision.c.decided_at.label("decision_at"),
                    candidate_plan_decision.c.decided_by.label("decision_by"),
                    candidate_plan_decision.c.operation_id.label(
                        "decision_operation_id"
                    ),
                )
                .join(candidate_plan, candidate_plan.c.id == v_plan_detail.c.id)
                .outerjoin(
                    candidate_plan_decision,
                    candidate_plan_decision.c.plan_id == v_plan_detail.c.id,
                )
                .where(v_plan_detail.c.matter_id == matter_id)
                .order_by(v_plan_detail.c.version_no.desc())
            )
            .mappings()
            .all()
        )
        states = fact_service.plan_basis_states(session, rows)
        plans = []
        for row in rows:
            basis_status, stale_facts = states[row["id"]]
            plans.append(
                {
                    "id": uuid_text(row["id"]),
                    "matter_id": uuid_text(row["matter_id"]),
                    "version_no": row["version_no"],
                    "status": row["status"],
                    "basis_version": row["basis_version"],
                    "basis_status": basis_status,
                    "stale_facts": stale_facts,
                    "generated_at": iso(row["generated_at"]),
                    "confirmed_at": iso(row["confirmed_at"]),
                    "expired_at": iso(row["expired_at"]),
                    "item_count": row["item_count"],
                    "requirement_linked_count": row["requirement_linked_count"],
                    "source_count": row["source_count"],
                    "decision": (
                        {
                            "decision": row["decision_value"],
                            "decided_by": uuid_text(row["decision_by"]),
                            "decided_at": iso(row["decision_at"]),
                            "operation_id": uuid_text(row["decision_operation_id"]),
                        }
                        if row["decision_value"] is not None
                        else None
                    ),
                }
            )
        return {"plans": plans}


def get_plan(
    session: Session, current_user: CurrentUser, plan_id: UUID
) -> dict[str, Any]:
    with transaction(session, current_user):
        return _plan_detail(
            session,
            plan_id,
            current_user.workspace_id,
        )


def basis_states_for_plan_ids(
    session: Session,
    current_user: CurrentUser,
    plan_ids: set[UUID],
) -> dict[UUID, tuple[str, list[dict[str, Any]]]]:
    if not plan_ids:
        return {}
    rows = (
        session.execute(
            select(
                candidate_plan.c.id,
                candidate_plan.c.matter_id,
                candidate_plan.c.status,
                candidate_plan.c.basis_input,
            )
            .join(matter, matter.c.id == candidate_plan.c.matter_id)
            .where(
                candidate_plan.c.id.in_(plan_ids),
                matter.c.workspace_id == current_user.workspace_id,
            )
        )
        .mappings()
        .all()
    )
    return fact_service.plan_basis_states(session, rows)


def collect_basis_input(
    session: Session, matter_id: UUID, plan_id: UUID
) -> dict[str, Any]:
    matter_row = (
        session.execute(select(matter).where(matter.c.id == matter_id)).mappings().one()
    )
    requirement_rows = (
        session.execute(
            select(requirement)
            .where(
                requirement.c.matter_id == matter_id,
                requirement.c.extract_status != "rejected",
            )
            .order_by(requirement.c.id)
        )
        .mappings()
        .all()
    )
    used_snapshot_ids = (
        select(requirement.c.snapshot_id)
        .where(
            requirement.c.matter_id == matter_id,
            requirement.c.extract_status != "rejected",
        )
        .union(
            select(candidate_plan_item_source.c.snapshot_id)
            .join(
                candidate_plan_item,
                candidate_plan_item.c.id == candidate_plan_item_source.c.plan_item_id,
            )
            .where(candidate_plan_item.c.plan_id == plan_id)
        )
    )
    source_rows = (
        session.execute(
            select(
                source.c.id.label("source_id"),
                source.c.status,
                snapshot.c.id.label("snapshot_id"),
                snapshot.c.version_no,
                snapshot.c.content_hash,
                snapshot.c.is_current,
                snapshot.c.fetched_at,
            )
            .join(snapshot, snapshot.c.source_id == source.c.id)
            .where(snapshot.c.id.in_(used_snapshot_ids))
            .order_by(source.c.id, snapshot.c.id)
        )
        .mappings()
        .all()
    )
    relevant_fact_types = fact_service.relevant_fact_types(session, matter_id)
    fact_rows = fact_service.current_fact_entries(
        session, matter_id, relevant_fact_types
    )
    return build_basis_input(
        matter_row=matter_row,
        requirement_rows=requirement_rows,
        source_rows=source_rows,
        fact_rows=fact_rows,
    )


def basis_source_ids(session: Session, matter_id: UUID, plan_id: UUID) -> list[UUID]:
    item_source_ids = (
        session.execute(
            select(candidate_plan_item_source.c.source_id)
            .join(
                candidate_plan_item,
                candidate_plan_item.c.id == candidate_plan_item_source.c.plan_item_id,
            )
            .where(candidate_plan_item.c.plan_id == plan_id)
        )
        .scalars()
        .all()
    )
    requirement_source_ids = (
        session.execute(
            select(snapshot.c.source_id)
            .join(requirement, requirement.c.snapshot_id == snapshot.c.id)
            .where(
                requirement.c.matter_id == matter_id,
                requirement.c.extract_status != "rejected",
            )
        )
        .scalars()
        .all()
    )
    return sorted({*item_source_ids, *requirement_source_ids})


def lock_basis_sources(session: Session, matter_id: UUID, plan_id: UUID) -> None:
    source_ids = basis_source_ids(session, matter_id, plan_id)
    if source_ids:
        session.execute(
            select(source.c.id)
            .where(source.c.id.in_(source_ids))
            .order_by(source.c.id)
            .with_for_update()
        )


def current_basis_source_issues(
    session: Session, matter_id: UUID, plan_id: UUID, *, today: date
) -> list[str]:
    used_snapshot_ids = (
        select(requirement.c.snapshot_id)
        .where(
            requirement.c.matter_id == matter_id,
            requirement.c.extract_status != "rejected",
        )
        .union(
            select(candidate_plan_item_source.c.snapshot_id)
            .join(
                candidate_plan_item,
                candidate_plan_item.c.id == candidate_plan_item_source.c.plan_item_id,
            )
            .where(candidate_plan_item.c.plan_id == plan_id)
        )
    )
    rows = session.execute(
        select(
            source.c.id.label("source_id"),
            source.c.status,
            source.c.auto_check_status,
            source.c.roi_status,
            source.c.valid_to,
            snapshot.c.is_current,
        )
        .join(snapshot, snapshot.c.source_id == source.c.id)
        .where(snapshot.c.id.in_(used_snapshot_ids))
    ).mappings()
    issues: list[str] = []
    for row in rows:
        if not is_source_basis_usable(
            status=row["status"],
            auto_check_status=row["auto_check_status"],
            roi_status=row["roi_status"],
            is_current=row["is_current"],
            valid_to=row["valid_to"],
            today=today,
        ):
            issues.append(uuid_text(row["source_id"]) or "")
    return sorted({source_id for source_id in issues if source_id})


def current_basis_gap_issues(session: Session, matter_id: UUID) -> list[dict[str, Any]]:
    rows = session.execute(
        select(requirement_self_check.c.gaps)
        .join(
            requirement,
            requirement.c.id == requirement_self_check.c.requirement_id,
        )
        .where(
            requirement.c.matter_id == matter_id,
            requirement.c.extract_status != "rejected",
        )
    ).scalars()
    issues: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for gaps in rows:
        for gap in gaps or []:
            gap_type = str(gap.get("gap_type", ""))
            if gap_type not in CRITICAL_BASIS_GAP_TYPES:
                continue
            description = str(gap.get("description", ""))
            key = (gap_type, description)
            if key in seen:
                continue
            seen.add(key)
            issues.append(
                {
                    "gap_type": gap_type,
                    "description": description,
                    "locator": gap.get("locator"),
                }
            )
    return issues


def _normalize_deadlines(
    items: list[CandidatePlanItemInput], timezone: ZoneInfo
) -> None:
    for item in items:
        if item.official_deadline_at is None:
            continue
        local_date = item.official_deadline_at.astimezone(timezone).date()
        if item.official_deadline_date is None:
            item.official_deadline_date = local_date
        elif item.official_deadline_date != local_date:
            raise ApiError(
                422,
                "validation_error",
                "official_deadline_date 与 official_deadline_at 的日期不一致",
                next_step=f"按 {timezone} 时区核对官方期限日期",
                details={"client_item_id": item.client_item_id},
            )


def _validate_requirements(
    session: Session, matter_id: UUID, items: list[CandidatePlanItemInput]
) -> None:
    requirement_ids = {
        item.requirement_id for item in items if item.requirement_id is not None
    }
    if not requirement_ids:
        return
    found = set(
        session.execute(
            select(requirement.c.id).where(
                requirement.c.matter_id == matter_id,
                requirement.c.id.in_(requirement_ids),
            )
        ).scalars()
    )
    missing = requirement_ids - found
    if missing:
        raise ApiError(
            422,
            "unknown_requirement",
            "候选计划引用了不属于当前事项的要求",
            next_step="核对 requirement_id",
            details={"missing": sorted(str(value) for value in missing)},
        )


def _validate_sources(session: Session, items: list[CandidatePlanItemInput]) -> None:
    pairs = {
        (item_source.source_id, item_source.snapshot_id)
        for item in items
        for item_source in item.sources
    }
    if not pairs:
        return
    source_ids = {pair[0] for pair in pairs}
    snapshot_ids = {pair[1] for pair in pairs}
    rows = (
        session.execute(
            select(
                source.c.id.label("source_id"),
                source.c.status,
                snapshot.c.id.label("snapshot_id"),
                snapshot.c.is_current,
                snapshot.c.source_id.label("snapshot_source_id"),
            )
            .join(snapshot, snapshot.c.source_id == source.c.id)
            .where(
                source.c.id.in_(source_ids),
                snapshot.c.id.in_(snapshot_ids),
            )
        )
        .mappings()
        .all()
    )
    found = {(row["source_id"], row["snapshot_id"]): row for row in rows}
    for source_id, snapshot_id in pairs:
        row = found.get((source_id, snapshot_id))
        if row is None or row["snapshot_source_id"] != source_id:
            raise ApiError(
                422,
                "unknown_source_snapshot",
                "候选计划引用的来源快照不存在或与来源不一致",
                next_step="核对 source_id 与 snapshot_id",
            )
        if row["status"] != "active" or not row["is_current"]:
            raise ApiError(
                422,
                "source_unavailable",
                "候选计划引用的来源当前不可用",
                next_step="重新检索并登记当前快照后生成新候选",
            )


def _plan_detail(
    session: Session,
    plan_id: UUID,
    workspace_id: UUID,
) -> dict[str, Any]:
    plan_row = (
        session.execute(
            select(candidate_plan)
            .join(matter, matter.c.id == candidate_plan.c.matter_id)
            .where(
                candidate_plan.c.id == plan_id,
                matter.c.workspace_id == workspace_id,
            )
        )
        .mappings()
        .first()
    )
    if plan_row is None:
        raise ApiError(
            404,
            "plan_not_found",
            "未找到当前工作区中的候选计划",
            next_step="刷新候选计划列表后重试",
        )
    basis_status, stale_facts = fact_service.plan_basis_state(session, plan_row)
    matter_row = (
        session.execute(select(matter).where(matter.c.id == plan_row["matter_id"]))
        .mappings()
        .one()
    )

    item_rows = (
        session.execute(
            select(candidate_plan_item)
            .where(candidate_plan_item.c.plan_id == plan_id)
            .order_by(candidate_plan_item.c.seq)
        )
        .mappings()
        .all()
    )
    item_ids = [row["id"] for row in item_rows]

    source_rows = []
    if item_ids:
        source_rows = (
            session.execute(
                select(
                    candidate_plan_item_source.c.plan_item_id,
                    candidate_plan_item_source.c.id.label("item_source_id"),
                    candidate_plan_item_source.c.locator_kind,
                    candidate_plan_item_source.c.locator,
                    candidate_plan_item_source.c.quote,
                    source.c.id.label("source_id"),
                    source.c.publisher,
                    source.c.url,
                    source.c.status.label("source_status"),
                    snapshot.c.id.label("snapshot_id"),
                    snapshot.c.version_no,
                    snapshot.c.content_hash,
                    snapshot.c.fetched_at,
                    snapshot.c.is_current,
                )
                .join(source, source.c.id == candidate_plan_item_source.c.source_id)
                .join(
                    snapshot,
                    snapshot.c.id == candidate_plan_item_source.c.snapshot_id,
                )
                .where(candidate_plan_item_source.c.plan_item_id.in_(item_ids))
                .order_by(
                    candidate_plan_item_source.c.plan_item_id,
                    source.c.id,
                    snapshot.c.id,
                )
            )
            .mappings()
            .all()
        )
    sources_by_item: dict[UUID, list[dict[str, Any]]] = defaultdict(list)
    for row in source_rows:
        sources_by_item[row["plan_item_id"]].append(
            {
                "id": uuid_text(row["item_source_id"]),
                "source_id": uuid_text(row["source_id"]),
                "publisher": row["publisher"],
                "url": row["url"],
                "source_status": row["source_status"],
                "snapshot_id": uuid_text(row["snapshot_id"]),
                "version_no": row["version_no"],
                "content_hash": row["content_hash"],
                "fetched_at": iso(row["fetched_at"]),
                "is_current": row["is_current"],
                "locator_kind": row["locator_kind"],
                "locator": row["locator"],
                "quote": row["quote"],
            }
        )

    requirement_ids = {
        row["requirement_id"] for row in item_rows if row["requirement_id"] is not None
    }
    requirements_by_id: dict[UUID, dict[str, Any]] = {}
    self_check_by_requirement: dict[UUID, dict[str, Any]] = {}
    if requirement_ids:
        for row in session.execute(
            select(requirement).where(requirement.c.id.in_(requirement_ids))
        ).mappings():
            requirements_by_id[row["id"]] = {
                "id": uuid_text(row["id"]),
                "field_key": row["field_key"],
                "label": row["label"],
                "obligation_nature": row["obligation_nature"],
                "extract_status": row["extract_status"],
            }
        for row in session.execute(
            select(requirement_self_check).where(
                requirement_self_check.c.requirement_id.in_(requirement_ids)
            )
        ).mappings():
            self_check_by_requirement[row["requirement_id"]] = {
                "conclusion": row["conclusion"],
                "reason": row["reason"],
                "missing_fields": list(row["missing_fields"] or []),
                "computed_deadline_at": iso(row["computed_deadline_at"]),
                "gaps": list(row["gaps"] or []),
            }
        for requirement_id, summary in requirements_by_id.items():
            summary["self_check"] = self_check_by_requirement.get(requirement_id)

    decision_row = (
        session.execute(
            select(candidate_plan_decision).where(
                candidate_plan_decision.c.plan_id == plan_id
            )
        )
        .mappings()
        .first()
    )
    task_rows = (
        session.execute(
            select(task)
            .outerjoin(
                candidate_plan_item,
                candidate_plan_item.c.id == task.c.plan_item_id,
            )
            .where(task.c.plan_id == plan_id)
            .order_by(
                task.c.created_at,
                candidate_plan_item.c.seq.asc().nulls_last(),
                task.c.id,
            )
        )
        .mappings()
        .all()
    )

    items = []
    for row in item_rows:
        items.append(
            {
                "id": uuid_text(row["id"]),
                "seq": row["seq"],
                "title": row["title"],
                "detail": row["detail"],
                "obligation_nature": row["obligation_nature"],
                "official_deadline_date": iso(row["official_deadline_date"]),
                "official_deadline_at": iso(row["official_deadline_at"]),
                "suggested_date": iso(row["suggested_date"]),
                "depends_on_item_ids": [
                    str(value) for value in row["depends_on_item_ids"]
                ],
                "evidence_required": row["evidence_required"],
                "requirement_id": uuid_text(row["requirement_id"]),
                "created_at": iso(row["created_at"]),
                "requirement": requirements_by_id.get(row["requirement_id"]),
                "sources": sources_by_item.get(row["id"], []),
            }
        )

    return {
        "id": uuid_text(plan_row["id"]),
        "matter_id": uuid_text(plan_row["matter_id"]),
        "version_no": plan_row["version_no"],
        "status": plan_row["status"],
        "basis_version": plan_row["basis_version"],
        "basis_status": basis_status,
        "stale_facts": stale_facts,
        "generated_at": iso(plan_row["generated_at"]),
        "confirmed_at": iso(plan_row["confirmed_at"]),
        "expired_at": iso(plan_row["expired_at"]),
        "confirmed_by": uuid_text(plan_row["confirmed_by"]),
        "op_id": uuid_text(plan_row["op_id"]),
        "matter": {
            "id": uuid_text(matter_row["id"]),
            "goal": matter_row["goal"],
            "type_code": matter_row["type_code"],
            "scope_year": matter_row["scope_year"],
            "scope_attrs": matter_row["scope_attrs"],
        },
        "items": items,
        "decision": (
            {
                "id": uuid_text(decision_row["id"]),
                "decision": decision_row["decision"],
                "decided_by": uuid_text(decision_row["decided_by"]),
                "decided_at": iso(decision_row["decided_at"]),
                "operation_id": uuid_text(decision_row["operation_id"]),
            }
            if decision_row is not None
            else None
        ),
        "tasks": [serialize_task_row(row) for row in task_rows],
    }
