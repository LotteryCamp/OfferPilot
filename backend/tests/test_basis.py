"""Unit tests for deterministic basis fingerprints."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from backend.basis import build_basis_input, compute_basis_version

MATTER_ID = UUID("00000000-0000-7000-8000-000000000003")
TEMPLATE_ID = UUID("10000000-0000-7000-8000-000000000001")
REQUIREMENT_ID = UUID("00000000-0000-7000-8000-000000000006")
SOURCE_ID = UUID("00000000-0000-7000-8000-000000000004")
SNAPSHOT_ID = UUID("00000000-0000-7000-8000-000000000005")


def _matter() -> dict:
    return {
        "id": MATTER_ID,
        "type_code": "pre_recommend",
        "template_version_id": TEMPLATE_ID,
        "scope_year": 2027,
        "scope_attrs": {"college": "数学与统计学院", "school": "福州大学"},
        "updated_at": datetime(2026, 9, 8, 12, 0, tzinfo=UTC),
    }


def _requirement() -> dict:
    return {
        "id": REQUIREMENT_ID,
        "snapshot_id": SNAPSHOT_ID,
        "field_key": "application.deadline",
        "label": "申请截止",
        "obligation_nature": "required",
        "extract_status": "checked",
        "scope": "2027 届",
        "value_text": "2026-09-10T15:00:00+08:00",
        "value_type": "text",
        "confidence": None,
        "updated_at": datetime(2026, 9, 8, 12, 0, tzinfo=UTC),
    }


def _source(status: str = "active", is_current: bool = True) -> dict:
    return {
        "source_id": SOURCE_ID,
        "status": status,
        "snapshot_id": SNAPSHOT_ID,
        "version_no": 1,
        "content_hash": "a" * 64,
        "is_current": is_current,
        "fetched_at": datetime(2026, 9, 8, 12, 0, tzinfo=UTC),
    }


def test_basis_is_stable_across_input_order() -> None:
    second_requirement = {
        **_requirement(),
        "id": UUID("00000000-0000-7000-8000-000000000007"),
        "snapshot_id": UUID("00000000-0000-7000-8000-000000000008"),
        "field_key": "application.materials",
        "label": "申请材料",
    }
    second_source = {
        **_source(),
        "source_id": UUID("00000000-0000-7000-8000-000000000009"),
        "snapshot_id": UUID("00000000-0000-7000-8000-000000000010"),
        "content_hash": "b" * 64,
    }
    first = build_basis_input(
        matter_row=_matter(),
        requirement_rows=[_requirement(), second_requirement],
        source_rows=[_source(), second_source],
    )
    second = build_basis_input(
        matter_row=_matter(),
        requirement_rows=[second_requirement, _requirement()],
        source_rows=[second_source, _source()],
    )
    assert compute_basis_version(first) == compute_basis_version(second)


def test_basis_changes_when_source_status_changes() -> None:
    active = build_basis_input(
        matter_row=_matter(),
        requirement_rows=[_requirement()],
        source_rows=[_source("active")],
    )
    withdrawn = build_basis_input(
        matter_row=_matter(),
        requirement_rows=[_requirement()],
        source_rows=[_source("withdrawn")],
    )
    assert compute_basis_version(active) != compute_basis_version(withdrawn)
    assert active["matter"]["template_version_id"] == str(TEMPLATE_ID)
    assert active["confirmed_facts"] == []
