"""External model transfer scope shared by the consent API and outbound gateway."""

from __future__ import annotations

TRANSFER_PURPOSES = ("requirement_extraction", "candidate_planning")
TRANSFER_FIELD_CATEGORIES = ("matter_goal", "public_scope", "public_sources")

TRANSFER_TOOL_SCOPE: dict[str, tuple[str, tuple[str, ...]]] = {
    "extract_requirements": (
        "requirement_extraction",
        ("matter_goal", "public_sources"),
    ),
    "generate_candidate_plan": ("candidate_planning", TRANSFER_FIELD_CATEGORIES),
    "persist_candidate_artifacts": ("candidate_planning", TRANSFER_FIELD_CATEGORIES),
}

REQUIRED_TRANSFER_SCOPES = tuple(dict.fromkeys(TRANSFER_TOOL_SCOPE.values()))

TRANSFER_DATA_HANDLING = (
    "仅发送本次运行的事项目标、白名单公开范围字段与公开来源正文；"
    "不发送个人事实、个人材料或用户导入件。模型服务按其自身数据处理条款处理请求。"
)

TRANSFER_CONSENT_SCOPE = (
    "同意归属当前用户并覆盖全部事项；授权对象为向外部模型传输公开资料的处理行为，"
    "覆盖当前配置及后续更换的外部模型服务。"
)
