"""Bridge adapting PR #38 structured LLM adapter to ModelAdapterPort."""

from __future__ import annotations

import importlib
import json
import re
from datetime import date, datetime
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field, ValidationError

from backend.agent.schemas import (
    AgentErrorCode,
    CandidatePlan,
    CandidateTask,
    ExtractedRequirement,
    ObligationType,
    RequirementEvaluation,
    RuleKind,
    RunContext,
    SourceCitation,
    SourceDocument,
    SourceGap,
)


class CallModelFn(Protocol):
    """Callable matching PR #38 backend.model_adapter.call_model signature."""

    def __call__[T: BaseModel](
        self,
        instruction: str,
        text: str,
        response_model: type[T],
    ) -> T: ...


_PUBLIC_SCOPE_ALLOWLIST = frozenset(
    {
        "school",
        "college",
        "department",
        "program",
        "major",
        "track",
        "category",
        "degree",
        "intake_year",
        "scope_year",
        "region",
    }
)


def sanitize_public_scope_attrs(scope_attrs: dict[str, Any]) -> dict[str, Any]:
    """Keep only allowlisted public academic scope fields for external model payloads."""
    sanitized: dict[str, Any] = {}
    for key, value in scope_attrs.items():
        if key not in _PUBLIC_SCOPE_ALLOWLIST:
            continue
        if isinstance(value, str):
            trimmed = value.strip()[:100]
            if trimmed:
                sanitized[key] = trimmed
        elif isinstance(value, (int, bool)):
            sanitized[key] = value
    return sanitized


