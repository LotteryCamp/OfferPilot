"""Canonical candidate-plan basis input and SHA-256 fingerprint."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

BASIS_CONTRACT_VERSION = "alpha-1"
PLAN_STRATEGY_VERSION = "alpha-1"


def canonical_json(value: Any) -> str:
    """Return deterministic compact UTF-8 JSON for hashing."""

    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def compute_basis_version(basis_input: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json(basis_input).encode("utf-8")).hexdigest()


def build_basis_input(
    *,
    matter_row: Mapping[str, Any],
    requirement_rows: Iterable[Mapping[str, Any]],
    source_rows: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build the normalized input that identifies one candidate basis.

    The stored object keeps explicit nulls and stable ordering. Generation time,
    request identifiers, and model-authored text are excluded.
    """

    requirements = sorted(
        (_requirement_entry(row) for row in requirement_rows),
        key=lambda item: item["id"],
    )
    sources = sorted(
        (_source_entry(row) for row in source_rows),
        key=lambda item: (item["source_id"], item["snapshot_id"]),
    )
    return {
        "contract": {
            "agent_output": BASIS_CONTRACT_VERSION,
            "plan_strategy": PLAN_STRATEGY_VERSION,
        },
        "matter": {
            "id": _uuid_text(matter_row.get("id")),
            "type_code": matter_row.get("type_code"),
            "template_version_id": _uuid_text(matter_row.get("template_version_id")),
            "scope_year": matter_row.get("scope_year"),
            "scope_attrs": matter_row.get("scope_attrs"),
            "updated_at": _datetime_text(matter_row.get("updated_at")),
        },
        "requirements": requirements,
        "sources": sources,
        "confirmed_facts": [],
    }


def _requirement_entry(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": _uuid_text(row.get("id")),
        "snapshot_id": _uuid_text(row.get("snapshot_id")),
        "field_key": row.get("field_key"),
        "label": row.get("label"),
        "obligation_nature": row.get("obligation_nature"),
        "extract_status": row.get("extract_status"),
        "scope": row.get("scope"),
        "value_text": row.get("value_text"),
        "value_type": row.get("value_type"),
        "confidence": _decimal_text(row.get("confidence")),
        "updated_at": _datetime_text(row.get("updated_at")),
    }


def _source_entry(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "source_id": _uuid_text(row.get("source_id")),
        "status": row.get("status"),
        "snapshot_id": _uuid_text(row.get("snapshot_id")),
        "version_no": row.get("version_no"),
        "content_hash": row.get("content_hash"),
        "is_current": row.get("is_current"),
        "fetched_at": _datetime_text(row.get("fetched_at")),
    }


def _uuid_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, UUID):
        return str(value)
    return str(value)


def _decimal_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return format(value, "f")
    return str(value)


def _datetime_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    return str(value)


def _date_text(value: date | None) -> str | None:
    return value.isoformat() if value is not None else None
