"""Public source and snapshot registration plus source-chain reads."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import func, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from backend.errors import ApiError
from backend.identity import CurrentUser
from backend.schemas import SourceCreate, SourceReadRequest
from backend.services.common import (
    iso,
    json_object,
    require_matter,
    transaction,
    uuid_text,
)
from backend.sources import (
    PublicSourceResult,
    SourceReadError,
    read_public_html,
    source_document_from_registration,
    source_registration_payload,
)
from backend.tables import (
    candidate_plan,
    candidate_plan_item,
    candidate_plan_item_source,
    evidence,
    matter_source,
    matter_type,
    requirement,
    requirement_self_check,
    snapshot,
    source,
)

SourceReader = Callable[[dict[str, Any]], PublicSourceResult]

_SOURCE_READ_MESSAGES = {
    "unsafe_url": "来源地址不可公开读取",
    "invalid_request": "来源读取请求不符合契约",
    "network_error": "来源暂时无法访问",
    "http_error": "来源返回了错误响应",
    "unsupported_content_type": "来源不是可读取的 HTML 页面或 PDF 附件",
    "empty_content": "来源页面没有可读取的正文",
    "response_too_large": "来源页面超过读取大小限制",
    "too_many_fragments": "来源页面段落数量超过读取限制",
    "decode_error": "来源页面编码无法识别",
    "parse_error": "来源页面无法解析",
    "pdf_encrypted": "PDF 已加密，无法读取正文",
    "pdf_no_text": "PDF 没有可提取的文字，扫描件需人工核对",
    "pdf_page_limit": "PDF 页数超过读取限制",
    "pdf_parse_error": "PDF 文件损坏或无法解析",
}


def register_source(
    session: Session,
    current_user: CurrentUser,
    matter_id: UUID,
    body: SourceCreate,
    *,
    now: datetime,
) -> dict[str, Any]:
    with transaction(session, current_user):
        matter_row = require_matter(session, current_user, matter_id)
        type_row = session.execute(
            select(matter_type.c.id).where(
                matter_type.c.type_code == matter_row["type_code"]
            )
        ).first()
        if type_row is None:
            raise ApiError(
                422,
                "unknown_matter_type",
                "事项类型不存在",
                next_step="检查事项类型配置",
            )
        matter_type_id = type_row[0]

        url = str(body.url)
        content_hash = (
            body.content_hash
            or hashlib.sha256(body.content.encode("utf-8")).hexdigest()
        )
        fetched_at = (
            body.fetched_at.astimezone(UTC) if body.fetched_at is not None else now
        )

        existing = (
            session.execute(select(source).where(source.c.url == url).with_for_update())
            .mappings()
            .first()
        )
        if body.source_id is not None:
            if existing is not None and existing["id"] != body.source_id:
                raise ApiError(
                    409,
                    "source_conflict",
                    "同一 URL 已登记为其他来源",
                    next_step="使用已登记的来源标识",
                )
            if existing is None:
                by_id = (
                    session.execute(
                        select(source)
                        .where(source.c.id == body.source_id)
                        .with_for_update()
                    )
                    .mappings()
                    .first()
                )
                if by_id is not None:
                    raise ApiError(
                        409,
                        "source_conflict",
                        "来源标识已被其他 URL 使用",
                        next_step="核对来源标识",
                    )

        source_created = existing is None
        if existing is None:
            source_id = body.source_id or uuid5(NAMESPACE_URL, url)
            session.execute(
                insert(source).values(
                    id=source_id,
                    publisher=body.publisher,
                    url=url,
                    matter_type_id=matter_type_id,
                    scope=body.scope,
                    scope_year=body.scope_year,
                    valid_from=body.valid_from,
                    valid_to=body.valid_to,
                    status=body.status,
                    auto_check_status=body.auto_check_status,
                    roi_status=body.roi_status,
                    last_fetched_at=fetched_at,
                    created_at=now,
                )
            )
            source_row = (
                session.execute(select(source).where(source.c.id == source_id))
                .mappings()
                .one()
            )
        else:
            _check_source_metadata(existing, body, matter_type_id)
            source_id = existing["id"]
            source_row = existing
            updates: dict[str, Any] = {}
            if body.scope is not None:
                updates["scope"] = body.scope
            if body.valid_from is not None:
                updates["valid_from"] = body.valid_from
            if body.valid_to is not None:
                updates["valid_to"] = body.valid_to
            if updates:
                session.execute(
                    update(source).where(source.c.id == source_id).values(**updates)
                )
                source_row = (
                    session.execute(select(source).where(source.c.id == source_id))
                    .mappings()
                    .one()
                )

        existing_snapshot = (
            session.execute(
                select(snapshot)
                .where(
                    snapshot.c.source_id == source_id,
                    snapshot.c.content_hash == content_hash,
                )
                .with_for_update()
            )
            .mappings()
            .first()
        )
        if existing_snapshot is not None:
            if (
                body.snapshot_id is not None
                and existing_snapshot["id"] != body.snapshot_id
            ):
                raise ApiError(
                    409,
                    "snapshot_conflict",
                    "同一内容已登记为其他快照",
                    next_step="使用已登记的共享快照标识",
                )
            snapshot_created = False
            snapshot_row = existing_snapshot
        else:
            if body.snapshot_id is not None:
                snapshot_by_id = (
                    session.execute(
                        select(snapshot)
                        .where(snapshot.c.id == body.snapshot_id)
                        .with_for_update()
                    )
                    .mappings()
                    .first()
                )
                if snapshot_by_id is not None:
                    raise ApiError(
                        409,
                        "snapshot_conflict",
                        "快照标识已被其他来源或内容使用",
                        next_step="核对快照标识",
                    )
            max_version = session.execute(
                select(func.max(snapshot.c.version_no)).where(
                    snapshot.c.source_id == source_id
                )
            ).scalar_one_or_none()
            version_no = (max_version or 0) + 1
            snapshot_id = body.snapshot_id or uuid5(
                NAMESPACE_URL, f"{url}#{content_hash}"
            )
            extraction: dict[str, Any] = {
                "text": body.content,
                "title": body.title,
            }
            if body.published_date is not None:
                extraction["published_date"] = body.published_date.isoformat()
            if body.fragments:
                extraction["fragments"] = [
                    fragment.model_dump(mode="json") for fragment in body.fragments
                ]
            session.execute(
                insert(snapshot).values(
                    id=snapshot_id,
                    source_id=source_id,
                    version_no=version_no,
                    object_key=f"inline:{content_hash}",
                    content_hash=content_hash,
                    extraction=extraction,
                    fetched_at=fetched_at,
                    is_current=True,
                )
            )
            session.execute(
                update(source)
                .where(source.c.id == source_id)
                .values(
                    last_fetched_at=max(
                        source_row["last_fetched_at"] or fetched_at,
                        fetched_at,
                    ),
                    auto_check_status=body.auto_check_status,
                )
            )
            snapshot_created = True
            snapshot_row = (
                session.execute(select(snapshot).where(snapshot.c.id == snapshot_id))
                .mappings()
                .one()
            )
            source_row = (
                session.execute(select(source).where(source.c.id == source_id))
                .mappings()
                .one()
            )

        _link_matter_source(
            session,
            matter_id=matter_id,
            snapshot_id=snapshot_row["id"],
            now=now,
        )
        return {
            "source": _serialize_source({**source_row, "source_id": source_row["id"]}),
            "snapshot": _serialize_snapshot(
                {**snapshot_row, "snapshot_id": snapshot_row["id"]}
            ),
            "created": {
                "source": source_created,
                "snapshot": snapshot_created,
            },
        }


def _link_matter_source(
    session: Session,
    *,
    matter_id: UUID,
    snapshot_id: UUID,
    now: datetime,
) -> None:
    session.execute(
        pg_insert(matter_source)
        .values(matter_id=matter_id, snapshot_id=snapshot_id, linked_at=now)
        .on_conflict_do_nothing(index_elements=["matter_id", "snapshot_id"])
    )


def read_and_register_source(
    session: Session,
    current_user: CurrentUser,
    matter_id: UUID,
    body: SourceReadRequest,
    *,
    now: datetime,
    reader: SourceReader = read_public_html,
) -> dict[str, Any]:
    with transaction(session, current_user):
        require_matter(session, current_user, matter_id)
    try:
        result = reader(
            {
                "url": str(body.url),
                "publisher": body.publisher,
                "scope_year": body.scope_year,
                "scope": body.scope,
                "title": body.title,
                "matter_id": matter_id,
            }
        )
    except SourceReadError as error:
        raise _source_read_failure(error) from error
    registration = register_source(
        session,
        current_user,
        matter_id,
        SourceCreate.model_validate(source_registration_payload(result)),
        now=now,
    )
    return {
        **registration,
        "document": source_document_from_registration(registration),
    }


def _source_read_failure(error: SourceReadError) -> ApiError:
    upstream_failure = error.code in {"network_error", "incomplete_response"} or (
        error.code == "http_error" and error.retryable
    )
    return ApiError(
        502 if upstream_failure else 422,
        "source_read_failed",
        _SOURCE_READ_MESSAGES.get(error.code, "来源读取失败"),
        next_step=(
            "稍后重试；若持续失败请检查来源地址"
            if error.retryable
            else "核对来源地址或页面类型后重试"
        ),
        details={"code": error.code, "retryable": error.retryable},
    )


def list_matter_sources(
    session: Session, current_user: CurrentUser, matter_id: UUID
) -> dict[str, Any]:
    with transaction(session, current_user):
        require_matter(session, current_user, matter_id)
        requirement_rows = (
            session.execute(
                select(requirement)
                .where(requirement.c.matter_id == matter_id)
                .order_by(requirement.c.field_key, requirement.c.id)
            )
            .mappings()
            .all()
        )
        requirement_ids = [row["id"] for row in requirement_rows]
        evidence_by_requirement: dict[UUID, list[dict[str, Any]]] = defaultdict(list)
        self_check_by_requirement: dict[UUID, dict[str, Any]] = {}
        if requirement_ids:
            evidence_rows = session.execute(
                select(evidence)
                .where(
                    evidence.c.target_type == "requirement",
                    evidence.c.target_id.in_(requirement_ids),
                )
                .order_by(evidence.c.locator, evidence.c.id)
            ).mappings()
            for row in evidence_rows:
                evidence_by_requirement[row["target_id"]].append(
                    _serialize_evidence(row)
                )
            for row in session.execute(
                select(requirement_self_check).where(
                    requirement_self_check.c.requirement_id.in_(requirement_ids)
                )
            ).mappings():
                self_check_by_requirement[row["requirement_id"]] = (
                    _serialize_self_check(row)
                )

        snapshot_ids = {row["snapshot_id"] for row in requirement_rows}
        snapshot_ids.update(
            session.execute(
                select(matter_source.c.snapshot_id).where(
                    matter_source.c.matter_id == matter_id
                )
            ).scalars()
        )
        plan_snapshot_ids = session.execute(
            select(candidate_plan_item_source.c.snapshot_id)
            .join(
                candidate_plan_item,
                candidate_plan_item.c.id == candidate_plan_item_source.c.plan_item_id,
            )
            .join(
                candidate_plan,
                candidate_plan.c.id == candidate_plan_item.c.plan_id,
            )
            .where(candidate_plan.c.matter_id == matter_id)
        ).scalars()
        snapshot_ids.update(plan_snapshot_ids)

        source_ids = set()
        if snapshot_ids:
            source_ids = set(
                session.execute(
                    select(snapshot.c.source_id).where(snapshot.c.id.in_(snapshot_ids))
                ).scalars()
            )

        snapshot_rows = []
        if source_ids:
            snapshot_rows = (
                session.execute(
                    select(
                        source.c.id.label("source_id"),
                        source.c.publisher,
                        source.c.url,
                        source.c.scope,
                        source.c.scope_year,
                        source.c.valid_from,
                        source.c.valid_to,
                        source.c.status,
                        source.c.auto_check_status,
                        source.c.roi_status,
                        source.c.last_fetched_at,
                        source.c.created_at,
                        snapshot.c.id.label("snapshot_id"),
                        snapshot.c.version_no,
                        snapshot.c.content_hash,
                        snapshot.c.extraction,
                        snapshot.c.fetched_at,
                        snapshot.c.is_current,
                    )
                    .join(source, source.c.id == snapshot.c.source_id)
                    .where(snapshot.c.source_id.in_(source_ids))
                    .order_by(source.c.publisher, source.c.url, snapshot.c.version_no)
                )
                .mappings()
                .all()
            )

        requirements_by_snapshot: dict[UUID, list[dict[str, Any]]] = defaultdict(list)
        for row in requirement_rows:
            requirements_by_snapshot[row["snapshot_id"]].append(
                {
                    **_serialize_requirement(row),
                    "evidence": evidence_by_requirement[row["id"]],
                    "self_check": self_check_by_requirement.get(row["id"]),
                }
            )

        grouped: dict[UUID, dict[str, Any]] = {}
        for row in snapshot_rows:
            source_data = _serialize_source(row)
            source_entry = grouped.setdefault(
                row["source_id"],
                {
                    **source_data,
                    "snapshots": [],
                },
            )
            source_entry["snapshots"].append(
                {
                    **_serialize_snapshot(row),
                    "requirements": requirements_by_snapshot.get(
                        row["snapshot_id"], []
                    ),
                }
            )

        sources = sorted(
            grouped.values(),
            key=lambda item: (item["publisher"], item["url"]),
        )
        return {"sources": sources}


def _check_source_metadata(
    existing: dict[str, Any], body: SourceCreate, matter_type_id: UUID
) -> None:
    if existing["publisher"] != body.publisher:
        raise ApiError(
            409,
            "source_conflict",
            "同一 URL 的发布主体不一致",
            next_step="核对来源元数据后重新提交",
        )
    if existing["scope_year"] != body.scope_year:
        raise ApiError(
            409,
            "source_conflict",
            "同一 URL 的适用年度不一致",
            next_step="核对来源适用年度",
        )
    if existing["matter_type_id"] not in (None, matter_type_id):
        raise ApiError(
            409,
            "source_conflict",
            "同一 URL 的事项类型不一致",
            next_step="核对来源事项类型",
        )


def _serialize_source(row: Any) -> dict[str, Any]:
    return {
        "id": uuid_text(row["source_id"]),
        "publisher": row["publisher"],
        "url": row["url"],
        "scope": row["scope"],
        "scope_year": row["scope_year"],
        "valid_from": iso(row["valid_from"]),
        "valid_to": iso(row["valid_to"]),
        "status": row["status"],
        "auto_check_status": row["auto_check_status"],
        "roi_status": row["roi_status"],
        "last_fetched_at": iso(row["last_fetched_at"]),
        "created_at": iso(row["created_at"]),
    }


def _serialize_snapshot(row: Any) -> dict[str, Any]:
    extraction = json_object(row["extraction"]) or {}
    return {
        "id": uuid_text(row["snapshot_id"]),
        "source_id": uuid_text(row["source_id"]),
        "version_no": row["version_no"],
        "content_hash": row["content_hash"],
        "title": extraction.get("title"),
        "published_date": extraction.get("published_date"),
        "text": extraction.get("text"),
        "fragments": extraction.get("fragments", []),
        "fetched_at": iso(row["fetched_at"]),
        "is_current": row["is_current"],
    }


def _serialize_requirement(row: Any) -> dict[str, Any]:
    return {
        "id": uuid_text(row["id"]),
        "matter_id": uuid_text(row["matter_id"]),
        "snapshot_id": uuid_text(row["snapshot_id"]),
        "field_key": row["field_key"],
        "label": row["label"],
        "obligation_nature": row["obligation_nature"],
        "extract_status": row["extract_status"],
        "scope": row["scope"],
        "value_text": row["value_text"],
        "value_type": row["value_type"],
        "confidence": float(row["confidence"])
        if row["confidence"] is not None
        else None,
        "checked_at": iso(row["checked_at"]),
        "created_at": iso(row["created_at"]),
        "updated_at": iso(row["updated_at"]),
    }


def _serialize_self_check(row: Any) -> dict[str, Any]:
    return {
        "conclusion": row["conclusion"],
        "reason": row["reason"],
        "missing_fields": list(row["missing_fields"] or []),
        "computed_deadline_at": iso(row["computed_deadline_at"]),
        "gaps": list(row["gaps"] or []),
    }


def _serialize_evidence(row: Any) -> dict[str, Any]:
    return {
        "id": uuid_text(row["id"]),
        "source_id": uuid_text(row["source_id"]),
        "snapshot_id": uuid_text(row["snapshot_id"]),
        "locator_kind": row["locator_kind"],
        "locator": row["locator"],
        "quote": row["quote"],
        "quote_hash": row["quote_hash"],
        "fetched_at": iso(row["fetched_at"]),
    }
