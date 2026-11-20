"""Candidate plan confirmation and rejection with idempotent writes."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import func, insert, select, update
from sqlalchemy.orm import Session

from backend.basis import compute_basis_version
from backend.config import Settings
from backend.errors import ApiError
from backend.services.common import iso, serialize_task_row, transaction, uuid_text
from backend.services.plans import (
    collect_basis_input,
    current_basis_gap_issues,
    current_basis_source_issues,
    lock_basis_sources,
)
from backend.tables import (
    candidate_plan,
    candidate_plan_decision,
    candidate_plan_item,
    matter,
    task,
)

DecisionValue = Literal["confirmed", "rejected"]


@dataclass(slots=True)
class DecisionResult:
    plan_id: UUID
    status: str
    decision: dict[str, Any] | None
    tasks: list[dict[str, Any]] = field(default_factory=list)
    replayed: bool = False
    expired: bool = False
    current_basis_version: str | None = None


def decide_plan(
    session: Session,
    settings: Settings,
    plan_id: UUID,
    *,
    decision: DecisionValue,
    operation_id: UUID,
    now: datetime,
) -> DecisionResult:
    with transaction(session, settings):
        session.execute(
            select(
                func.pg_advisory_xact_lock(
                    func.hashtext(f"offerpilot:workspace:{settings.demo_workspace_id}")
                )
            )
        )
        plan_row = (
            session.execute(
                select(candidate_plan)
                .join(matter, matter.c.id == candidate_plan.c.matter_id)
                .where(
                    candidate_plan.c.id == plan_id,
                    matter.c.workspace_id == settings.demo_workspace_id,
                )
                .with_for_update(of=candidate_plan)
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

        existing_operation = (
            session.execute(
                select(candidate_plan_decision).where(
                    candidate_plan_decision.c.operation_id == operation_id
                )
            )
            .mappings()
            .first()
        )
        if existing_operation is not None:
            if (
                existing_operation["plan_id"] != plan_id
                or existing_operation["decision"] != decision
            ):
                raise ApiError(
                    409,
                    "operation_conflict",
                    "该 Idempotency-Key 已用于其他计划或决定",
                    next_step="为新操作生成新的 Idempotency-Key",
                )
            return _replay_result(session, plan_id, existing_operation)

        existing_decision = (
            session.execute(
                select(candidate_plan_decision).where(
                    candidate_plan_decision.c.plan_id == plan_id
                )
            )
            .mappings()
            .first()
        )
        if existing_decision is not None:
            raise ApiError(
                409,
                "plan_already_decided",
                "候选计划已有终态决定",
                next_step="重新读取候选计划状态",
                details={
                    "status": plan_row["status"],
                    "decision": existing_decision["decision"],
                },
            )

        if plan_row["status"] == "expired":
            raise ApiError(
                409,
                "plan_expired",
                "候选计划依据已失效",
                next_step="重新生成候选计划后再确认或拒绝",
            )
        if plan_row["status"] != "pending":
            raise ApiError(
                409,
                "plan_not_pending",
                "只有待确认的候选计划可以作出决定",
                next_step="刷新候选计划状态",
                details={"status": plan_row["status"]},
            )

        if decision == "confirmed":
            return _confirm(
                session,
                settings,
                plan_row,
                operation_id=operation_id,
                now=now,
            )
        return _reject(
            session,
            settings,
            plan_row,
            operation_id=operation_id,
            now=now,
        )


def _confirm(
    session: Session,
    settings: Settings,
    plan_row: Any,
    *,
    operation_id: UUID,
    now: datetime,
) -> DecisionResult:
    plan_id = plan_row["id"]
    matter_id = plan_row["matter_id"]
    item_rows = (
        session.execute(
            select(candidate_plan_item)
            .where(candidate_plan_item.c.plan_id == plan_id)
            .order_by(candidate_plan_item.c.seq)
        )
        .mappings()
        .all()
    )

    lock_basis_sources(session, matter_id, plan_id)
    blocked = _first_expired_deadline(item_rows, now, ZoneInfo(settings.demo_timezone))
    if blocked is not None:
        raise ApiError(
            409,
            "official_deadline_passed",
            "候选计划包含已过的官方期限",
            next_step="重新核对来源与计划；该批次不再生成正式任务",
            details={
                "plan_item_id": str(blocked["id"]),
                "title": blocked["title"],
                "official_deadline_date": iso(blocked["official_deadline_date"]),
                "official_deadline_at": iso(blocked["official_deadline_at"]),
            },
        )

    current_basis = collect_basis_input(session, matter_id, plan_id)
    current_hash = compute_basis_version(current_basis)
    if current_hash != plan_row["basis_version"]:
        session.execute(
            update(candidate_plan)
            .where(candidate_plan.c.id == plan_id)
            .values(
                status="expired",
                expired_at=now,
                confirmed_at=None,
                confirmed_by=None,
                op_id=None,
            )
        )
        return DecisionResult(
            plan_id=plan_id,
            status="expired",
            decision=None,
            expired=True,
            current_basis_version=current_hash,
        )
    gap_issues = current_basis_gap_issues(session, matter_id)
    if gap_issues:
        raise ApiError(
            409,
            "basis_unresolved",
            "候选计划存在未解决的关键依据疑点",
            next_step="核对来源与要求中的缺口后重新生成候选计划",
            details={"gaps": gap_issues},
        )
    unavailable_source_ids = current_basis_source_issues(
        session,
        matter_id,
        plan_id,
        today=now.astimezone(ZoneInfo(settings.demo_timezone)).date(),
    )
    if unavailable_source_ids:
        raise ApiError(
            409,
            "source_unavailable",
            "候选计划引用的来源当前不可用",
            next_step="重新检索并登记当前快照后生成新候选",
            details={"source_ids": unavailable_source_ids},
        )

    session.execute(
        update(candidate_plan)
        .where(candidate_plan.c.id == plan_id)
        .values(
            status="confirmed",
            confirmed_at=now,
            expired_at=None,
            confirmed_by=settings.demo_user_id,
            op_id=operation_id,
        )
    )
    _insert_decision(
        session,
        plan_id=plan_id,
        decision="confirmed",
        decided_by=settings.demo_user_id,
        decided_at=now,
        operation_id=operation_id,
    )
    task_ids = {row["id"]: uuid4() for row in item_rows}
    for row in item_rows:
        session.execute(
            insert(task).values(
                id=task_ids[row["id"]],
                matter_id=matter_id,
                plan_id=plan_id,
                plan_item_id=row["id"],
                executor_id=settings.demo_user_id,
                title=row["title"],
                due_at=row["official_deadline_at"],
                official_deadline_date=row["official_deadline_date"],
                official_deadline_at=row["official_deadline_at"],
                suggested_date=row["suggested_date"],
                status="pending",
                completion_evidence=None,
                depends_on=[task_ids[value] for value in row["depends_on_item_ids"]]
                or None,
                created_at=now,
                updated_at=now,
            )
        )
    session.flush()
    decision_row = _load_decision(session, plan_id)
    return DecisionResult(
        plan_id=plan_id,
        status="confirmed",
        decision=_serialize_decision(decision_row),
        tasks=_load_tasks(session, plan_id),
    )


def _reject(
    session: Session,
    settings: Settings,
    plan_row: Any,
    *,
    operation_id: UUID,
    now: datetime,
) -> DecisionResult:
    plan_id = plan_row["id"]
    session.execute(
        update(candidate_plan)
        .where(candidate_plan.c.id == plan_id)
        .values(
            status="rejected",
            confirmed_at=None,
            expired_at=None,
            confirmed_by=None,
            op_id=None,
        )
    )
    _insert_decision(
        session,
        plan_id=plan_id,
        decision="rejected",
        decided_by=settings.demo_user_id,
        decided_at=now,
        operation_id=operation_id,
    )
    session.flush()
    decision_row = _load_decision(session, plan_id)
    return DecisionResult(
        plan_id=plan_id,
        status="rejected",
        decision=_serialize_decision(decision_row),
    )


def _replay_result(
    session: Session, plan_id: UUID, decision_row: Any
) -> DecisionResult:
    tasks = (
        _load_tasks(session, plan_id) if decision_row["decision"] == "confirmed" else []
    )
    return DecisionResult(
        plan_id=plan_id,
        status=decision_row["decision"],
        decision=_serialize_decision(decision_row),
        tasks=tasks,
        replayed=True,
    )


def _insert_decision(
    session: Session,
    *,
    plan_id: UUID,
    decision: str,
    decided_by: UUID,
    decided_at: datetime,
    operation_id: UUID,
) -> None:
    session.execute(
        insert(candidate_plan_decision).values(
            id=uuid4(),
            plan_id=plan_id,
            decision=decision,
            decided_by=decided_by,
            decided_at=decided_at,
            operation_id=operation_id,
        )
    )


def _load_decision(session: Session, plan_id: UUID) -> Any:
    return (
        session.execute(
            select(candidate_plan_decision).where(
                candidate_plan_decision.c.plan_id == plan_id
            )
        )
        .mappings()
        .one()
    )


def _load_tasks(session: Session, plan_id: UUID) -> list[dict[str, Any]]:
    rows = (
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
    return [serialize_task_row(row) for row in rows]


def _serialize_decision(row: Any) -> dict[str, Any]:
    return {
        "id": uuid_text(row["id"]),
        "plan_id": uuid_text(row["plan_id"]),
        "decision": row["decision"],
        "decided_by": uuid_text(row["decided_by"]),
        "decided_at": iso(row["decided_at"]),
        "operation_id": uuid_text(row["operation_id"]),
    }


def _first_expired_deadline(
    items: Sequence[Any], now: datetime, timezone: ZoneInfo
) -> Any | None:
    local_today = now.astimezone(timezone).date()
    for item in items:
        if (
            item["official_deadline_at"] is not None
            and now > item["official_deadline_at"]
        ):
            return item
        if (
            item["official_deadline_date"] is not None
            and local_today > item["official_deadline_date"]
        ):
            return item
    return None
