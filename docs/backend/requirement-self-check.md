# 要求自查结果保存协议

关联 #32、#41。前端按条件逐条展示四态结论、判断原因、缺失信息、缺口和来源引用，需要从保存后的要求记录还原这些内容。

## 字段含义

| 字段 | 位置 | 含义 |
| --- | --- | --- |
| `extract_status` | 要求记录 | 提取记录的核验进度：`extracted` 未自查、`checked` 已自查且无未决疑点、`to_review` 条款存在歧义或自查结论为待用户核对、`rejected` 已被拒绝 |
| `self_check.conclusion` | 要求记录 | 四态自查结论：`matched` 按现有信息符合、`not_matched` 按现有信息不符合、`missing_info` 待补充信息、`needs_user_review` 待用户核对 |
| `self_check.reason` | 要求记录 | 判断原因 |
| `self_check.missing_fields` | 要求记录 | 待用户补充的个人事实键；`missing_info` 时列出缺失项 |
| `self_check.computed_deadline_at` | 要求记录 | 规则计算出的截止时间，带时区的 ISO 8601，无则为 `null` |
| `self_check.gaps` | 要求记录 | 与该要求相关的缺口，包含关联该要求的缺口，以及该要求所引用来源的来源级缺口（转载、过期、未读取范围、缺失附件） |
| 来源引用 | `evidence` | 沿用 `ops.evidence`，`target_type = requirement` |

`extract_status` 不承载四态结论：`matched` 与 `not_matched` 的 `extract_status` 都是 `checked`，两者只靠 `self_check.conclusion` 区分，`missing_info` 同样如此。读取方必须以 `self_check.conclusion` 展示结论。

缺口 `gap_type` 取值：`missing_attachment`、`missing_basis`、`missing_personal_fact`、`repost_only`、`expired_source`、`scope_unclear`、`ambiguous_clause`、`read_failed`。`missing_personal_fact` 表示需要用户补充个人事实，`missing_basis` 表示来源依据缺失。

## 存储

`core.requirement_self_check`（迁移 `0009`）按 `requirement_id` 一对一关联 `core.requirement`，删除要求时级联删除，并按事项所属工作区启用行级安全。

## 请求示例

`POST /api/v1/matters/{matter_id}/requirements`

```json
{
  "requirements": [
    {
      "field_key": "english_level",
      "label": "英语水平",
      "obligation_nature": "to_verify",
      "extract_status": "checked",
      "scope": "福州大学数学与统计学院",
      "value_text": null,
      "value_type": "text",
      "confidence": 0.9,
      "snapshot_id": "b0000000-0000-4000-8000-000000000102",
      "evidence": [
        {
          "source_id": "b0000000-0000-4000-8000-000000000101",
          "snapshot_id": "b0000000-0000-4000-8000-000000000102",
          "locator_kind": "section",
          "locator": "二第5项",
          "quote": "英语要求：原则上四级>=500或六级>=425"
        }
      ],
      "self_check": {
        "conclusion": "missing_info",
        "reason": "尚无达标项，待补充其他可替代项：cet6, toefl, ielts（规则限定：原则上）",
        "missing_fields": ["cet6", "toefl", "ielts"],
        "computed_deadline_at": null,
        "gaps": [
          {
            "gap_type": "missing_personal_fact",
            "description": "英语水平：尚无达标项，待补充其他可替代项：cet6, toefl, ielts（规则限定：原则上）",
            "locator": "二第5项",
            "source_id": "b0000000-0000-4000-8000-000000000101",
            "snapshot_id": "b0000000-0000-4000-8000-000000000102"
          }
        ]
      }
    }
  ]
}
```

没有执行自查的要求，`self_check` 为 `null`，`extract_status` 为 `extracted`。

## 响应示例

要求读取接口在每条要求中返回同样结构的 `self_check`，并附带 `id` 与 `evidence`。事项来源链接口 `GET /api/v1/matters/{matter_id}/sources` 的每条要求都包含该字段；没有自查结果时为 `null`。

```json
{
  "id": "c0000000-0000-4000-8000-000000000201",
  "matter_id": "a0000000-0000-4000-8000-000000000001",
  "field_key": "english_level",
  "label": "英语水平",
  "obligation_nature": "to_verify",
  "extract_status": "checked",
  "snapshot_id": "b0000000-0000-4000-8000-000000000102",
  "evidence": [
    {
      "source_id": "b0000000-0000-4000-8000-000000000101",
      "snapshot_id": "b0000000-0000-4000-8000-000000000102",
      "locator_kind": "section",
      "locator": "二第5项",
      "quote": "英语要求：原则上四级>=500或六级>=425"
    }
  ],
  "self_check": {
    "conclusion": "missing_info",
    "reason": "尚无达标项，待补充其他可替代项：cet6, toefl, ielts（规则限定：原则上）",
    "missing_fields": ["cet6", "toefl", "ielts"],
    "computed_deadline_at": null,
    "gaps": []
  }
}
```

## Agent 侧

`backend.agent.contracts.build_requirements_batch_payload(requirements, evaluations, sources_by_id, gaps)` 生成上述请求体；`AgentOrchestrator` 把本次运行的合并缺口一并传入。
