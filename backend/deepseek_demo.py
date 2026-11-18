import json
import os

from openai import OpenAI

notice = "申请人须提交本科成绩单。"

prompt = """
从公开推免通知中提取申请材料，只依据提供的原文。
每条要求返回 description（材料要求）、quote（逐字引用）、
official_deadline（官方截止时间）。
如果原文没写截止时间，填 null，并在 gaps 中说明。

只返回 JSON。格式示例：
{
  "requirements": [
    {
      "description": "提交申请表",
      "quote": "须提交申请表",
      "official_deadline": null
    }
  ],
  "gaps": ["原文未说明截止时间"]
}
"""

with OpenAI(
    api_key=os.environ["OFFERPILOT_MODEL_API_KEY"],
    base_url=os.environ["OFFERPILOT_MODEL_API_URL"],
    timeout=30,
    max_retries=0,
) as client:
    response = client.chat.completions.create(
        model=os.environ["OFFERPILOT_MODEL_NAME"],
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": notice},
        ],
        response_format={"type": "json_object"},
    )

choice = response.choices[0]
content = choice.message.content
if choice.finish_reason != "stop" or not content or not content.strip():
    raise RuntimeError(f"模型未返回完整内容：{choice.finish_reason}")

result = json.loads(content)
print(json.dumps(result, ensure_ascii=False, indent=2))