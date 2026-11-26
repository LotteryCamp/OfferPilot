"""Deterministic filtering and deduplication for public official source fragments."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from backend.agent.schemas import SourceDocument, SourceFragmentRecord

_INVISIBLE_CHARS = "\ufeff\u200b\u200c\u200d\u00a0"
_INVISIBLE_TRANS = str.maketrans("", "", _INVISIBLE_CHARS)

_EXACT_PORTAL_CHROME = frozenset(
    {
        "设为首页",
        "加入收藏",
        "网站首页",
        "首页",
        "返回首页",
        "正文",
        "打印本页",
        "关闭窗口",
        "分享到",
        "上一篇",
        "下一篇",
        "上一篇 下一篇",
        "上一条",
        "下一条",
        "旧版入口",
        "联系我们",
        "站内搜索",
        "搜索",
        "登录",
        "注册",
        "网站地图",
        "版权所有",
        "隐私政策",
        "学院动态",
        "学院新闻",
        "通知公告",
        "院内公示",
        "教务公告",
        "学术动态",
        "招生信息",
        "教学动态",
        "通知通告",
        ">",
        ">>",
        "»",
        "›",
    }
)

_NAV_PREFIXES = (
    "学院概况",
    "学院动态",
    "师资队伍",
    "本科教育",
    "本科教学",
    "研究生教育",
    "科研工作",
    "科学研究",
    "学生工作",
    "党建工作",
    "党群工作",
    "教工之家",
    "校友会",
    "校友工作",
    "服务指南",
    "对外交流",
    "合作交流",
    "机构设置",
    "学科建设",
    "人才培养",
    "招生就业",
    "信息公开",
    "下载专区",
    "教学科研",
)

_POST_FOOTER_SENTINELS = frozenset(
    {
        "上一篇 下一篇",
        "上一篇",
        "下一篇",
        "上一条",
        "下一条",
        "相关新闻",
        "相关阅读",
        "推荐阅读",
    }
)
_PREV_NEXT_PREFIX_RE = re.compile(
    r"^(?:上一篇|下一篇|上一条|下一条|相关新闻|相关阅读|推荐阅读)(?:\s|$|[:：])"
)
_BREADCRUMB_PREFIX_RE = re.compile(r"^当前位置\s*[:：]")
_LANGUAGE_SWITCH_RE = re.compile(
    r"^(?:english|中文)\s*[|/·]\s*(?:english|中文)$", re.IGNORECASE
)
_NAV_DISALLOWED_CHARS_RE = re.compile(r"[。！？；：:，,、（）()《》【】0-9]")
_NAV_ITEM_DISALLOWED_RE = re.compile(r"[。！？；，,：:（）()《》【】0-9]")
_FOOTER_LEGAL_RE = re.compile(
    r"(?:copyright|©|版权所有|icp备|公网安备|技术支持)", re.IGNORECASE
)
_FOOTER_ADDRESS_RE = re.compile(r"^地址[:：].*邮编[:：]\s*\d{6}")
_POLICY_OR_ATTACHMENT_RE = re.compile(
    r"(?:附件|截止|推免|免试|复试|报名|申请材料|证明材料|电子材料|纸质材料|提交材料|材料清单|报送材料|复试材料|公示|成绩|排名|资格|竞赛|赛道|申报|提交|申请表|承诺书|体检)"
)
_SUBMISSION_OR_POLICY_RE = re.compile(
    r"(?:提交|申请材料|证明材料|电子材料|纸质材料|提交材料|材料清单|报送材料|复试材料|报送|纸质|申请|截止|附件|邮寄|办公室|推免|复试|报名)"
)
_NUMBERED_CLAUSE_RE = re.compile(
    r"^(?:[（(]?\d+[）)、.．]|[一二三四五六七八九十]+[、.．])"
)
_DATE_HEADLINE_RE = re.compile(
    r"^(?:\d{4}[-/.年]\d{1,2}[-/.月]\d{1,2}日?|\[\d{2,4}[-/.]\d{1,2}(?:[-/.]\d{1,2})?\]|\d{1,2}[-/.]\d{1,2})\s+\S{4,}"
)
_OFFTOPIC_EVENT_HEADLINE_RE = re.compile(
    r"^关于.*(?:放假|值班|羽毛球|篮球赛|运动会|文艺汇演|健步走|工会|停水|停电|物业).*(?:通知|公告)$"
)

_DOMAIN_RELEVANCE_TERMS = (
    "推免",
    "免试",
    "保研",
    "夏令营",
    "预推免",
    "复试",
    "招生",
    "遴选",
    "推荐",
    "接收",
    "成绩",
    "绩点",
    "gpa",
    "排名",
    "四级",
    "六级",
    "cet",
    "ielts",
    "toefl",
    "申请",
    "材料",
    "截止",
    "附件",
    "公示",
    "异议",
    "导师",
    "志愿",
    "竞赛",
    "挑战杯",
    "创新大赛",
    "报名",
    "赛道",
    "选拔",
    "获奖",
    "论文",
    "专利",
    "学分",
    "补考",
    "重修",
    "体检",
    "承诺书",
    "公章",
    "署名",
    "资格",
)
_GENERIC_SCOPE_TOKENS = frozenset(
    {"学院", "大学", "通知", "公告", "工作", "方案", "办法"}
)


@dataclass(frozen=True)
class FilteredSourceFragments:
    """Result of deterministic fragment filtering and deduplication."""

    fragments: list[SourceFragmentRecord]
    dropped_noise_count: int = 0
    dropped_duplicate_count: int = 0
    dropped_irrelevant_count: int = 0


def _strip_invisible(text: str) -> str:
    return text.translate(_INVISIBLE_TRANS).strip()


def _normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", _strip_invisible(text))


def _is_footer_sentinel(norm_quote: str) -> bool:
    return norm_quote in _POST_FOOTER_SENTINELS or bool(
        _PREV_NEXT_PREFIX_RE.match(norm_quote)
    )


def _is_portal_chrome(norm_quote: str) -> bool:
    if norm_quote in _EXACT_PORTAL_CHROME:
        return True
    if _LANGUAGE_SWITCH_RE.match(norm_quote):
        return True
    if _BREADCRUMB_PREFIX_RE.match(norm_quote):
        return True
    if len(norm_quote) <= 40 and norm_quote.endswith((">", "»", "›")):
        return True
    if (
        len(norm_quote) <= 60
        and not _NAV_DISALLOWED_CHARS_RE.search(norm_quote)
        and norm_quote.startswith(_NAV_PREFIXES)
    ):
        return True
    if _FOOTER_LEGAL_RE.search(norm_quote):
        return True
    return bool(
        _FOOTER_ADDRESS_RE.match(norm_quote)
        and not _SUBMISSION_OR_POLICY_RE.search(norm_quote)
    )


def _find_leading_chrome_end(fragments: list[SourceFragmentRecord]) -> int:
    first_section_idx = next(
        (
            idx
            for idx, frag in enumerate(fragments)
            if frag.locator_kind == "section" and _normalize_ws(frag.quote)
        ),
        None,
    )
    if first_section_idx is None or first_section_idx < 3:
        return 0

    chrome_hits = 0
    for frag in fragments[:first_section_idx]:
        if frag.locator_kind == "table_row":
            return 0
        norm_quote = _normalize_ws(frag.quote)
        if _is_portal_chrome(norm_quote):
            chrome_hits += 1
            continue
        if not norm_quote:
            continue
        if (
            len(norm_quote) <= 25
            and not _NAV_ITEM_DISALLOWED_RE.search(norm_quote)
            and not _POLICY_OR_ATTACHMENT_RE.search(norm_quote)
        ):
            continue
        return 0
    return first_section_idx if chrome_hits >= 2 else 0


def _extract_relevance_terms(
    goal: str,
    scope_attrs: Mapping[str, Any] | None,
) -> tuple[str, ...]:
    terms: list[str] = list(_DOMAIN_RELEVANCE_TERMS)
    raw_texts: list[str] = []
    if goal:
        raw_texts.append(goal)
    if scope_attrs:
        for val in scope_attrs.values():
            if isinstance(val, str) and val.strip():
                raw_texts.append(val)
    for raw in raw_texts:
        for token in re.split(r"[\s,，、；;：:/()（）《》]+", raw.lower()):
            cleaned = token.strip()
            if len(cleaned) >= 2 and cleaned not in _GENERIC_SCOPE_TOKENS:
                terms.append(cleaned)
    return tuple(dict.fromkeys(terms))


def _is_irrelevant_standalone(
    frag: SourceFragmentRecord,
    norm_quote: str,
    relevance_terms: tuple[str, ...],
) -> bool:
    if frag.locator_kind in ("section", "table_row"):
        return False
    if _NUMBERED_CLAUSE_RE.match(norm_quote):
        return False
    if not (
        _DATE_HEADLINE_RE.match(norm_quote)
        or _OFFTOPIC_EVENT_HEADLINE_RE.match(norm_quote)
    ):
        return False
    lowered = norm_quote.lower()
    return not any(term in lowered for term in relevance_terms)


def deduplicate_sources(sources: list[SourceDocument]) -> list[SourceDocument]:
    """Deduplicate official sources by source_version_id, preserving version context."""
    unique: list[SourceDocument] = []
    seen_versions: set[str] = set()
    for src in sources:
        if src.source_version_id in seen_versions:
            continue
        seen_versions.add(src.source_version_id)
        unique.append(src)
    return unique


def filter_and_deduplicate_fragments(
    doc: SourceDocument,
    *,
    goal: str = "",
    scope_attrs: Mapping[str, Any] | None = None,
    required_locators: set[tuple[str, str]] | None = None,
) -> FilteredSourceFragments:
    """Filter portal boilerplate, deduplicate fragments, and keep verbatim records.

    Retained ``SourceFragmentRecord`` objects preserve their original ``locator_kind``,
    ``locator``, and ``quote`` unchanged so downstream citation validation stays exact.
    """
    if not doc.fragments:
        return FilteredSourceFragments(fragments=[])

    required_keys: set[tuple[str, str]] = {
        (kind, _normalize_ws(loc)) for kind, loc in (required_locators or set())
    }
    seen_fragments: set[tuple[tuple[str, str], str]] = set()
    candidates: list[tuple[SourceFragmentRecord, str, bool]] = []
    fallback_deduped: list[SourceFragmentRecord] = []
    fallback_seen_fragments: set[tuple[tuple[str, str], str]] = set()

    dropped_noise = 0
    dropped_duplicate = 0
    in_post_footer = False
    leading_chrome_end = _find_leading_chrome_end(doc.fragments)

    for idx, frag in enumerate(doc.fragments):
        norm_locator = _normalize_ws(frag.locator)
        norm_quote = _normalize_ws(frag.quote)
        locator_key = (frag.locator_kind, norm_locator)
        is_required = locator_key in required_keys

        fragment_key = (locator_key, norm_quote)
        if norm_quote and fragment_key not in fallback_seen_fragments:
            fallback_seen_fragments.add(fragment_key)
            fallback_deduped.append(frag)

        if not norm_quote and not is_required:
            dropped_noise += 1
            continue

        if not is_required and idx < leading_chrome_end:
            dropped_noise += 1
            continue

        if not is_required and frag.locator_kind not in ("section", "table_row"):
            if _is_footer_sentinel(norm_quote):
                in_post_footer = True
                dropped_noise += 1
                continue
            if in_post_footer and not _POLICY_OR_ATTACHMENT_RE.search(norm_quote):
                dropped_noise += 1
                continue
            if _is_portal_chrome(norm_quote):
                dropped_noise += 1
                continue

        if fragment_key in seen_fragments:
            dropped_duplicate += 1
            continue

        seen_fragments.add(fragment_key)
        candidates.append((frag, norm_quote, is_required))

    dropped_irrelevant = 0
    if len(candidates) >= 5:
        relevance_terms = _extract_relevance_terms(goal, scope_attrs)
        retained: list[SourceFragmentRecord] = []
        for frag, norm_quote, is_required in candidates:
            if not is_required and _is_irrelevant_standalone(
                frag, norm_quote, relevance_terms
            ):
                dropped_irrelevant += 1
                continue
            retained.append(frag)
    else:
        retained = [frag for frag, _, _ in candidates]

    if not retained and fallback_deduped:
        return FilteredSourceFragments(
            fragments=fallback_deduped,
            dropped_noise_count=0,
            dropped_duplicate_count=len(doc.fragments) - len(fallback_deduped),
            dropped_irrelevant_count=0,
        )

    return FilteredSourceFragments(
        fragments=retained,
        dropped_noise_count=dropped_noise,
        dropped_duplicate_count=dropped_duplicate,
        dropped_irrelevant_count=dropped_irrelevant,
    )
