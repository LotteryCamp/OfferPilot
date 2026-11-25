"""Requirement and evidence persistence for extracted official rules."""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from backend.errors import ApiError
from backend.identity import CurrentUser
from backend.schemas import RequirementBatchCreate, RequirementInput
from backend.services.common import (
    iso,
    require_matter,
    transaction,
)
from backend.tables import (
    evidence,
    requirement,
    requirement_self_check,
    snapshot,
    source,
)


def create_requirements(
    session: Session,
    current_user: CurrentUser,
    matter_id: UUID,
    body: RequirementBatchCreate,
    *,
    now: datetime,
) -> dict[str, Any]:
    with transaction(session, current_user):
        matter_row = require_matter(session, current_user, matter_id)
        created = []
        for item in body.requirements:
            created.append(
                _create_requirement(
                    session,
                    matter_id=matter_id,
                    matter_scope_year=matter_row["scope_year"],
                    item=item,
                    now=now,
                )
            )
        return {"requirements": created}


def _create_requirement(
    session: Session,
    *,
    matter_id: UUID,
    matter_scope_year: int | None,
    item: RequirementInput,
    now: datetime,
) -> dict[str, Any]:
    snapshot_row = _snapshot_source(session, item.snapshot_id)
    if snapshot_row is None:
        raise ApiError(
            422,
            "unknown_snapshot",
            "要求引用的来源快照不存在",
            next_step="先登记来源快照，再写入要求",
        )
    if snapshot_row["source_status"] != "active":
        raise ApiError(
            422,
            "source_unavailable",
            "来源当前不可用",
            next_step="重新检索或登记可用来源",
        )
    if (
        matter_scope_year is not None
        and snapshot_row["source_scope_year"] is not None
        and snapshot_row["source_scope_year"] != matter_scope_year
    ):
        raise ApiError(
            422,
            "scope_year_mismatch",
            "来源适用年度与事项年度不一致",
            next_step="核对来源适用范围",
        )
    for evidence_item in item.evidence:
        if evidence_item.snapshot_id != item.snapshot_id:
            raise ApiError(
                422,
                "evidence_snapshot_mismatch",
                "证据快照必须与要求快照一致",
                next_step="按要求的同一快照提供原文定位",
            )
        if evidence_item.source_id != snapshot_row["source_id"]:
            raise ApiError(
                422,
                "evidence_source_mismatch",
                "证据来源必须与快照所属来源一致",
                next_step="核对来源与快照标识",
            )

    requirement_id = uuid4()
    session.execute(
        insert(requirement).values(
            id=requirement_id,
            matter_id=matter_id,
            snapshot_id=item.snapshot_id,
            field_key=item.field_key,
            label=item.label,
            obligation_nature=item.obligation_nature,
            extract_status=item.extract_status,
            scope=item.scope,
            value_text=item.value_text,
            value_type=item.value_type,
            confidence=item.confidence,
            checked_at=now if item.extract_status == "checked" else None,
            created_at=now,
            updated_at=now,
        )
    )

    if item.self_check is not None:
        session.execute(
            insert(requirement_self_check).values(
                requirement_id=requirement_id,
                conclusion=item.self_check.conclusion,
                reason=item.self_check.reason,
                missing_fields=item.self_check.missing_fields,
                computed_deadline_at=item.self_check.computed_deadline_at,
                gaps=[gap.model_dump(mode="json") for gap in item.self_check.gaps],
                evaluated_at=now,
            )
        )

    evidence_payload = []
    for evidence_item in item.evidence:
        evidence_id = uuid4()
        quote_hash = (
            hashlib.sha256(evidence_item.quote.encode("utf-8")).hexdigest()
            if evidence_item.quote is not None
            else None
        )
        session.execute(
            insert(evidence).values(
                id=evidence_id,
                source_id=evidence_item.source_id,
                snapshot_id=evidence_item.snapshot_id,
                target_type="requirement",
                target_id=requirement_id,
                locator_kind=evidence_item.locator_kind,
                locator=evidence_item.locator,
                quote=evidence_item.quote,
                quote_hash=quote_hash,
                fetched_at=snapshot_row["snapshot_fetched_at"],
            )
        )
        evidence_payload.append(
            {
                "id": str(evidence_id),
                "source_id": str(evidence_item.source_id),
                "snapshot_id": str(evidence_item.snapshot_id),
                "locator_kind": evidence_item.locator_kind,
                "locator": evidence_item.locator,
                "quote": evidence_item.quote,
                "quote_hash": quote_hash,
                "fetched_at": iso(snapshot_row["snapshot_fetched_at"]),
            }
        )

    return {
        "id": str(requirement_id),
        "matter_id": str(matter_id),
        "snapshot_id": str(item.snapshot_id),
        "field_key": item.field_key,
        "label": item.label,
        "obligation_nature": item.obligation_nature,
        "extract_status": item.extract_status,
        "scope": item.scope,
        "value_text": item.value_text,
        "value_type": item.value_type,
        "confidence": float(item.confidence) if item.confidence is not None else None,
        "checked_at": iso(now) if item.extract_status == "checked" else None,
        "created_at": iso(now),
        "updated_at": iso(now),
        "evidence": evidence_payload,
        "self_check": (
            {
                **item.self_check.model_dump(mode="json"),
                "computed_deadline_at": iso(item.self_check.computed_deadline_at),
            }
            if item.self_check is not None
            else None
        ),
    }


def _snapshot_source(session: Session, snapshot_id: UUID) -> dict[str, Any] | None:
    row = (
        session.execute(
            select(
                snapshot.c.id.label("snapshot_id"),
                snapshot.c.source_id.label("snapshot_source_id"),
                snapshot.c.fetched_at.label("snapshot_fetched_at"),
                snapshot.c.is_current.label("snapshot_is_current"),
                source.c.id.label("source_id"),
                source.c.status.label("source_status"),
                source.c.scope_year.label("source_scope_year"),
            )
            .join(source, source.c.id == snapshot.c.source_id)
            .where(snapshot.c.id == snapshot_id)
        )
        .mappings()
        .first()
    )
    if row is None:
        return None
    if row["snapshot_source_id"] != row["source_id"]:
        return None
    return dict(row)
