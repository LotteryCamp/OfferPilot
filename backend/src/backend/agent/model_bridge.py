"""Bridge adapting PR #38 structured LLM adapter to ModelAdapterPort."""

from __future__ import annotations

import importlib
import json
import re
from collections.abc import Callable, Iterable, Mapping
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
from backend.agent.source_filter import (
    deduplicate_sources,
    filter_and_deduplicate_fragments,
)
from backend.config import Settings
from backend.fact_types import supported_fact_types


class CallModelFn(Protocol):
    """Callable matching PR #38 backend.model_adapter.call_model signature."""

    def __call__[T: BaseModel](
        self,
        instruction: str,
        text: str,
        response_model: type[T],
    ) -> T: ...


MATTER_GOAL_MAX_LEN = 200

PUBLIC_SCOPE_ALLOWLIST = frozenset(
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
        "region",
    }
)
_PUBLIC_SCOPE_ALLOWLIST = PUBLIC_SCOPE_ALLOWLIST


def sanitize_matter_goal(goal: str) -> str:
    """Trim matter goal and cap outbound text at 200 characters."""
    return goal.strip()[:MATTER_GOAL_MAX_LEN].strip()


def sanitize_public_scope_attrs(scope_attrs: Mapping[str, Any]) -> dict[str, Any]:
    """Keep only allowlisted public academic scope fields for external model payloads."""
    sanitized: dict[str, Any] = {}
    for key, value in scope_attrs.items():
        if key not in PUBLIC_SCOPE_ALLOWLIST:
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
    "   当 value_type 为 date 时，value_text 必须严格使用 YYYY-MM-DD 格式（如 2026-09-10），严禁填中文日期或带时刻描述；"
    "精确时刻请单独填入 official_deadline（带时区 ISO 8601）。value_type 为 number 时 value_text 须为纯数字，boolean 时须为 true 或 false。\n"
    "3. 不同条件或适用人群（如申请推荐与放弃推荐）须拆开标注 scope。\n"
    "4. 缺少上位文件、附件或个人依据时，在 gaps 中显式记录，禁止得出最终资格认定。\n"
    "5. 若条款涉及已登记个人事实，field_key、required_fact_keys 与 rule_parameters 中的 fact/键名必须使用标准事实键，禁止自造同义键：\n"
    "   - 标准事实键：gpa.rank（学业排名百分位，0–100 数值越小越靠前，如 10/100 对应 10，“前 N%”使用 <= N）、"
    "gpa.score（0–4.0 绩点）、cet4、cet6、toefl、ielts、cert、comp。\n"
    "   - 可执行规则：\n"
    "     * 排名阈值或“前 N% 且无补考重修 / 前 M% 且至多 1 门”等复合条件使用 rule_kind='any_of'，rule_parameters 为 "
    '{"all_required": [{"fact": str, "operator": "<=" | "<" | ">=" | ">" | "==", "value": num|bool|str}], '
    '"paths": [{"label": str, "checks": [{"fact": str, "operator": ..., "value": ...}]}]}；\n'
    '     * 多项英语分数任一达标使用 rule_kind=\'any_minimum\'，rule_parameters 为 {"minimum": {"cet6": 425, "cet4": 480}, "operator": ">="}；\n'
    '     * 固定期限/材料清单/缺位核对分别使用 fixed_deadline（{"before": ISO8601, "fact": str, "operator": "<="}）、'
    'materials（{"required_facts": [str]}）、coverage_gap（{"missing_documents": [str]}）。\n'
    '   - 涉及学业排名要求时，field_key 固定填 "gpa.rank"。'
)


def _collect_rule_parameter_fact_keys(rule_parameters: Mapping[str, Any]) -> list[str]:
    keys: list[str] = []
    all_required = rule_parameters.get("all_required")
    if isinstance(all_required, list):
        for check in all_required:
            if isinstance(check, Mapping) and isinstance(check.get("fact"), str):
                fact = check["fact"].strip()
                if fact:
                    keys.append(fact)

    paths = rule_parameters.get("paths")
    if isinstance(paths, list):
        for path in paths:
            if not isinstance(path, Mapping):
                continue
            checks = path.get("checks")
            if isinstance(checks, list):
                for check in checks:
                    if isinstance(check, Mapping) and isinstance(
                        check.get("fact"), str
                    ):
                        fact = check["fact"].strip()
                        if fact:
                            keys.append(fact)

    minimum = rule_parameters.get("minimum")
    if isinstance(minimum, Mapping):
        for key in minimum:
            if isinstance(key, str) and key.strip():
                keys.append(key.strip())

    required_facts = rule_parameters.get("required_facts")
    if isinstance(required_facts, list):
        for key in required_facts:
            if isinstance(key, str) and key.strip():
                keys.append(key.strip())

    fact_key = rule_parameters.get("fact")
    if isinstance(fact_key, str) and fact_key.strip():
        keys.append(fact_key.strip())
    return keys


