"""Alpha REST API contract mappers and HTTP candidate persistence client."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from backend.agent.schemas import (
    SHANGHAI,
    CandidatePlan,
    EvaluationStatus,
    ExtractedRequirement,
    LocatorKind,
    ObligationType,
    RequirementEvaluation,
    SourceCitation,
    SourceDocument,
)

ApiObligationNature = Literal["required", "advised", "optional", "to_verify"]
ApiExtractStatus = Literal["extracted", "checked", "to_review", "rejected"]
ApiLocatorKind = Literal["section", "page", "text_span", "table_row"]

FIELD_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_.]{1,63}$")

_OBLIGATION_TO_API: dict[ObligationType, ApiObligationNature] = {
    ObligationType.OFFICIAL_REQUIRED: "required",
    ObligationType.OFFICIAL_RECOMMENDED: "advised",
    ObligationType.OPTIONAL: "optional",
    ObligationType.PENDING_VERIFICATION: "to_verify",
}

_STATUS_TO_API: dict[EvaluationStatus, ApiExtractStatus] = {
    EvaluationStatus.MATCHED: "checked",
    EvaluationStatus.NOT_MATCHED: "checked",
    EvaluationStatus.MISSING_INFO: "to_review",
    EvaluationStatus.NEEDS_USER_REVIEW: "to_review",
}


def to_api_obligation(obligation: ObligationType) -> ApiObligationNature:
    """Convert internal ObligationType to PR #41 API obligation_nature enum."""
    return _OBLIGATION_TO_API[obligation]


def to_api_extract_status(status: EvaluationStatus) -> ApiExtractStatus:
    """Convert internal EvaluationStatus to PR #41 API extract_status enum."""
    return _STATUS_TO_API[status]


def normalize_api_locator_kind(kind: LocatorKind) -> ApiLocatorKind:
    """Normalize LocatorKind for PR #41 EvidenceInput / PlanItemSourceInput."""
    if kind == "list_item":
        return "section"
    return kind


def normalize_field_key(raw_key: str | None, fallback_id: str) -> str:
    """Produce a valid field_key matching ^[a-z][a-z0-9_.]{1,63}$."""
    candidate = (raw_key or fallback_id).strip().lower().replace("-", "_")
    candidate = re.sub(r"[^a-z0-9_.]", "_", candidate)
    if not candidate or not candidate[0].isalpha():
        candidate = f"req_{candidate}"
    if len(candidate) < 2:
        candidate = f"{candidate}_item"
    candidate = candidate[:64]
    if not FIELD_KEY_PATTERN.fullmatch(candidate):
        return "req.item"
    return candidate


def _resolve_citation_uuids(
    cite: SourceCitation,
    sources_by_id: dict[str, SourceDocument],
) -> tuple[str, str]:
    doc = sources_by_id.get(cite.source_version_id)
    source_id = cite.source_id or (doc.source_id if doc else None)
    snapshot_id = cite.snapshot_id or (doc.snapshot_id if doc else None)
    if not source_id or not snapshot_id:
        raise ValueError(f"引用 {cite.source_version_id} 缺少 UUID 格式的 source_id 或 snapshot_id")
    UUID(source_id)
    UUID(snapshot_id)
    return source_id, snapshot_id


def _format_value_text(
    value_text: str | None,
    value_type: Literal["text", "date", "number", "boolean", "enum"],
) -> str | None:
    if value_text is None:
        return None
    stripped = value_text.strip()
    if value_type == "date":
        if len(stripped) != 10:
            raise ValueError(f"date 类型 value_text 须为 YYYY-MM-DD：{stripped}")
        date.fromisoformat(stripped)
        return stripped
    if value_type == "number":
        if not re.fullmatch(r"-?\d+(?:\.\d+)?", stripped):
            raise ValueError(f"number 类型 value_text 须为无千位分隔符数字：{stripped}")
        return stripped
    if value_type == "boolean":
        if stripped not in {"true", "false"}:
            raise ValueError(f"boolean 类型 value_text 须为 true 或 false：{stripped}")
        return stripped
    return stripped


