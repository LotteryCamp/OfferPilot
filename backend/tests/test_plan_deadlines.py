"""Tests for candidate plan deadline normalization in the business timezone."""

from __future__ import annotations

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest

from backend.errors import ApiError
from backend.schemas import CandidatePlanItemInput
from backend.services.plans import _normalize_deadlines


def _item(*, deadline_date: date | None = None) -> CandidatePlanItemInput:
    return CandidatePlanItemInput(
        client_item_id="t1",
        title="提交材料",
        official_deadline_date=deadline_date,
        official_deadline_at=datetime(2026, 9, 11, 6, 0, tzinfo=UTC),
    )


def test_normalize_deadlines_uses_configured_timezone() -> None:
    item = _item()

    _normalize_deadlines([item], ZoneInfo("America/Los_Angeles"))

    assert item.official_deadline_date == date(2026, 9, 10)


def test_normalize_deadlines_rejects_mismatched_date() -> None:
    item = _item(deadline_date=date(2026, 9, 11))

    with pytest.raises(ApiError) as error:
        _normalize_deadlines([item], ZoneInfo("America/Los_Angeles"))

    assert error.value.status_code == 422
    assert error.value.details["client_item_id"] == "t1"

    _normalize_deadlines([item], ZoneInfo("Asia/Shanghai"))

    assert item.official_deadline_date == date(2026, 9, 11)