def normalize_requirement_field_key(draft: ExtractedRequirementDraft) -> str | None:
    """Align extracted field_key to a uniquely referenced registered personal fact type."""
    registered = set(supported_fact_types())
    if draft.field_key in registered:
        return draft.field_key

    candidates = _collect_rule_parameter_fact_keys(draft.rule_parameters)
    candidates.extend(
        k.strip() for k in draft.required_fact_keys if isinstance(k, str) and k.strip()
    )
    registered_refs = list(dict.fromkeys(k for k in candidates if k in registered))
    if len(registered_refs) == 1:
        return registered_refs[0]
    return draft.field_key


def collect_registered_fact_types(
    requirements: Iterable[ExtractedRequirement | ExtractedRequirementDraft],
) -> list[str]:
    """Collect sorted unique registered fact types referenced by requirements."""
    registered = set(supported_fact_types())
    found: set[str] = set()
    for req in requirements:
        if req.field_key and req.field_key in registered:
            found.add(req.field_key)
        for key in _collect_rule_parameter_fact_keys(req.rule_parameters):
            if key in registered:
                found.add(key)
        for key in req.required_fact_keys:
            if isinstance(key, str) and key.strip() in registered:
                found.add(key.strip())
    return sorted(found)


_PLANNING_INSTRUCTION = (
    "你是 OfferPilot 候选计划生成助手。仅根据已核实来源和公开要求摘要生成待用户确认的候选任务：\n"
    "1. 每条候选任务必须包含来自输入 sources 的 source_version_id 与 locator。"
    "当来源对象包含非空 fragments 列表时，basis[*].locator 必须原样复制对应片段的 fragments[*].locator（或沿用 evaluations.basis 中的 locator），"
    "locator_kind 必须匹配该片段。可复制 evaluations.basis 中对应的原文摘录；无对应摘录时省略 excerpt。\n"
    "2. 官方日期存入 official_deadline_date，仅原文给出时刻时填写 official_deadline_at（带时区），"
    "个人建议准备日存入 suggested_date，不高于官方期限。\n"
    "3. task_id 优先使用简短编号（如 T-01、T-02）；depends_on 中的每一项必须逐字等于本计划内某条任务的完整 task_id（禁止只写编号前缀），"
    "不得引用不存在的任务，且不得成环。\n"
    "4. 缺依据或条件不清时在 gaps 中明确说明，不编造确定性结论。"
)


def build_extraction_input(
    goal: str,
    sources: list[SourceDocument],
    *,
    strategy_version: str,
) -> dict[str, Any]:
    """Build the model input for requirement extraction, carrying filtered source fragments."""
    payload, _ = _prepare_extraction_input(
        goal, sources, strategy_version=strategy_version
    )
    return payload


def _prepare_extraction_input(
    goal: str,
    sources: list[SourceDocument],
    *,
    strategy_version: str,
) -> tuple[dict[str, Any], dict[str, SourceDocument]]:
    clean_goal = sanitize_matter_goal(goal)
    citation_sources: dict[str, SourceDocument] = {}
    sources_payload: list[dict[str, Any]] = []
    for s in deduplicate_sources(sources):
        filtered = filter_and_deduplicate_fragments(s, goal=clean_goal)
        citation_sources[s.source_version_id] = s.model_copy(
            update={"fragments": filtered.fragments}
        )
        sources_payload.append(
            {
                "source_version_id": s.source_version_id,
                "source_id": s.source_id,
                "snapshot_id": s.snapshot_id,
                "title": s.title,
                "publisher": s.publisher,
                "year": s.year,
                "scope": s.scope,
                "content": "" if filtered.fragments else s.content,
                "missing_attachments": s.missing_attachments,
                "fragments": [
                    {
                        "locator_kind": f.locator_kind,
                        "locator": f.locator,
                        "quote": f.quote,
                    }
                    for f in filtered.fragments
                ],
            }
        )
    return {
        "goal": clean_goal,
        "strategy_version": strategy_version,
        "sources": sources_payload,
    }, citation_sources


