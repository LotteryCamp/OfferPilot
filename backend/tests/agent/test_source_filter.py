"""Tests for P0 source fragment filtering, deduplication, outbound contracts, and regressions."""

from __future__ import annotations

import gzip
import json
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from backend.agent import (
    PUBLIC_SCOPE_ALLOWLIST,
    EvaluationStatus,
    ExtractedRequirement,
    ObligationType,
    RunContext,
    SourceCitation,
    SourceDocument,
    SourceFragmentRecord,
    deduplicate_sources,
    evaluate_requirements,
    filter_and_deduplicate_fragments,
    sanitize_matter_goal,
    sanitize_public_scope_attrs,
    source_document_from_public_result,
)
from backend.agent.model_bridge import (
    _prepare_extraction_input,
    _prepare_planning_input,
    build_extraction_input,
    build_planning_input,
)
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
    original_fragments = {(f.locator_kind, f.locator, f.quote) for f in doc.fragments}
    assert all(
        (fragment.locator_kind, fragment.locator, fragment.quote) in original_fragments
        for fragment in filtered.fragments
    )

    extraction = build_extraction_input(
        "准备推免申请", [doc], strategy_version="alpha-1"
    )
    assert extraction["sources"][0]["content"] == ""
    assert len(extraction["sources"][0]["fragments"]) == 76
    assert extraction["sources"][0]["fragments"] == [
        {
            "locator_kind": fragment.locator_kind,
            "locator": fragment.locator,
            "quote": fragment.quote,
        }
        for fragment in filtered.fragments
    ]


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
                quote="（1）学业成绩排名前 40%。",
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

    filtered = filter_and_deduplicate_fragments(doc, goal="推免材料与排名核对")
    locator_quotes = [(f.locator, f.quote) for f in filtered.fragments]
    assert locator_quotes == [
        ("一、基本条件", "一、基本条件"),
        ("第1段", "（1）学业成绩排名前 35%。"),
        ("第1段", "（1）学业成绩排名前 40%。"),
        ("第2段", "（1）学业成绩排名前   35%。"),
        ("第3段", "（2）2026年9月9日16:00前提交申请材料。"),
        ("第4段", "（3）须提供加盖公章的成绩单。"),
        ("第5段", "（4）未尽事宜待学院进一步通知。"),
    ]
    assert filtered.dropped_duplicate_count == 1
    assert filtered.dropped_irrelevant_count == 2
    with_required = filter_and_deduplicate_fragments(
        doc,
        goal="推免材料与排名核对",
        required_locators={("text_span", "第6段")},
    )
    assert with_required.fragments == [*filtered.fragments, doc.fragments[-2]]

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
    doc_same_version_different_content = doc_a.model_copy(
        update={
            "content_hash": "b" * 64,
            "fragments": [
                SourceFragmentRecord(
                    locator_kind="text_span", locator="替代记录", quote="不同的原文"
                )
            ],
        }
    )
    doc_different_version_same_content = doc_a.model_copy(
        update={
            "source_version_id": snap_b,
            "snapshot_id": snap_b,
            "scope": "另一适用范围",
        }
    )
    sources = [
        doc_a,
        doc_same_version_different_content,
        doc_different_version_same_content,
    ]
    assert deduplicate_sources(sources) == [doc_a, doc_different_version_same_content]

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

    extraction, extraction_sources = _prepare_extraction_input(
        long_goal, sources, strategy_version="alpha-1"
    )
    assert len(extraction["goal"]) == 200
    assert [source["source_version_id"] for source in extraction["sources"]] == [
        snap_a,
        snap_b,
    ]
    assert [f["locator"] for f in extraction["sources"][0]["fragments"]] == ["第1段"]
    assert extraction_sources[snap_a].fragments == [doc_a.fragments[0]]
    assert extraction_sources[snap_b].scope == "另一适用范围"

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
        confirmed_facts={
            "gpa.rank": 2,
            "cet6": 520,
            "deadline": "2026-09-08T15:00:00+08:00",
            "submitted_at": "2026-09-08T14:00:00+08:00",
        },
    )
    requirements = [
        ExtractedRequirement(
            requirement_id="GR-01",
            title="在个人通知指定时间前提交",
            obligation=ObligationType.OFFICIAL_REQUIRED,
            basis=[
                SourceCitation(
                    source_version_id=snap_b,
                    locator_kind="text_span",
                    locator="第1段",
                )
            ],
            rule_kind="notice_deadline",
            rule_parameters={
                "deadline_fact": "deadline",
                "action_fact": "submitted_at",
            },
        )
    ]
    eval_sources = {snap_b: doc_different_version_same_content}
    ev, _ = evaluate_requirements(requirements, eval_sources, ctx.confirmed_facts)
    assert ev[0].status == EvaluationStatus.MATCHED
    assert ev[0].computed_deadline == datetime.fromisoformat(
        "2026-09-08T15:00:00+08:00"
    )
    planning, planning_sources = _prepare_planning_input(
        ctx, sources, ev, strategy_version="alpha-1"
    )
    assert len(planning["goal"]) == 200
    assert planning["scope_year"] == 2027
    assert planning["scope_attrs"] == {"school": "福州大学"}
    assert "confirmed_facts" not in planning
    assert set(planning["evaluations"][0]) == {
        "requirement_id",
        "title",
        "basis",
        "scope",
    }
    assert [source["source_version_id"] for source in planning["sources"]] == [
        snap_a,
        snap_b,
    ]
    assert planning["sources"][1]["scope"] == "另一适用范围"
    assert planning["evaluations"][0]["basis"][0]["source_version_id"] == snap_b
    assert planning_sources[snap_a].fragments == [doc_a.fragments[0]]
    assert planning_sources[snap_b].fragments == [
        doc_different_version_same_content.fragments[0]
    ]
    assert planning["sources"][0]["fragments"] == [
        {"locator_kind": "text_span", "locator": "第1段"}
    ]
    public_ctx = ctx.model_copy(update={"confirmed_facts": {}})
    public_ev, _ = evaluate_requirements(requirements, eval_sources, {})
    assert public_ev[0].status == EvaluationStatus.MISSING_INFO
    assert (
        build_planning_input(public_ctx, sources, public_ev, strategy_version="alpha-1")
        == planning
    )


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