class ModelInvocationError(RuntimeError):
    """Error raised when LLM invocation fails, times out, or returns invalid structure."""

    def __init__(self, code: AgentErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class ExtractedRequirementDraft(BaseModel):
    """Structured LLM output schema for a single extracted requirement."""

    requirement_id: str = Field(min_length=1)
    title: str = Field(min_length=1, max_length=120)
    obligation: ObligationType = ObligationType.PENDING_VERIFICATION
    basis: list[SourceCitation] = Field(min_length=1)
    official_deadline: datetime | None = None
    required_fact_keys: list[str] = Field(default_factory=list)
    is_ambiguous: bool = False
    field_key: str | None = None
    scope: str | None = None
    value_text: str | None = None
    value_type: Literal["text", "date", "number", "boolean", "enum"] = "text"
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    rule_kind: RuleKind | None = None
    rule_parameters: dict[str, Any] = Field(default_factory=dict)
    required_attachments: list[str] = Field(default_factory=list)


class RequirementExtractionPayload(BaseModel):
    """Top-level structured LLM output for requirement extraction."""

    requirements: list[ExtractedRequirementDraft] = Field(default_factory=list)
    gaps: list[SourceGap] = Field(default_factory=list)
    scope_summary: dict[str, Any] = Field(default_factory=dict)


class CandidateTaskDraft(BaseModel):
    """Structured LLM output schema for a single candidate task."""

    task_id: str = Field(min_length=1)
    title: str = Field(min_length=1, max_length=160)
    detail: str | None = None
    requirement_id: str | None = None
    basis: list[SourceCitation] = Field(min_length=1)
    obligation: ObligationType = ObligationType.PENDING_VERIFICATION
    official_deadline_date: date | None = None
    official_deadline_at: datetime | None = None
    suggested_date: date | None = None
    depends_on: list[str] = Field(default_factory=list)
    evidence_required: str = Field(min_length=1)


class CandidatePlanDraftPayload(BaseModel):
    """Top-level structured LLM output for candidate plan generation."""

    tasks: list[CandidateTaskDraft] = Field(default_factory=list)
    gaps: list[SourceGap] = Field(default_factory=list)
    scope_summary: dict[str, Any] = Field(default_factory=dict)


_EXTRACTION_INSTRUCTION = (
    "你是 OfferPilot 推免信息抽取助手。严格依据传入的官方来源原文提取要求与适用范围：\n"
    "1. 每条要求必须保留可回溯的 source_version_id 与 locator，禁止编造来源版本或条文。\n"
    "   当来源对象包含非空 fragments 列表时，basis[*].locator 必须原样复制对应片段的 fragments[*].locator，"
    "locator_kind 必须取自该片段的 locator_kind，excerpt 必须是该片段 quote 的连续原文字串，严禁自行改写或简写 locator。\n"
    "2. 原文仅给出日期时只填 date 值；给出精确时刻时才填带时区的时间戳，不得虚构时刻。\n"
    "3. 不同条件或适用人群（如申请推荐与放弃推荐）须拆开标注 scope。\n"
    "4. 缺少上位文件、附件或个人依据时，在 gaps 中显式记录，禁止得出最终资格认定。"
)

_PLANNING_INSTRUCTION = (
    "你是 OfferPilot 候选计划生成助手。仅根据已核实来源和条件自查结果生成待用户确认的候选任务：\n"
    "1. 每条候选任务必须包含来自输入 sources 的 source_version_id 与 locator。"
    "当来源对象包含非空 fragments 列表时，basis[*].locator 必须原样复制对应片段的 fragments[*].locator（或沿用 evaluations.basis 中的 locator），"
    "locator_kind 必须匹配该片段，excerpt 必须是对应片段 quote 的连续原文字串，严禁自行改写。\n"
    "2. 官方日期存入 official_deadline_date，仅原文给出时刻时填写 official_deadline_at（带时区），"
    "个人建议准备日存入 suggested_date，不高于官方期限。\n"
    "3. 依赖关系 depends_on 只能引用本计划内的 task_id 且不得成环。\n"
    "4. 缺依据或条件不清时在 gaps 中明确说明，不编造确定性结论。"
)


class StructuredModelAdapter:
    """ModelAdapterPort implementation backed by PR #38 call_model."""

    def __init__(
        self,
        call_model_fn: CallModelFn,
        *,
        strategy_version: str = "alpha-1",
    ) -> None:
        self._call_model = call_model_fn
        self._strategy_version = strategy_version
        self.last_gaps: list[SourceGap] = []
        self.last_scope_summary: dict[str, Any] = {}

    @classmethod
    def from_backend_adapter(
        cls, *, strategy_version: str = "alpha-1"
    ) -> StructuredModelAdapter:
        """Construct adapter using PR #38 backend.model_adapter.call_model."""
        try:
            module = importlib.import_module("backend.model_adapter")
        except ImportError as exc:
            raise ModelInvocationError(
                AgentErrorCode.MODEL_ERROR,
                "未找到 backend.model_adapter，请先安装或合入模型适配模块",
            ) from exc
        return cls(module.call_model, strategy_version=strategy_version)

    def extract_requirements(
        self,
        goal: str,
        sources: list[SourceDocument],
    ) -> list[ExtractedRequirement]:
        """Extract structured requirements from official sources via LLM."""
        requirements, gaps, scope_summary = self.extract_requirements_with_metadata(
            goal, sources
        )
        self.last_gaps = gaps
        self.last_scope_summary = scope_summary
        return requirements

    def extract_requirements_with_metadata(
        self,
        goal: str,
        sources: list[SourceDocument],
    ) -> tuple[list[ExtractedRequirement], list[SourceGap], dict[str, Any]]:
        """Extract structured requirements, gaps, and scope summary per call without shared state."""
        payload_input = {
            "goal": goal.strip(),
            "strategy_version": self._strategy_version,
            "sources": [
                {
                    "source_version_id": s.source_version_id,
                    "source_id": s.source_id,
                    "snapshot_id": s.snapshot_id,
                    "title": s.title,
                    "publisher": s.publisher,
                    "year": s.year,
                    "scope": s.scope,
                    "content": "" if s.fragments else s.content,
                    "missing_attachments": s.missing_attachments,
                    "fragments": [
                        {
                            "locator_kind": f.locator_kind,
                            "locator": f.locator,
                            "quote": f.quote,
                        }
                        for f in s.fragments
                    ],
                }
                for s in sources
            ],
        }
        parsed = self._invoke_model(
            _EXTRACTION_INSTRUCTION,
            json.dumps(payload_input, ensure_ascii=False),
            RequirementExtractionPayload,
        )

        valid_source_ids = {s.source_version_id for s in sources}
        sources_by_id = {s.source_version_id: s for s in sources}
        requirements: list[ExtractedRequirement] = []

        for draft in parsed.requirements:
            citations = _validate_and_enrich_citations(
                draft.basis, valid_source_ids, sources_by_id
            )
            requirements.append(
                ExtractedRequirement(
                    requirement_id=draft.requirement_id,
                    title=draft.title,
                    obligation=draft.obligation,
                    basis=citations,
                    official_deadline=draft.official_deadline,
                    required_fact_keys=draft.required_fact_keys,
                    is_ambiguous=draft.is_ambiguous,
                    field_key=draft.field_key,
                    scope=draft.scope,
                    value_text=draft.value_text,
                    value_type=draft.value_type,
                    confidence=draft.confidence,
                    rule_kind=draft.rule_kind,
                    rule_parameters=draft.rule_parameters,
                    required_attachments=draft.required_attachments,
                )
            )

        return requirements, list(parsed.gaps), dict(parsed.scope_summary)

    def generate_candidate_plan(
        self,
        context: RunContext,
        sources: list[SourceDocument],
        evaluations: list[RequirementEvaluation],
    ) -> CandidatePlan:
        """Generate a structured CandidatePlan without persisting formal tasks."""
        payload_input = {
            "goal": context.goal.strip(),
            "scope_year": context.scope_year,
            "scope_attrs": sanitize_public_scope_attrs(context.scope_attrs),
            "strategy_version": self._strategy_version,
            "sources": [
                {
                    "source_version_id": s.source_version_id,
                    "title": s.title,
                    "publisher": s.publisher,
                    "year": s.year,
                    "scope": s.scope,
                    "fragments": [
                        {
                            "locator_kind": f.locator_kind,
                            "locator": f.locator,
                        }
                        for f in s.fragments
                    ],
                }
                for s in sources
            ],
            "evaluations": [
                {
                    "requirement_id": ev.requirement_id,
                    "title": ev.title,
                    "status": ev.status.value,
                    "basis": [c.model_dump(mode="json") for c in ev.basis],
                    "scope": ev.scope,
                    "computed_deadline": ev.computed_deadline.isoformat()
                    if ev.computed_deadline is not None
                    else None,
                }
                for ev in evaluations
            ],
        }
        parsed = self._invoke_model(
            _PLANNING_INSTRUCTION,
            json.dumps(payload_input, ensure_ascii=False),
            CandidatePlanDraftPayload,
        )

        valid_source_ids = {s.source_version_id for s in sources}
        sources_by_id = {s.source_version_id: s for s in sources}
        tasks: list[CandidateTask] = []

        for item in parsed.tasks:
            citations = _validate_and_enrich_citations(
                item.basis, valid_source_ids, sources_by_id
            )
            tasks.append(
                CandidateTask(
                    task_id=item.task_id,
                    title=item.title,
                    detail=item.detail,
                    requirement_id=item.requirement_id,
                    basis=citations,
                    obligation=item.obligation,
                    official_deadline=item.official_deadline_at,
                    official_deadline_date=item.official_deadline_date,
                    official_deadline_at=item.official_deadline_at,
                    suggested_date=item.suggested_date,
                    depends_on=item.depends_on,
                    evidence_required=item.evidence_required,
                )
            )

        snapshot_id = sources[0].snapshot_id or sources[0].source_version_id

        return CandidatePlan(
            candidate_id=f"cand-{context.matter_id}",
            workspace_version=context.workspace_version,
            candidate_version=1,
            input_snapshot_id=snapshot_id,
            tasks=tasks,
            scope_summary=dict(parsed.scope_summary),
            gaps=list(parsed.gaps),
        )

    def _invoke_model[T: BaseModel](
        self,
        instruction: str,
        user_text: str,
        response_model: type[T],
    ) -> T:
        try:
            return self._call_model(instruction, user_text, response_model)
        except ModelInvocationError:
            raise
        except TimeoutError as exc:
            raise ModelInvocationError(
                AgentErrorCode.TIMEOUT, f"模型请求超时: {exc}"
            ) from exc
        except ValidationError as exc:
            raise ModelInvocationError(
                AgentErrorCode.VALIDATION_FAILED, f"模型输出不符合结构契约: {exc}"
            ) from exc
        except Exception as exc:
            raw_code = str(getattr(exc, "code", "")).upper()
            if raw_code == "TIMEOUT":
                raise ModelInvocationError(AgentErrorCode.TIMEOUT, str(exc)) from exc
            if raw_code == "INVALID_RESPONSE":
                raise ModelInvocationError(
                    AgentErrorCode.VALIDATION_FAILED, str(exc)
                ) from exc
            raise ModelInvocationError(AgentErrorCode.MODEL_ERROR, str(exc)) from exc


def _normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _validate_and_enrich_citations(
    citations: list[SourceCitation],
    valid_source_ids: set[str],
    sources_by_id: dict[str, SourceDocument],
) -> list[SourceCitation]:
    enriched: list[SourceCitation] = []
    for cite in citations:
        if cite.source_version_id not in valid_source_ids:
            raise ModelInvocationError(
                AgentErrorCode.VALIDATION_FAILED,
                f"模型输出引用了未提供的来源版本 {cite.source_version_id}",
            )
        doc = sources_by_id[cite.source_version_id]

        if (
            cite.source_id is not None
            and doc.source_id is not None
            and cite.source_id != doc.source_id
        ):
            raise ModelInvocationError(
                AgentErrorCode.VALIDATION_FAILED,
                f"引用 {cite.source_version_id} 的 source_id 与真实来源记录不一致",
            )
        if (
            cite.snapshot_id is not None
            and doc.snapshot_id is not None
            and cite.snapshot_id != doc.snapshot_id
        ):
            raise ModelInvocationError(
                AgentErrorCode.VALIDATION_FAILED,
                f"引用 {cite.source_version_id} 的 snapshot_id 与真实来源记录不一致",
            )

        norm_locator = _normalize_ws(cite.locator)
        resolved_excerpt = cite.excerpt
        if cite.excerpt is not None and not _normalize_ws(cite.excerpt):
            raise ModelInvocationError(
                AgentErrorCode.VALIDATION_FAILED,
                f"引用定位 '{cite.locator}' 的摘录不能为空",
            )
        if doc.fragments:
            matching_frags = [
                frag
                for frag in doc.fragments
                if _normalize_ws(frag.locator) == norm_locator
            ]
            if not matching_frags:
                raise ModelInvocationError(
                    AgentErrorCode.VALIDATION_FAILED,
                    f"引用定位 '{cite.locator}' 不在来源 {doc.title} 已提取的片段中",
                )
            kind_matched = [
                frag
                for frag in matching_frags
                if frag.locator_kind == cite.locator_kind
            ]
            if not kind_matched:
                raise ModelInvocationError(
                    AgentErrorCode.VALIDATION_FAILED,
                    f"引用定位 '{cite.locator}' 的类型 {cite.locator_kind} 与来源片段类型不一致",
                )
            if cite.excerpt is not None:
                norm_excerpt = _normalize_ws(cite.excerpt)
                if not any(
                    norm_excerpt in _normalize_ws(frag.quote) for frag in kind_matched
                ):
                    raise ModelInvocationError(
                        AgentErrorCode.VALIDATION_FAILED,
                        f"引用摘录与定位 '{cite.locator}' 对应的原文片段不符",
                    )
            else:
                resolved_excerpt = kind_matched[0].quote
        elif cite.excerpt is not None:
            norm_excerpt = _normalize_ws(cite.excerpt)
            if norm_excerpt not in _normalize_ws(doc.content):
                raise ModelInvocationError(
                    AgentErrorCode.VALIDATION_FAILED,
                    f"引用摘录不在来源 {doc.title} 原文中",
                )

        enriched.append(
            cite.model_copy(
                update={
                    "source_id": doc.source_id or cite.source_id,
                    "snapshot_id": doc.snapshot_id or cite.snapshot_id,
                    "excerpt": resolved_excerpt,
                }
            )
        )
    return enriched