def build_planning_input(
    context: RunContext,
    sources: list[SourceDocument],
    evaluations: list[RequirementEvaluation],
    *,
    strategy_version: str,
) -> dict[str, Any]:
    """Build the model input for candidate planning from public fields only."""
    payload, _ = _prepare_planning_input(
        context, sources, evaluations, strategy_version=strategy_version
    )
    return payload


def _prepare_planning_input(
    context: RunContext,
    sources: list[SourceDocument],
    evaluations: list[RequirementEvaluation],
    *,
    strategy_version: str,
) -> tuple[dict[str, Any], dict[str, SourceDocument]]:
    clean_goal = sanitize_matter_goal(context.goal)
    clean_scope_attrs = sanitize_public_scope_attrs(context.scope_attrs)
    required_by_source: dict[str, set[tuple[str, str]]] = {}
    for ev in evaluations:
        for cite in ev.basis:
            required_by_source.setdefault(cite.source_version_id, set()).add(
                (cite.locator_kind, _normalize_ws(cite.locator))
            )

    citation_sources: dict[str, SourceDocument] = {}
    sources_payload: list[dict[str, Any]] = []
    for s in deduplicate_sources(sources):
        filtered = filter_and_deduplicate_fragments(
            s,
            goal=clean_goal,
            scope_attrs=clean_scope_attrs,
            required_locators=required_by_source.get(s.source_version_id),
        )
        citation_sources[s.source_version_id] = s.model_copy(
            update={"fragments": filtered.fragments}
        )
        sources_payload.append(
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
                    for f in filtered.fragments
                ],
            }
        )

    return {
        "goal": clean_goal,
        "scope_year": context.scope_year,
        "scope_attrs": clean_scope_attrs,
        "strategy_version": strategy_version,
        "sources": sources_payload,
        "evaluations": [
            {
                "requirement_id": ev.requirement_id,
                "title": ev.title,
                "basis": [c.model_dump(mode="json") for c in ev.basis],
                "scope": ev.scope,
            }
            for ev in evaluations
        ],
    }, citation_sources


