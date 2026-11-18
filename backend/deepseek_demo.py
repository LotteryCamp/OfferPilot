from pydantic import BaseModel, ConfigDict

from backend.model_adapter import ModelAdapterError, call_model


class Requirement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str
    quote: str
    official_deadline: str | None


class ExtractionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirements: list[Requirement]
    gaps: list[str]


notice = "申请人须提交本科成绩单。"
instruction = """
从通知中提取申请人需要提交的材料。只依据原文。
quote 必须逐字引用原文。没有截止时间时填 null，并在 gaps 中说明。
JSON 示例：
{"requirements":[{"description":"提交申请表","quote":"须提交申请表",
"official_deadline":null}],"gaps":["原文未说明截止时间"]}
"""

try:
    result = call_model(instruction, notice, ExtractionResult)
except ModelAdapterError as exc:
    raise SystemExit(f"{exc.code}: {exc}") from None

print(result.model_dump_json(indent=2))