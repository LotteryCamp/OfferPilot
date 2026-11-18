"""Formal task reads with the candidate item source chain."""

from __future__ import annotations

from collections import defaultdict
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.config import Settings
from backend.services.common import (
    iso,
    require_matter,
    serialize_task_row,
    transaction,
    uuid_text,
)
from backend.tables import (
    candidate_plan_item,
    candidate_plan_item_source,
    snapshot,
    source,
    task,
)


def list_tasks(session: Session, settings: Settings, matter_id: UUID) -> dict[str, Any]:
    with transaction(session, settings):
        require_matter(session, settings, matter_id)
        task_rows = (
            session.execute(
                select(task)
                .outerjoin(
                    candidate_plan_item,
                    candidate_plan_item.c.id == task.c.plan_item_id,
                )
                .where(task.c.matter_id == matter_id)
                .order_by(
                    task.c.created_at,
                    candidate_plan_item.c.seq.asc().nulls_last(),
                    task.c.id,
                )
            )
            .mappings()
            .all()
        )
        plan_item_ids = [
            row["plan_item_id"] for row in task_rows if row["plan_item_id"] is not None
        ]
        sources_by_item: dict[UUID, list[dict[str, Any]]] = defaultdict(list)
        if plan_item_ids:
            source_rows = session.execute(
                select(
                    candidate_plan_item_source.c.plan_item_id,
                    source.c.id.label("source_id"),
                    source.c.publisher,
                    source.c.url,
                    source.c.status.label("source_status"),
                    snapshot.c.id.label("snapshot_id"),
                    snapshot.c.version_no,
                    snapshot.c.content_hash,
                    snapshot.c.fetched_at,
                    snapshot.c.is_current,
                    candidate_plan_item_source.c.locator_kind,
                    candidate_plan_item_source.c.locator,
                    candidate_plan_item_source.c.quote,
                )
                .join(
                    source,
                    source.c.id == candidate_plan_item_source.c.source_id,
                )
                .join(
                    snapshot,
                    snapshot.c.id == candidate_plan_item_source.c.snapshot_id,
                )
                .where(candidate_plan_item_source.c.plan_item_id.in_(plan_item_ids))
                .order_by(
                    candidate_plan_item_source.c.plan_item_id,
                    source.c.id,
                    snapshot.c.id,
                )
            ).mappings()
            for row in source_rows:
                sources_by_item[row["plan_item_id"]].append(
                    {
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
        return {
            "tasks": [
                {
                    **serialize_task_row(row),
                    "sources": sources_by_item.get(row["plan_item_id"], []),
                }
                for row in task_rows
            ]
        }