def build_requirements_batch_payload(
    requirements: list[ExtractedRequirement],
    evaluations: list[RequirementEvaluation],
    sources_by_id: dict[str, SourceDocument],
) -> dict[str, Any]:
    """Build exact POST /api/v1/matters/{matter_id}/requirements request body."""
    eval_by_req = {ev.requirement_id: ev for ev in evaluations}
    payload_items: list[dict[str, Any]] = []

    for req in requirements:
        evidence_list: list[dict[str, Any]] = []
        primary_snapshot_id: str | None = None
        for cite in req.basis:
            source_id, snapshot_id = _resolve_citation_uuids(cite, sources_by_id)
            if primary_snapshot_id is None:
                primary_snapshot_id = snapshot_id
            elif primary_snapshot_id != snapshot_id:
                continue
            evidence_list.append(
                {
                    "source_id": source_id,
                    "snapshot_id": snapshot_id,
                    "locator_kind": normalize_api_locator_kind(cite.locator_kind),
                    "locator": cite.locator[:300],
                    "quote": cite.excerpt,
                }
            )

        if primary_snapshot_id is None or not evidence_list:
            raise ValueError(f"要求 {req.requirement_id} 缺少有效的快照证据")

        ev = eval_by_req.get(req.requirement_id)
        extract_status: ApiExtractStatus = (
            to_api_extract_status(ev.status) if ev is not None else "extracted"
        )
        value_text = req.value_text
        if value_text is None and req.official_deadline is not None:
            value_text = req.official_deadline.isoformat()
        formatted_value = _format_value_text(value_text, req.value_type)

        payload_items.append(
            {
                "field_key": normalize_field_key(req.field_key, req.requirement_id),
                "label": req.title[:120],
                "obligation_nature": to_api_obligation(req.obligation),
                "extract_status": extract_status,
                "scope": req.scope[:200] if req.scope else None,
                "value_text": formatted_value,
                "value_type": req.value_type,
                "confidence": req.confidence,
                "snapshot_id": primary_snapshot_id,
                "evidence": evidence_list,
            }
        )

    return {"requirements": payload_items}


def build_candidate_plan_create_payload(
    plan: CandidatePlan,
    sources_by_id: dict[str, SourceDocument],
    requirement_id_map: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build exact POST /api/v1/matters/{matter_id}/candidate-plans request body."""
    items_payload: list[dict[str, Any]] = []
    req_map = requirement_id_map or {}

    for task in plan.tasks:
        sources_payload: list[dict[str, Any]] = []
        for cite in task.basis:
            source_id, snapshot_id = _resolve_citation_uuids(cite, sources_by_id)
            sources_payload.append(
                {
                    "source_id": source_id,
                    "snapshot_id": snapshot_id,
                    "locator_kind": normalize_api_locator_kind(cite.locator_kind),
                    "locator": cite.locator[:300],
                    "quote": cite.excerpt,
                }
            )

        deadline_at = task.official_deadline_at or task.official_deadline
        deadline_date = task.official_deadline_date
        if deadline_at is not None:
            shanghai_date = deadline_at.astimezone(SHANGHAI).date()
            if deadline_date is None:
                deadline_date = shanghai_date
            elif deadline_date != shanghai_date:
                raise ValueError(
                    f"任务 {task.task_id} 的 official_deadline_date 与 Asia/Shanghai 时刻日期不一致"
                )

        mapped_req_id: str | None = None
        if task.requirement_id:
            candidate_uuid = req_map.get(task.requirement_id, task.requirement_id)
            UUID(candidate_uuid)
            mapped_req_id = candidate_uuid

        items_payload.append(
            {
                "client_item_id": task.task_id[:80],
                "title": task.title[:160],
                "detail": task.detail,
                "obligation_nature": to_api_obligation(task.obligation),
                "official_deadline_date": deadline_date.isoformat() if deadline_date else None,
                "official_deadline_at": _format_iso_dt(deadline_at),
                "suggested_date": task.suggested_date.isoformat() if task.suggested_date else None,
                "depends_on": list(task.depends_on),
                "evidence_required": bool(task.evidence_required),
                "requirement_id": mapped_req_id,
                "sources": sources_payload,
            }
        )

    return {"items": items_payload}


def _format_iso_dt(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


class PersistenceApiError(RuntimeError):
    """Raised when persisting candidate requirements or plans to the backend API fails."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code


class HttpCandidatePersistenceClient:
    """HTTP client targeting PR #41 backend candidate endpoints; never invokes /confirm."""

    def __init__(self, base_url: str, *, timeout_seconds: float = 10.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds

    def persist_requirements(self, matter_id: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
        """Persist extracted requirements via POST /api/v1/matters/{matter_id}/requirements."""
        data = self._post_json(f"{self._base_url}/api/v1/matters/{matter_id}/requirements", payload)
        return list(data.get("requirements", []))

    def persist_candidate_plan(self, matter_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Persist pending candidate plan via POST /api/v1/matters/{matter_id}/candidate-plans."""
        data = self._post_json(f"{self._base_url}/api/v1/matters/{matter_id}/candidate-plans", payload)
        return dict(data.get("plan", data))

    def _post_json(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise PersistenceApiError(exc.code, f"后端接口返回 HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise PersistenceApiError(503, f"无法连接后端接口: {exc.reason}") from exc
