import os

from openai import OpenAI

prompt = "从推免通知中提取需要提交的材料，并引用原文。"
notice = "申请人须提交本科成绩单。"

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
    )
    print(response.choices[0].message.content)