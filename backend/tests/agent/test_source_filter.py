"""Tests for P0 source fragment filtering, deduplication, outbound contracts, and regressions."""

from __future__ import annotations

import gzip
import json
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel

from backend.agent import (
    PUBLIC_SCOPE_ALLOWLIST,
    SHANGHAI,
    AgentErrorCode,
    AgentOrchestrator,
    AuthLevel,
    CandidatePlan,
    CandidatePlanDraftPayload,
    CandidateTask,
    CandidateTaskDraft,
    EvaluationStatus,
    ExecutionRecord,
    ExtractedRequirement,
    ExtractedRequirementDraft,
    ObligationType,
    PublicHtmlSourceReader,
    RequirementExtractionPayload,
    RunContext,
    RunStatus,
    SourceCitation,
    SourceDocument,
    SourceFragmentRecord,
    StructuredModelAdapter,
    WrittenTask,
    deduplicate_sources,
    evaluate_requirements,
    filter_and_deduplicate_fragments,
    sanitize_matter_goal,
    sanitize_public_scope_attrs,
    source_document_from_public_result,
    validate_candidate_plan,
)
from backend.agent.model_bridge import build_extraction_input, build_planning_input
from backend.sources.reader import parse_public_html

_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "sources"


def _load_fzu_notice_doc() -> SourceDocument:
    prov = json.loads(
        (_FIXTURES / "fzu_notice_provenance.json").read_text(encoding="utf-8")
    )
    html = gzip.decompress((_FIXTURES / "fzu_notice.html.gz").read_bytes())
    pub = parse_public_html(
        html,
        content_type="text/html; charset=utf-8",
        final_url=prov["url"],
        request={
            "url": prov["url"],
            "publisher": "福州大学数学与统计学院",
            "scope_year": 2027,
        },
        fetched_at=datetime.fromisoformat(prov["retrieved_at"]),
    )
    return source_document_from_public_result(pub)


def test_filter_fzu_notice_drops_portal_noise_and_keeps_policy_verbatim() -> None:
    doc = _load_fzu_notice_doc()
    assert len(doc.fragments) == 102

    filtered = filter_and_deduplicate_fragments(
        doc,
        goal="核对2027届福州大学数统学院校内推免材料与截止时间",
        scope_attrs={"school": "福州大学", "college": "数学与统计学院"},
    )
    assert filtered.dropped_noise_count == 26
    assert filtered.dropped_duplicate_count == 0
    assert filtered.dropped_irrelevant_count == 0
    assert len(filtered.fragments) == 76

    quotes = [f.quote for f in filtered.fragments]
    assert "\ufeff" not in quotes
    assert "设为首页" not in quotes
    assert "网站首页 >" not in quotes
    assert "上一篇 下一篇" not in quotes
    assert all(not q.startswith("学院概况") for q in quotes)
    assert all("邮编：350108" not in q for q in quotes)

    assert any("2026年9月10日下午15:00前" in q for q in quotes)
    assert any(
        f.locator_kind == "table_row" and "经济统计学 7" in f.quote
        for f in filtered.fragments
    )
    assert any("附件【福州大学数学与统计学院2027年" in q for q in quotes)

    extraction = build_extraction_input(
        "准备推免申请", [doc], strategy_version="alpha-1"
    )
    assert extraction["sources"][0]["content"] == ""
    assert len(extraction["sources"][0]["fragments"]) == 76

    target_frag = next(
        f for f in filtered.fragments if "2026年9月10日下午15:00前" in f.quote
    )

    def replay_call_model[T: BaseModel](
        instruction: str,
        text: str,
        response_model: type[T],
    ) -> T:
        payload = json.loads(text)
        assert len(payload["sources"][0]["fragments"]) == 76
        assert response_model is RequirementExtractionPayload
        return response_model.model_validate(
            RequirementExtractionPayload(
                requirements=[
                    ExtractedRequirementDraft(
                        requirement_id="GR-02",
                        title="提交推免申请材料截止",
                        obligation=ObligationType.OFFICIAL_REQUIRED,
                        basis=[
                            SourceCitation(
                                source_version_id=doc.source_version_id,
                                locator_kind=target_frag.locator_kind,
                                locator=target_frag.locator,
                                excerpt="2026年9月10日下午15:00前提交",
                            )
                        ],
                        value_text="2026-09-10",
                        value_type="date",
                        official_deadline=datetime(2026, 9, 10, 15, 0, tzinfo=SHANGHAI),
                    )
                ]
            ).model_dump()
        )

    adapter = StructuredModelAdapter(replay_call_model)
    reqs, _, _ = adapter.extract_requirements_with_metadata("准备推免申请", [doc])
    assert len(reqs) == 1
    assert reqs[0].basis[0].locator == target_frag.locator
    assert reqs[0].basis[0].locator_kind == target_frag.locator_kind