class StructuredModelAdapter:
    """ModelAdapterPort implementation backed by PR #38 call_model."""

    def __init__(
        self,
        call_model_fn: CallModelFn,
        *,
        strategy_version: str = "1.0",
    ) -> None:
        self._call_model = call_model_fn
        self._strategy_version = strategy_version
        self.last_gaps: list[SourceGap] = []
        self.last_scope_summary: dict[str, Any] = {}

    @classmethod
    def from_backend_adapter(
        cls,
        settings_provider: Callable[[], Settings] | None = None,
        *,
        strategy_version: str = "1.0",
    ) -> StructuredModelAdapter:
        """Construct adapter using PR #38 backend.model_adapter.call_model."""
        try:
            module = importlib.import_module("backend.model_adapter")
        except ImportError as exc:
            raise ModelInvocationError(
                AgentErrorCode.MODEL_ERROR,
                "未找到 backend.model_adapter，请先安装或合入模型适配模块",
            ) from exc
        if settings_provider is None:
            return cls(module.call_model, strategy_version=strategy_version)

        def bound_call_model[T: BaseModel](
            instruction: str,
            text: str,
            response_model: type[T],
        ) -> T:
            return module.call_model(
                instruction,
                text,
                response_model,
                settings=settings_provider(),
            )

        return cls(bound_call_model, strategy_version=strategy_version)

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
        payload_input, sources_by_id = _prepare_extraction_input(
            goal, sources, strategy_version=self._strategy_version
        )
        parsed = self._invoke_model(
            _EXTRACTION_INSTRUCTION,
            json.dumps(payload_input, ensure_ascii=False),
            RequirementExtractionPayload,
        )

        valid_source_ids = set(sources_by_id)
        requirements: list[ExtractedRequirement] = []

        for draft in parsed.requirements:
            citations = _validate_and_enrich_citations(
                draft.basis, valid_source_ids, sources_by_id
            )
            value_text = _normalize_model_value_text(
                draft.value_text,
                draft.value_type,
                official_deadline=draft.official_deadline,
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
                    field_key=normalize_requirement_field_key(draft),
                    scope=draft.scope,
                    value_text=value_text,
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
        payload_input, sources_by_id = _prepare_planning_input(
            context,
            sources,
            evaluations,
            strategy_version=self._strategy_version,
        )
        parsed = self._invoke_model(
            _PLANNING_INSTRUCTION,
            json.dumps(payload_input, ensure_ascii=False),
            CandidatePlanDraftPayload,
        )

        valid_source_ids = set(sources_by_id)
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

        tasks = _resolve_task_dependency_prefixes(tasks)
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


_CALENDAR_DATE_RE = re.compile(
    r"(?P<year>\d{4})\s*(?:年|[./-])\s*(?P<month>\d{1,2})\s*(?:月|[./-])\s*(?P<day>\d{1,2})\s*日?"
)


def _normalize_model_value_text(
    value_text: str | None,
    value_type: Literal["text", "date", "number", "boolean", "enum"],
    *,
    official_deadline: datetime | None = None,
) -> str | None:
    if value_text is None:
        if value_type == "date" and official_deadline is not None:
            return official_deadline.date().isoformat()
        return None
    stripped = value_text.strip()
    if not stripped:
        if value_type == "date" and official_deadline is not None:
            return official_deadline.date().isoformat()
        return None
    if value_type == "date":
        if len(stripped) == 10:
            try:
                return date.fromisoformat(stripped).isoformat()
            except ValueError as exc:
                raise ModelInvocationError(
                    AgentErrorCode.VALIDATION_FAILED,
                    f"模型返回的日期 {stripped} 无效",
                ) from exc
        try:
            return datetime.fromisoformat(stripped).date().isoformat()
        except ValueError:
            pass
        match = _CALENDAR_DATE_RE.search(stripped)
        if match is not None:
            try:
                parsed_date = date(
                    int(match.group("year")),
                    int(match.group("month")),
                    int(match.group("day")),
                )
            except ValueError as exc:
                raise ModelInvocationError(
                    AgentErrorCode.VALIDATION_FAILED,
                    f"模型返回的日期 {stripped} 无效",
                ) from exc
            return parsed_date.isoformat()
        if official_deadline is not None:
            return official_deadline.date().isoformat()
        raise ModelInvocationError(
            AgentErrorCode.VALIDATION_FAILED,
            f"date 类型 value_text 无法规范化为 YYYY-MM-DD：{stripped}",
        )
    if value_type == "boolean":
        lowered = stripped.lower()
        if lowered in {"true", "false"}:
            return lowered
    return stripped


def _resolve_task_dependency_prefixes(
    tasks: list[CandidateTask],
) -> list[CandidateTask]:
    """Resolve unambiguous task_id prefix shorthands (e.g. 'T01' -> 'T01-xxx') in depends_on."""
    ordered_ids = [t.task_id for t in tasks]
    exact_ids = set(ordered_ids)
    resolved_tasks: list[CandidateTask] = []

    for task in tasks:
        if not task.depends_on:
            resolved_tasks.append(task)
            continue
        new_deps: list[str] = []
        seen: set[str] = set()
        for raw_dep in task.depends_on:
            dep = raw_dep.strip()
            if not dep:
                mapped = raw_dep
            elif dep in exact_ids:
                mapped = dep
            else:
                matches = [
                    tid for tid in ordered_ids if tid.startswith((f"{dep}-", f"{dep}_"))
                ]
                mapped = matches[0] if len(matches) == 1 else raw_dep
            if mapped not in seen:
                seen.add(mapped)
                new_deps.append(mapped)
        if new_deps == task.depends_on:
            resolved_tasks.append(task)
        else:
            resolved_tasks.append(task.model_copy(update={"depends_on": new_deps}))

    return resolved_tasks


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
                if not any(cite.excerpt in frag.quote for frag in kind_matched):
                    raise ModelInvocationError(
                        AgentErrorCode.VALIDATION_FAILED,
                        f"引用摘录与定位 '{cite.locator}' 对应的原文片段不符",
                    )
            else:
                resolved_excerpt = kind_matched[0].quote
        elif cite.excerpt is not None and cite.excerpt not in doc.content:
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
