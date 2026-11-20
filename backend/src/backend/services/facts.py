"""Personal fact persistence, versioning, and basis-state helpers."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, insert, select, update
from sqlalchemy.orm import Session

from backend.basis import canonical_json
from backend.config import Settings
from backend.errors import ApiError
from backend.fact_types import (
    FactTypeSpec,
    FactValueError,
    get_fact_type,
    supported_fact_types,
)
from backend.schemas import FactSaveRequest
from backend.services.common import iso, transaction, uuid_text
from backend.tables import (
    candidate_plan,
    matter,
    requirement,
    requirement_self_check,
)
from backend.tables import (
    fact as fact_table,
)


def save_fact(
    session: Session,
    settings: Settings,
    fact_type: str,
    body: FactSaveRequest,
    *,
    now: datetime,
) -> dict[str, Any]:
    with transaction(session, settings):
        spec = _require_spec(fact_type)
        value_json = _normalize_value(spec, body.value)
        rendered = spec.render(value_json)
        scope = _normalize_scope(body.scope)
        value_hash = _value_hash(
            fact_type=fact_type,
            scope=scope,
            valid_from=body.valid_from,
            value_json=value_json,
            value_text=rendered.value_text,
        )
        owner_id = settings.demo_user_id
        session.execute(
            select(
                func.pg_advisory_xact_lock(
                    func.hashtext(f"offerpilot:fact:{owner_id}:{fact_type}")
                )
            )
        )
        current = _load_current(
            session, owner_id=owner_id, fact_type=fact_type, for_update=True
        )
        if current is not None and current["value_hash"] == value_hash:
            return {
                "fact": _serialize_fact(current),
                "created": False,
                "affected_plans": _affected_plans(
                    session,
                    settings,
                    fact_type=fact_type,
                    current_version=current["version_no"],
                ),
            }

        next_version = _next_version(session, owner_id, fact_type)
        fact_id = uuid4()
        if current is not None:
            session.execute(
                update(fact_table)
                .where(fact_table.c.id == current["id"])
                .values(confirm_status="superseded", superseded_at=now)
            )
        session.execute(
            insert(fact_table).values(
                id=fact_id,
                owner_id=owner_id,
                fact_type=fact_type,
                value_text=rendered.value_text,
                value_json=value_json,
                value_hash=value_hash,
                scope=scope,
                valid_from=body.valid_from,
                trust_level="self",
                confirm_status="confirmed",
                version_no=next_version,
                confirmed_at=now,
                superseded_at=None,
                created_at=now,
            )
        )
        session.flush()
        created = _load_current(
            session, owner_id=owner_id, fact_type=fact_type, for_update=False
        )
        assert created is not None
        return {
            "fact": _serialize_fact(created),
            "created": True,
            "affected_plans": _affected_plans(
                session,
                settings,
                fact_type=fact_type,
                current_version=next_version,
            ),
        }


def list_facts(session: Session, settings: Settings) -> dict[str, Any]:
    with transaction(session, settings):
        rows = (
            session.execute(
                select(fact_table)
                .where(
                    fact_table.c.owner_id == settings.demo_user_id,
                    fact_table.c.confirm_status == "confirmed",
                )
                .order_by(fact_table.c.fact_type)
            )
            .mappings()
            .all()
        )
        return {"facts": [_serialize_fact(row) for row in rows]}


def get_fact(session: Session, settings: Settings, fact_type: str) -> dict[str, Any]:
    with transaction(session, settings):
        _require_spec(fact_type)
        current = _load_current(
            session,
            owner_id=settings.demo_user_id,
            fact_type=fact_type,
            for_update=False,
        )
        versions = (
            session.execute(
                select(fact_table)
                .where(
                    fact_table.c.owner_id == settings.demo_user_id,
                    fact_table.c.fact_type == fact_type,
                )
                .order_by(fact_table.c.version_no.desc())
            )
            .mappings()
            .all()
        )
        return {
            "fact": _serialize_fact(current) if current is not None else None,
            "versions": [_serialize_fact(row) for row in versions],
        }


def relevant_fact_types(session: Session, matter_id: UUID) -> list[str]:
    field_keys = (
        session.execute(
            select(requirement.c.field_key).where(
                requirement.c.matter_id == matter_id,
                requirement.c.extract_status != "rejected",
            )
        )
        .scalars()
        .all()
    )
    missing_fields = session.execute(
        select(requirement_self_check.c.missing_fields)
        .join(
            requirement,
            requirement.c.id == requirement_self_check.c.requirement_id,
        )
        .where(
            requirement.c.matter_id == matter_id,
            requirement.c.extract_status != "rejected",
        )
    ).scalars()
    keys = {str(key) for key in field_keys if key}
    for fields in missing_fields:
        for key in fields or []:
            if key:
                keys.add(str(key))
    return sorted(keys)


def current_fact_map(
    session: Session,
    owner_id: UUID,
    fact_types: Iterable[str] | None = None,
) -> dict[str, Mapping[str, Any]]:
    statement = select(fact_table).where(
        fact_table.c.owner_id == owner_id,
        fact_table.c.confirm_status == "confirmed",
    )
    if fact_types is not None:
        types = sorted(set(fact_types))
        if not types:
            return {}
        statement = statement.where(fact_table.c.fact_type.in_(types))
    rows = session.execute(statement).mappings().all()
    return {row["fact_type"]: row for row in rows}


def current_fact_entries(
    session: Session,
    owner_id: UUID,
    fact_types: Iterable[str],
) -> list[dict[str, Any]]:
    current = current_fact_map(session, owner_id, fact_types)
    entries: list[dict[str, Any]] = []
    for fact_type in sorted(set(fact_types)):
        row = current.get(fact_type)
        entries.append(
            {
                "fact_type": fact_type,
                "fact_id": row["id"] if row is not None else None,
                "version_no": row["version_no"] if row is not None else None,
                "value_hash": row["value_hash"] if row is not None else None,
            }
        )
    return entries


def agent_fact_values(
    session: Session,
    owner_id: UUID,
    fact_types: Iterable[str],
) -> dict[str, Any]:
    current = current_fact_map(session, owner_id, fact_types)
    values: dict[str, Any] = {}
    for fact_type, row in current.items():
        spec = get_fact_type(fact_type)
        if spec is None:
            continue
        rendered = spec.render(row["value_json"])
        if rendered.agent_value is not None:
            values[fact_type] = rendered.agent_value
    return values


def expected_fact_versions(
    session: Session,
    owner_id: UUID,
    fact_types: Iterable[str],
) -> dict[str, int | None]:
    current = current_fact_map(session, owner_id, fact_types)
    return {
        fact_type: (current[fact_type]["version_no"] if fact_type in current else None)
        for fact_type in sorted(set(fact_types))
    }


def assert_fact_versions(
    session: Session,
    owner_id: UUID,
    expected: Mapping[str, int | None] | None,
) -> None:
    if not expected:
        return
    current = current_fact_map(session, owner_id, expected)
    stale: list[dict[str, Any]] = []
    for fact_type, expected_version in sorted(expected.items()):
        row = current.get(fact_type)
        current_version = row["version_no"] if row is not None else None
        if current_version != expected_version:
            stale.append(
                {
                    "fact_type": fact_type,
                    "stored_version_no": expected_version,
                    "current_version_no": current_version,
                    "current_fact_id": (
                        uuid_text(row["id"]) if row is not None else None
                    ),
                }
            )
    if stale:
        raise ApiError(
            409,
            "version_conflict",
            "运行依赖的事实版本已变化",
            next_step="重新发起运行，使用最新确认事实生成候选",
            details={"stale_facts": stale},
        )


def plan_basis_state(
    session: Session,
    plan_row: Mapping[str, Any],
    owner_id: UUID,
) -> tuple[str, list[dict[str, Any]]]:
    relevant = set(relevant_fact_types(session, plan_row["matter_id"]))
    current = current_fact_map(session, owner_id, relevant)
    return _basis_state(plan_row, relevant, current)


def plan_basis_states(
    session: Session,
    plans: Iterable[Mapping[str, Any]],
    owner_id: UUID,
) -> dict[UUID, tuple[str, list[dict[str, Any]]]]:
    plan_list = list(plans)
    relevant_by_matter: dict[UUID, set[str]] = {}
    all_types: set[str] = set()
    for plan in plan_list:
        matter_id = plan["matter_id"]
        if matter_id not in relevant_by_matter:
            relevant_by_matter[matter_id] = set(relevant_fact_types(session, matter_id))
        all_types.update(relevant_by_matter[matter_id])
    current = current_fact_map(session, owner_id, all_types)
    return {
        plan["id"]: _basis_state(
            plan,
            relevant_by_matter.get(plan["matter_id"], set()),
            current,
        )
        for plan in plan_list
    }


def stale_facts_for_plan(
    session: Session,
    plan_row: Mapping[str, Any],
    owner_id: UUID,
) -> list[dict[str, Any]]:
    relevant = set(relevant_fact_types(session, plan_row["matter_id"]))
    current = current_fact_map(session, owner_id, relevant)
    _, stale = _basis_state(plan_row, relevant, current)
    return stale


def _basis_state(
    plan_row: Mapping[str, Any],
    relevant: set[str],
    current: Mapping[str, Mapping[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    if plan_row["status"] != "pending" or not relevant:
        return "not_applicable", []
    entries = _stored_fact_entries(plan_row.get("basis_input"))
    stale: list[dict[str, Any]] = []
    for fact_type in sorted(relevant):
        entry = entries.get(fact_type)
        stored_version = entry.get("version_no") if entry is not None else None
        row = current.get(fact_type)
        current_version = row["version_no"] if row is not None else None
        if stored_version != current_version:
            stale.append(
                {
                    "fact_type": fact_type,
                    "stored_version_no": stored_version,
                    "current_version_no": current_version,
                    "current_fact_id": (
                        uuid_text(row["id"]) if row is not None else None
                    ),
                }
            )
    return ("stale" if stale else "current"), stale


def _stored_fact_entries(basis_input: Any) -> dict[str, Mapping[str, Any]]:
    if not isinstance(basis_input, dict):
        return {}
    raw = basis_input.get("confirmed_facts")
    if not isinstance(raw, list):
        return {}
    entries: dict[str, Mapping[str, Any]] = {}
    for item in raw:
        if isinstance(item, dict) and isinstance(item.get("fact_type"), str):
            entries[item["fact_type"]] = item
    return entries


def _affected_plans(
    session: Session,
    settings: Settings,
    *,
    fact_type: str,
    current_version: int,
) -> list[dict[str, Any]]:
    plan_rows = (
        session.execute(
            select(
                candidate_plan.c.id,
                candidate_plan.c.matter_id,
                candidate_plan.c.version_no,
                candidate_plan.c.basis_input,
            )
            .join(matter, matter.c.id == candidate_plan.c.matter_id)
            .where(
                candidate_plan.c.status == "pending",
                matter.c.workspace_id == settings.demo_workspace_id,
            )
            .order_by(candidate_plan.c.matter_id, candidate_plan.c.version_no.desc())
        )
        .mappings()
        .all()
    )
    relevant_by_matter: dict[UUID, set[str]] = {}
    affected: list[dict[str, Any]] = []
    for plan in plan_rows:
        entries = _stored_fact_entries(plan["basis_input"])
        if fact_type in entries:
            stored_version = entries[fact_type].get("version_no")
            if stored_version == current_version:
                continue
        else:
            matter_id = plan["matter_id"]
            if matter_id not in relevant_by_matter:
                relevant_by_matter[matter_id] = set(
                    relevant_fact_types(session, matter_id)
                )
            if fact_type not in relevant_by_matter[matter_id]:
                continue
            stored_version = None
        affected.append(
            {
                "plan_id": uuid_text(plan["id"]),
                "matter_id": uuid_text(plan["matter_id"]),
                "version_no": plan["version_no"],
                "stored_version_no": stored_version,
            }
        )
    return affected


def _require_spec(fact_type: str) -> FactTypeSpec:
    spec = get_fact_type(fact_type)
    if spec is None:
        raise ApiError(
            422,
            "unsupported_fact_type",
            "事实类型未注册",
            next_step="使用当前支持的事实类型",
            details={"supported_fact_types": supported_fact_types()},
        )
    return spec


def _normalize_value(spec: FactTypeSpec, value: Mapping[str, Any]) -> dict[str, Any]:
    try:
        return spec.normalize(value)
    except FactValueError as exc:
        raise ApiError(
            422,
            "invalid_fact_value",
            "事实值不合法",
            next_step="按 issues 修正事实值后重试",
            details={"issues": exc.issues},
        ) from exc


def _normalize_scope(scope: str | None) -> str | None:
    if scope is None:
        return None
    stripped = scope.strip()
    return stripped or None


def _value_hash(
    *,
    fact_type: str,
    scope: str | None,
    valid_from: Any,
    value_json: Mapping[str, Any],
    value_text: str,
) -> str:
    payload = {
        "fact_type": fact_type,
        "scope": scope,
        "valid_from": valid_from.isoformat() if valid_from is not None else None,
        "value_json": dict(value_json),
        "value_text": value_text,
    }
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _load_current(
    session: Session,
    *,
    owner_id: UUID,
    fact_type: str,
    for_update: bool,
) -> Mapping[str, Any] | None:
    statement = select(fact_table).where(
        fact_table.c.owner_id == owner_id,
        fact_table.c.fact_type == fact_type,
        fact_table.c.confirm_status == "confirmed",
    )
    if for_update:
        statement = statement.with_for_update()
    return session.execute(statement).mappings().first()


def _next_version(session: Session, owner_id: UUID, fact_type: str) -> int:
    current_max = session.execute(
        select(func.max(fact_table.c.version_no)).where(
            fact_table.c.owner_id == owner_id,
            fact_table.c.fact_type == fact_type,
        )
    ).scalar_one_or_none()
    return (current_max or 0) + 1


def _serialize_fact(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": uuid_text(row["id"]),
        "fact_type": row["fact_type"],
        "value": row["value_json"],
        "value_text": row["value_text"],
        "scope": row["scope"],
        "valid_from": iso(row["valid_from"]),
        "trust_level": row["trust_level"],
        "status": row["confirm_status"],
        "version_no": row["version_no"],
        "value_hash": row["value_hash"],
        "confirmed_at": iso(row["confirmed_at"]),
        "superseded_at": iso(row["superseded_at"]),
        "created_at": iso(row["created_at"]),
    }