def test_fragment_dedup_irrelevant_filter_and_fallback_guard() -> None:
    snap_id = str(uuid4())
    doc = SourceDocument(
        source_version_id=snap_id,
        source_id=str(uuid4()),
        snapshot_id=snap_id,
        title="2027年推免工作方案",
        publisher="某学院",
        content="正文",
        fragments=[
            SourceFragmentRecord(
                locator_kind="section",
                locator="一、基本条件",
                quote="一、基本条件",
            ),
            SourceFragmentRecord(
                locator_kind="text_span",
                locator="第1段",
                quote="（1）学业成绩排名前 35%。",
            ),
            SourceFragmentRecord(
                locator_kind="text_span",
                locator="第1段",
                quote="（1）学业成绩排名前 35%。",
            ),
            SourceFragmentRecord(
                locator_kind="text_span",
                locator="第2段",
                quote="（1）学业成绩排名前   35%。",
            ),
            SourceFragmentRecord(
                locator_kind="text_span",
                locator="第3段",
                quote="（2）2026年9月9日16:00前提交申请材料。",
            ),
            SourceFragmentRecord(
                locator_kind="text_span",
                locator="第4段",
                quote="（3）须提供加盖公章的成绩单。",
            ),
            SourceFragmentRecord(
                locator_kind="text_span",
                locator="第5段",
                quote="（4）未尽事宜待学院进一步通知。",
            ),
            SourceFragmentRecord(
                locator_kind="text_span",
                locator="第6段",
                quote="2026-09-03 学院召开工会健步走活动筹备会",
            ),
            SourceFragmentRecord(
                locator_kind="text_span",
                locator="第7段",
                quote="关于2026年中秋节放假值班安排的通知",
            ),
        ],
    )

    filtered = filter_and_deduplicate_fragments(
        doc,
        goal="推免材料与排名核对",
        required_locators={("text_span", "第2段")},
    )
    locators = [f.locator for f in filtered.fragments]
    assert locators == ["一、基本条件", "第1段", "第2段", "第3段", "第4段", "第5段"]
    assert filtered.dropped_duplicate_count == 1
    assert filtered.dropped_irrelevant_count == 2

    # Fallback keeps deduplicated non-empty fragments if all lines match noise rules.
    chrome_only_doc = SourceDocument(
        source_version_id=str(uuid4()),
        title="仅页眉页脚",
        publisher="某学院",
        content="设为首页",
        fragments=[
            SourceFragmentRecord(
                locator_kind="text_span", locator="第1段", quote="设为首页"
            ),
            SourceFragmentRecord(
                locator_kind="text_span", locator="第1段", quote="设为首页"
            ),
            SourceFragmentRecord(
                locator_kind="text_span", locator="第2段", quote="\ufeff"
            ),
        ],
    )
    fallback = filter_and_deduplicate_fragments(chrome_only_doc)
    assert [f.locator for f in fallback.fragments] == ["第1段"]


