"""Small registry for persisted personal fact types."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

FOUR_PLACES = Decimal("0.0001")
TWO_PLACES = Decimal("0.01")
ONE_PLACE = Decimal("0.1")
GPA_SCALE = Decimal("4.0")


class FactValueError(ValueError):
    """Raised when a fact value does not match its registered shape."""

    def __init__(self, issues: list[dict[str, str]]) -> None:
        super().__init__("事实值不合法")
        self.issues = issues


@dataclass(frozen=True)
class FactRender:
    value_text: str
    agent_value: object | None


@dataclass(frozen=True)
class FactTypeSpec:
    fact_type: str
    normalize: Callable[[Mapping[str, Any]], dict[str, Any]]
    render: Callable[[Mapping[str, Any]], FactRender]


def _issue(path: str, code: str, message: str) -> dict[str, str]:
    return {"path": path, "code": code, "message": message}


def _as_number(value: Any) -> Decimal | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return parsed if parsed.is_finite() else None


def _as_positive_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if value > 0 else None


def _quantize_percentile(value: Decimal) -> Decimal:
    return value.quantize(FOUR_PLACES, rounding=ROUND_HALF_UP)


def _format_percentile(value: Any) -> str:
    parsed = Decimal(str(value)).quantize(FOUR_PLACES, rounding=ROUND_HALF_UP)
    return format(parsed, "f").rstrip("0").rstrip(".")


def _as_integer(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _format_decimal(
    value: Any,
    places: Decimal,
    *,
    at_least_one_decimal: bool = False,
) -> str:
    parsed = Decimal(str(value)).quantize(places, rounding=ROUND_HALF_UP)
    text = format(parsed, "f").rstrip("0").rstrip(".")
    if at_least_one_decimal and "." not in text:
        text += ".0"
    return text


def _normalize_gpa_rank(value: Mapping[str, Any]) -> dict[str, Any]:
    keys = set(value)
    rank_keys = {"position", "cohort_size"}
    percentile_keys = {"percentile"}
    issues: list[dict[str, str]] = []

    if keys == rank_keys:
        position = _as_positive_int(value["position"])
        cohort_size = _as_positive_int(value["cohort_size"])
        if position is None:
            issues.append(
                _issue(
                    "value.position",
                    "positive_integer_required",
                    "名次必须是正整数",
                )
            )
        if cohort_size is None:
            issues.append(
                _issue(
                    "value.cohort_size",
                    "positive_integer_required",
                    "总人数必须是正整数",
                )
            )
        if issues:
            raise FactValueError(issues)
        assert position is not None and cohort_size is not None
        if position > cohort_size:
            raise FactValueError(
                [
                    _issue(
                        "value.position",
                        "greater_than_cohort",
                        "名次不得大于总人数",
                    )
                ]
            )
        percentile = _quantize_percentile(
            Decimal(position) / Decimal(cohort_size) * Decimal(100)
        )
        return {
            "position": position,
            "cohort_size": cohort_size,
            "percentile": float(percentile),
        }

    if keys == percentile_keys:
        percentile = _as_number(value["percentile"])
        if percentile is None or percentile <= 0 or percentile > 100:
            raise FactValueError(
                [
                    _issue(
                        "value.percentile",
                        "percentile_out_of_range",
                        "百分位必须大于 0 且不大于 100",
                    )
                ]
            )
        normalized = _quantize_percentile(percentile)
        return {
            "position": None,
            "cohort_size": None,
            "percentile": float(normalized),
        }

    if rank_keys & keys and percentile_keys & keys:
        issues.append(
            _issue(
                "value",
                "mutually_exclusive",
                "名次写法与百分位写法只能选择一种",
            )
        )
    else:
        missing_rank = sorted(rank_keys - keys)
        for key in missing_rank:
            issues.append(
                _issue(
                    f"value.{key}",
                    "required",
                    "名次写法需要同时提供 position 与 cohort_size",
                )
            )
        unknown = sorted(keys - rank_keys - percentile_keys)
        for key in unknown:
            issues.append(
                _issue(
                    f"value.{key}",
                    "unexpected_key",
                    "该字段不属于 gpa.rank 的值",
                )
            )
        if not issues:
            issues.append(
                _issue(
                    "value",
                    "required",
                    "需要提供 position/cohort_size 或 percentile",
                )
            )
    raise FactValueError(issues)


def _render_gpa_rank(value: Mapping[str, Any]) -> FactRender:
    position = value.get("position")
    cohort_size = value.get("cohort_size")
    percentile = value.get("percentile")
    if position is not None and cohort_size is not None:
        return FactRender(
            value_text=f"{position}/{cohort_size}",
            agent_value=percentile,
        )
    return FactRender(
        value_text=f"前 {_format_percentile(percentile)}%",
        agent_value=percentile,
    )


def _normalize_gpa_score(value: Mapping[str, Any]) -> dict[str, Any]:
    keys = set(value)
    issues: list[dict[str, str]] = []
    if "value" not in keys:
        issues.append(_issue("value.value", "required", "GPA 需要提供 value"))
    for key in sorted(keys - {"value"}):
        issues.append(
            _issue(
                f"value.{key}",
                "unexpected_key",
                "该字段不属于 gpa.score 的值",
            )
        )
    if issues:
        raise FactValueError(issues)

    parsed = _as_number(value["value"])
    if parsed is None or parsed < 0 or parsed > GPA_SCALE:
        raise FactValueError(
            [
                _issue(
                    "value.value",
                    "gpa_out_of_range",
                    "GPA 必须是 0 到 4.0 之间的数值",
                )
            ]
        )
    normalized = parsed.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
    if normalized > GPA_SCALE:
        raise FactValueError(
            [
                _issue(
                    "value.value",
                    "gpa_out_of_range",
                    "GPA 必须是 0 到 4.0 之间的数值",
                )
            ]
        )
    return {"value": float(normalized), "scale": float(GPA_SCALE)}


def _render_gpa_score(value: Mapping[str, Any]) -> FactRender:
    return FactRender(
        value_text=f"{_format_decimal(value['value'], TWO_PLACES, at_least_one_decimal=True)}/4.0",
        agent_value=value["value"],
    )


def _make_score_type(
    fact_type: str,
    label: str,
    maximum: int,
) -> FactTypeSpec:
    def normalize(value: Mapping[str, Any]) -> dict[str, Any]:
        keys = set(value)
        issues: list[dict[str, str]] = []
        if "score" not in keys:
            issues.append(_issue("value.score", "required", f"{label} 需要提供 score"))
        for key in sorted(keys - {"score"}):
            issues.append(
                _issue(
                    f"value.{key}",
                    "unexpected_key",
                    f"该字段不属于 {fact_type} 的值",
                )
            )
        if issues:
            raise FactValueError(issues)
        score = _as_integer(value["score"])
        if score is None or score < 0 or score > maximum:
            raise FactValueError(
                [
                    _issue(
                        "value.score",
                        "score_out_of_range",
                        f"{label} 分数必须是 0 到 {maximum} 之间的整数",
                    )
                ]
            )
        return {"score": score}

    def render(value: Mapping[str, Any]) -> FactRender:
        return FactRender(
            value_text=f"{label} {value['score']}",
            agent_value=value["score"],
        )

    return FactTypeSpec(fact_type=fact_type, normalize=normalize, render=render)


def _normalize_ielts(value: Mapping[str, Any]) -> dict[str, Any]:
    keys = set(value)
    issues: list[dict[str, str]] = []
    if "overall" not in keys:
        issues.append(_issue("value.overall", "required", "IELTS 需要提供 overall"))
    for key in sorted(keys - {"overall"}):
        issues.append(
            _issue(
                f"value.{key}",
                "unexpected_key",
                "该字段不属于 ielts 的值",
            )
        )
    if issues:
        raise FactValueError(issues)

    parsed = _as_number(value["overall"])
    if parsed is None or parsed < 0 or parsed > 9:
        raise FactValueError(
            [
                _issue(
                    "value.overall",
                    "score_out_of_range",
                    "IELTS 总分必须是 0 到 9 之间的数值",
                )
            ]
        )
    normalized = parsed.quantize(ONE_PLACE, rounding=ROUND_HALF_UP)
    if normalized > 9:
        raise FactValueError(
            [
                _issue(
                    "value.overall",
                    "score_out_of_range",
                    "IELTS 总分必须是 0 到 9 之间的数值",
                )
            ]
        )
    return {"overall": float(normalized)}


def _render_ielts(value: Mapping[str, Any]) -> FactRender:
    return FactRender(
        value_text=(
            f"IELTS {_format_decimal(value['overall'], ONE_PLACE, at_least_one_decimal=True)}"
        ),
        agent_value=value["overall"],
    )


def _make_level_type(fact_type: str, label: str) -> FactTypeSpec:
    def normalize(value: Mapping[str, Any]) -> dict[str, Any]:
        keys = set(value)
        issues: list[dict[str, str]] = []
        if "level" not in keys:
            issues.append(_issue("value.level", "required", f"{label}需要提供 level"))
        for key in sorted(keys - {"level"}):
            issues.append(
                _issue(
                    f"value.{key}",
                    "unexpected_key",
                    f"该字段不属于 {fact_type} 的值",
                )
            )
        if issues:
            raise FactValueError(issues)
        raw = value["level"]
        level = raw.strip() if isinstance(raw, str) else ""
        if not level or len(level) > 32:
            raise FactValueError(
                [
                    _issue(
                        "value.level",
                        "invalid_level",
                        f"{label}等级必须是非空字符串，最长 32 字符",
                    )
                ]
            )
        return {"level": level}

    def render(value: Mapping[str, Any]) -> FactRender:
        return FactRender(
            value_text=f"{label} {value['level']}",
            agent_value=value["level"],
        )

    return FactTypeSpec(fact_type=fact_type, normalize=normalize, render=render)


GPA_RANK = FactTypeSpec(
    fact_type="gpa.rank",
    normalize=_normalize_gpa_rank,
    render=_render_gpa_rank,
)

GPA_SCORE = FactTypeSpec(
    fact_type="gpa.score",
    normalize=_normalize_gpa_score,
    render=_render_gpa_score,
)

CET4 = _make_score_type("cet4", "CET-4", 710)
CET6 = _make_score_type("cet6", "CET-6", 710)
TOEFL = _make_score_type("toefl", "TOEFL", 120)

IELTS = FactTypeSpec(
    fact_type="ielts",
    normalize=_normalize_ielts,
    render=_render_ielts,
)

CERT = _make_level_type("cert", "证书")
COMP = _make_level_type("comp", "竞赛")

FACT_TYPES: dict[str, FactTypeSpec] = {
    spec.fact_type: spec
    for spec in (GPA_RANK, GPA_SCORE, CET4, CET6, TOEFL, IELTS, CERT, COMP)
}


def get_fact_type(fact_type: str) -> FactTypeSpec | None:
    return FACT_TYPES.get(fact_type)


def supported_fact_types() -> list[str]:
    return sorted(FACT_TYPES)