def test_deduplicate_sources_and_outbound_whitelist_contract() -> None:
    shared_src_id = str(uuid4())
    shared_hash = "a" * 64
    snap_a = str(uuid4())
    snap_b = str(uuid4())

    doc_a = SourceDocument(
        source_version_id=snap_a,
        source_id=shared_src_id,
        snapshot_id=snap_a,
        title="学院推荐通知",
        publisher="某学院",
        content="全文",
        content_hash=shared_hash,
        fragments=[
            SourceFragmentRecord(
                locator_kind="text_span",
                locator="第1段",
                quote="申请材料须于2026年9月10日前提交。",
            ),
            SourceFragmentRecord(
                locator_kind="text_span",
                locator="第2段",
                quote="设为首页",
            ),
        ],
    )
    doc_same_version = doc_a.model_copy()
    doc_same_content = doc_a.model_copy(
        update={"source_version_id": snap_b, "snapshot_id": snap_b}
    )

    assert len(deduplicate_sources([doc_a, doc_same_version, doc_same_content])) == 1

    long_goal = "  " + ("准备推免申请材料" * 40) + "  "
    assert len(sanitize_matter_goal(long_goal)) == 200

    assert PUBLIC_SCOPE_ALLOWLIST == frozenset(
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
    sanitized_scope = sanitize_public_scope_attrs(
        {
            "school": " 福州大学 ",
            "scope_year": 2027,
            "rank_position": 2,
            "phone": "13800138000",
            "email": "student@example.com",
        }
    )
    assert sanitized_scope == {"school": "福州大学"}

    extraction = build_extraction_input(
        long_goal, [doc_a, doc_same_content], strategy_version="alpha-1"
    )
    assert len(extraction["goal"]) == 200
    assert len(extraction["sources"]) == 1
    assert [f["locator"] for f in extraction["sources"][0]["fragments"]] == ["第1段"]

    ctx = RunContext(
        user_id="u1",
        matter_id="m1",
        goal=long_goal,
        workspace_version=1,
        scope_year=2027,
        scope_attrs={
            "school": "福州大学",
            "scope_year": 2027,
            "rank_position": 2,
            "email": "student@example.com",
        },
        confirmed_facts={"gpa.rank": 2, "cet6": 520},
    )
    ev = [
        evaluate_requirements(
            [
                ExtractedRequirement(
                    requirement_id="GR-01",
                    title="英语六级",
                    obligation=ObligationType.OFFICIAL_REQUIRED,
                    basis=[
                        SourceCitation(
                            source_version_id=snap_a,
                            locator_kind="text_span",
                            locator="第1段",
                        )
                    ],
                    rule_kind="any_minimum",
                    rule_parameters={"minimum": {"cet6": 425}, "operator": ">="},
                )
            ],
            {snap_a: doc_a},
            ctx.confirmed_facts,
        )[0][0]
    ]
    planning = build_planning_input(
        ctx, [doc_a, doc_same_content], ev, strategy_version="alpha-1"
    )
    assert len(planning["goal"]) == 200
    assert planning["scope_year"] == 2027
    assert planning["scope_attrs"] == {"school": "福州大学"}
    assert "confirmed_facts" not in planning
    assert "520" not in json.dumps(planning, ensure_ascii=False)
    assert len(planning["sources"]) == 1
    assert planning["sources"][0]["fragments"] == [
        {"locator_kind": "text_span", "locator": "第1段"}
    ]


def test_p0_end_to_end_insufficient_evidence_and_no_formal_tasks_before_confirm() -> (
    None
):
    doc = _load_fzu_notice_doc()
    target_frag = next(
        f for f in doc.fragments if "2026年9月10日下午15:00前" in f.quote
    )

    class _Backend:
        def __init__(self) -> None:
            self.records: list[ExecutionRecord] = []

        def check_permission(
            self, user_id: str, matter_id: str, auth_level: AuthLevel
        ) -> bool:
            return True

        def has_valid_transfer_consent(
            self,
            user_id: str,
            *,
            purpose: str,
            field_categories: tuple[str, ...],
        ) -> bool:
            return True

        def get_workspace_version(self, matter_id: str) -> int:
            return 1

        def consume_candidate_and_write_tasks(
            self,
            user_id: str,
            matter_id: str,
            candidate_plan: CandidatePlan,
            expected_workspace_version: int,
            operation_id: str,
        ) -> list[WrittenTask]:
            return []

        def record_execution(self, matter_id: str, record: ExecutionRecord) -> None:
            self.records.append(record)

    class _Persistence:
        def __init__(self) -> None:
            self.plans: dict[str, dict[str, Any]] = {}
            self.written_tasks: list[dict[str, Any]] = []

        def persist_requirements(
            self, matter_id: str, payload: dict[str, Any]
        ) -> list[dict[str, Any]]:
            return [{"id": str(uuid4()), **item} for item in payload["requirements"]]

        def persist_candidate_plan(
            self, matter_id: str, payload: dict[str, Any]
        ) -> dict[str, Any]:
            plan_id = str(uuid4())
            self.plans[plan_id] = {
                "id": plan_id,
                "matter_id": matter_id,
                "status": "pending",
                "items": payload["items"],
                "tasks": [],
            }
            return self.plans[plan_id]

        def get_candidate_plan(self, plan_id: str) -> dict[str, Any]:
            return self.plans[plan_id]

        def confirm_candidate_plan(
            self, plan_id: str, *, operation_id: str
        ) -> dict[str, Any]:
            return {"plan_id": plan_id, "status": "confirmed", "tasks": []}

        def reject_candidate_plan(
            self, plan_id: str, *, operation_id: str
        ) -> dict[str, Any]:
            return {"plan_id": plan_id, "status": "rejected", "tasks": []}

    def call_model[T: BaseModel](
        instruction: str,
        text: str,
        response_model: type[T],
    ) -> T:
        payload = json.loads(text)
        assert len(payload["sources"][0]["fragments"]) == 76
        if response_model is RequirementExtractionPayload:
            return response_model.model_validate(
                RequirementExtractionPayload(
                    requirements=[
                        ExtractedRequirementDraft(
                            requirement_id="GR-01",
                            title="上位校级推荐文件要求",
                            obligation=ObligationType.PENDING_VERIFICATION,
                            basis=[
                                SourceCitation(
                                    source_version_id=doc.source_version_id,
                                    locator_kind=target_frag.locator_kind,
                                    locator=target_frag.locator,
                                    excerpt="2026年9月10日下午15:00前提交",
                                )
                            ],
                            is_ambiguous=True,
                        )
                    ]
                ).model_dump()
            )
        return response_model.model_validate(
            CandidatePlanDraftPayload(
                tasks=[
                    CandidateTaskDraft(
                        task_id="T-01",
                        title="核对校级上位文件与个人资格",
                        requirement_id="GR-01",
                        basis=[
                            SourceCitation(
                                source_version_id=doc.source_version_id,
                                locator_kind=target_frag.locator_kind,
                                locator=target_frag.locator,
                                excerpt="2026年9月10日下午15:00前提交",
                            )
                        ],
                        obligation=ObligationType.PENDING_VERIFICATION,
                        evidence_required="校级文件核对记录",
                    ),
                    CandidateTaskDraft(
                        task_id="T-02",
                        title="准备学院申请表与证明材料",
                        requirement_id="GR-01",
                        basis=[
                            SourceCitation(
                                source_version_id=doc.source_version_id,
                                locator_kind=target_frag.locator_kind,
                                locator=target_frag.locator,
                                excerpt="2026年9月10日下午15:00前提交",
                            )
                        ],
                        obligation=ObligationType.OFFICIAL_REQUIRED,
                        depends_on=["T-01"],
                        evidence_required="申请表及成绩单",
                    ),
                ]
            ).model_dump()
        )

    persistence = _Persistence()
    orch = AgentOrchestrator(
        source_reader=PublicHtmlSourceReader(preloaded_sources=[doc]),
        model_adapter=StructuredModelAdapter(call_model),
        backend=_Backend(),
        persistence=persistence,
        clock=lambda: datetime(2026, 9, 9, 9, 0, tzinfo=SHANGHAI),
    )
    result = orch.start_run(
        RunContext(
            user_id=str(uuid4()),
            matter_id=str(uuid4()),
            goal="核对2027届校内推免材料",
            workspace_version=1,
            scope_year=2027,
            scope_attrs={"school": "福州大学", "college": "数学与统计学院"},
        )
    )
    assert result.status == RunStatus.WAITING_CONFIRMATION
    assert result.evaluations[0].status == EvaluationStatus.NEEDS_USER_REVIEW
    assert result.candidate_plan is not None
    assert validate_candidate_plan(result.candidate_plan, 1) == []
    assert persistence.written_tasks == []
    assert result.written_tasks == []

    # Invalid dependency on nonexistent task fails validation before formal persistence.
    bad_plan = result.candidate_plan.model_copy(
        update={
            "tasks": [
                CandidateTask(
                    task_id="T-01",
                    title="缺失依赖测试",
                    basis=result.candidate_plan.tasks[0].basis,
                    obligation=ObligationType.OFFICIAL_REQUIRED,
                    depends_on=["T-99"],
                    evidence_required="材料",
                )
            ]
        }
    )
    assert validate_candidate_plan(bad_plan, 1)
    assert AgentErrorCode.VALIDATION_FAILED.value == "VALIDATION_FAILED"


def test_filter_individual_nav_links_and_material_college_footer() -> None:
    snap_id = str(uuid4())
    heading = "【研究生】材料科学与工程学院2027年推荐免试研究生接收工作复试方案"
    doc = SourceDocument(
        source_version_id=snap_id,
        source_id=str(uuid4()),
        snapshot_id=snap_id,
        title=heading,
        publisher="福州大学材料科学与工程学院",
        content="正文",
        fragments=[
            SourceFragmentRecord(
                locator_kind="text_span", locator="第1段", quote="\ufeff"
            ),
            SourceFragmentRecord(
                locator_kind="text_span", locator="第2段", quote="English | 中文"
            ),
            SourceFragmentRecord(
                locator_kind="text_span", locator="第3段", quote="首页"
            ),
            SourceFragmentRecord(
                locator_kind="text_span", locator="第4段", quote="学院概况"
            ),
            SourceFragmentRecord(
                locator_kind="text_span", locator="第5段", quote="学院简介"
            ),
            SourceFragmentRecord(
                locator_kind="text_span", locator="第6段", quote="现任领导"
            ),
            SourceFragmentRecord(
                locator_kind="text_span", locator="第7段", quote="创新实验班"
            ),
            SourceFragmentRecord(
                locator_kind="text_span",
                locator="第8段",
                quote="学习贯彻习近平新时代中国特色社会主义思想",
            ),
            SourceFragmentRecord(
                locator_kind="text_span", locator="第9段", quote="修改简历"
            ),
            SourceFragmentRecord(
                locator_kind="text_span", locator="第10段", quote="当前位置:"
            ),
            SourceFragmentRecord(
                locator_kind="text_span", locator="第11段", quote="首页"
            ),
            SourceFragmentRecord(
                locator_kind="text_span", locator="第12段", quote=">>"
            ),
            SourceFragmentRecord(
                locator_kind="text_span", locator="第13段", quote="通知文件"
            ),
            SourceFragmentRecord(
                locator_kind="text_span", locator="第14段", quote=">>"
            ),
            SourceFragmentRecord(
                locator_kind="text_span", locator="第15段", quote="正文"
            ),
            SourceFragmentRecord(
                locator_kind="section", locator=heading, quote=heading
            ),
            SourceFragmentRecord(
                locator_kind="text_span",
                locator="第16段",
                quote="发布者： 发布时间： 2026-09-17 浏览量：",
            ),
            SourceFragmentRecord(
                locator_kind="text_span",
                locator="第17段",
                quote="正式报名须在北京时间 2026-09-22 08:00 前完成。",
            ),
            SourceFragmentRecord(
                locator_kind="text_span",
                locator="第18段",
                quote="附件下载 附件4_福州大学学生体格检查表.pdf 【已下载 次】",
            ),
            SourceFragmentRecord(
                locator_kind="text_span", locator="第19段", quote="上一篇"
            ),
            SourceFragmentRecord(
                locator_kind="text_span", locator="第20段", quote="下一篇"
            ),
            SourceFragmentRecord(
                locator_kind="text_span",
                locator="第21段",
                quote="版权所有:福州大学材料科学与工程学院 地址: 福建省福州市福州地区大学新区学园路2号 邮编: 350108",
            ),
            SourceFragmentRecord(
                locator_kind="text_span", locator="第22段", quote="联系我们"
            ),
        ],
    )

    filtered = filter_and_deduplicate_fragments(
        doc,
        goal="核对材料学院2027年推免接收与复试方案",
        scope_attrs={"school": "福州大学", "college": "材料科学与工程学院"},
    )
    assert filtered.dropped_noise_count == 19
    assert [f.locator for f in filtered.fragments] == [
        heading,
        "第16段",
        "第17段",
        "第18段",
    ]
    assert filtered.fragments[-1].quote == (
        "附件下载 附件4_福州大学学生体格检查表.pdf 【已下载 次】"
    )
