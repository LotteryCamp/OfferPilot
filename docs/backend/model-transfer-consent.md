# 模型传输同意接口

| 项目 | 内容 |
| :--- | :--- |
| 接口前缀 | `/api/v1` |
| 数据格式 | JSON，UTF-8 |
| 适用范围 | Alpha 单用户本地演示 |
| 业务契约 | [`api.md`](api.md) |
| 数据库结构 | 迁移 `0013_model_transfer_consent.sql` |

## 1. 范围与约束

模型传输同意归属于当前用户与当前事项，绑定服务商、用途、字段类别与授权版本。同一事项同时只有一条 `active` 记录；撤回后保留历史版本，重新授予产生新的 `version_no`。

事项的 `scope_attrs` 非空，或运行请求携带 `confirmed_facts` 时，创建 Agent 运行必须提供当前事项的有效同意标识。读取接口的 `required` 表示事项默认分析入口是否需要同意；运行级事实在请求中提供时，即使 `required` 为 `false`，该次运行仍需同意。

当前 Alpha 的服务商由服务端配置决定，前端不提交服务商、用途或字段类别。配置项：

| 配置 | 用途 | 默认值 |
| :--- | :--- | :--- |
| `OFFERPILOT_MODEL_PROVIDER` | 服务商名称，写入同意记录并参与出站校验 | `OpenAI 兼容模型服务` |
| `OFFERPILOT_MODEL_NAME` | 展示给用户的模型名称 | 空 |

同意覆盖两个用途与三类字段：

| 类别 | 值 |
| :--- | :--- |
| 用途 | `requirement_extraction`、`candidate_planning` |
| 字段类别 | `matter_goal`、`public_scope`、`public_sources` |

## 2. 路径与资源

事项标识通过路径参数 `{matter_id}` 传递。服务端在每次读取、授予或撤回前校验事项属于当前工作区，校验失败返回 `404 matter_not_found`。

| 方法 | 路径 | 用途 |
| :--- | :--- | :--- |
| `GET` | `/api/v1/matters/{matter_id}/model-transfer-consents` | 读取当前事项的授权状态与披露信息 |
| `POST` | `/api/v1/matters/{matter_id}/model-transfer-consents` | 授予同意；已有 `active` 记录时返回该记录 |
| `DELETE` | `/api/v1/matters/{matter_id}/model-transfer-consents/{consent_id}` | 撤回指定同意 |

## 3. 读取授权状态

`GET /api/v1/matters/{matter_id}/model-transfer-consents`

响应 `200`：

```json
{
  "required": true,
  "disclosure": {
    "provider": "OpenAI 兼容模型服务",
    "model": "gpt-4.1-mini",
    "purposes": [
      "requirement_extraction",
      "candidate_planning"
    ],
    "field_categories": [
      "matter_goal",
      "public_scope",
      "public_sources"
    ],
    "data_handling": "仅发送本次运行的事项目标、白名单公开范围字段与公开来源正文；不发送个人事实、个人材料或用户导入件。模型服务按其自身数据处理条款处理请求。"
  },
  "consent": {
    "consent_id": "e0000000-0000-4000-8000-000000000001",
    "matter_id": "a0000000-0000-4000-8000-000000000001",
    "provider": "OpenAI 兼容模型服务",
    "purposes": [
      "requirement_extraction",
      "candidate_planning"
    ],
    "field_categories": [
      "matter_goal",
      "public_scope",
      "public_sources"
    ],
    "status": "active",
    "version_no": 1,
    "created_at": "2026-09-09T01:00:00+00:00",
    "revoked_at": null
  }
}
```

无有效同意时 `consent` 为 `null`。`disclosure` 用于授权前展示，字段与授予后的同意记录一致。

## 4. 授予同意

`POST /api/v1/matters/{matter_id}/model-transfer-consents`

请求体为空。服务端按当前配置写入服务商、用途与字段类别。已有 `active` 记录时直接返回该记录，`created` 为 `false`。

响应 `200`：

```json
{
  "consent": {
    "consent_id": "e0000000-0000-4000-8000-000000000001",
    "matter_id": "a0000000-0000-4000-8000-000000000001",
    "provider": "OpenAI 兼容模型服务",
    "purposes": [
      "requirement_extraction",
      "candidate_planning"
    ],
    "field_categories": [
      "matter_goal",
      "public_scope",
      "public_sources"
    ],
    "status": "active",
    "version_no": 1,
    "created_at": "2026-09-09T01:00:00+00:00",
    "revoked_at": null
  },
  "created": true
}
```

## 5. 撤回同意

`DELETE /api/v1/matters/{matter_id}/model-transfer-consents/{consent_id}`

响应 `200`：

```json
{
  "consent": {
    "consent_id": "e0000000-0000-4000-8000-000000000001",
    "matter_id": "a0000000-0000-4000-8000-000000000001",
    "provider": "OpenAI 兼容模型服务",
    "purposes": [
      "requirement_extraction",
      "candidate_planning"
    ],
    "field_categories": [
      "matter_goal",
      "public_scope",
      "public_sources"
    ],
    "status": "revoked",
    "version_no": 1,
    "created_at": "2026-09-09T01:00:00+00:00",
    "revoked_at": "2026-09-09T02:00:00+00:00"
  },
  "revoked": true
}
```

重复撤回同一条记录返回 `200`，`revoked` 为 `false`。记录不存在或不属于当前事项时返回 `404 transfer_consent_not_found`。

## 6. Agent 运行接入

前端进入事项分析入口时按以下顺序处理：

1. 调用读取接口。
2. `consent` 为 `null` 且 `required` 为 `true` 时展示 `disclosure`，用户确认后调用授予接口并取得 `consent_id`。
3. 创建 Agent 运行时把 `consent_id` 写入 `model_transfer_consent_id`。
4. 用户撤回后重新读取授权状态；旧标识不再通过校验。

运行入口错误：

| HTTP 状态 | `code` | 含义 |
| :--- | :--- | :--- |
| 422 | `model_transfer_consent_required` | 需要同意但未提供标识，未创建运行 |
| 422 | `model_transfer_consent_invalid` | 标识不存在、已撤回、服务商不匹配、用途或字段类别未覆盖，未创建运行；`details.purposes` 列出未覆盖的用途 |

## 7. 出站校验

每个模型工具调用经 `ToolGateway` 进入统一出口，按工具核对用途与字段类别：

| 工具 | 用途 | 必需字段类别 |
| :--- | :--- | :--- |
| `extract_requirements` | `requirement_extraction` | `matter_goal`、`public_sources` |
| `generate_candidate_plan` | `candidate_planning` | `matter_goal`、`public_scope`、`public_sources` |
| `persist_candidate_artifacts` | `candidate_planning` | `matter_goal`、`public_scope`、`public_sources` |

`persist_candidate_artifacts` 不发起外部请求。该步骤在写入候选前复核同意，撤回后的模型结果不写入候选稿。

服务端校验项：

- 同意标识为 UUID，记录属于当前用户与当前事项。
- 记录状态为 `active`，服务商等于当前配置。
- `purposes` 覆盖本次工具用途，`field_categories` 覆盖本次发送类别。
- 运行入口在创建运行前检查全部用途；网关在每次工具调用前再次检查。

出站内容边界：

| 字段类别 | 实际内容 |
| :--- | :--- |
| `matter_goal` | 当前运行的目标描述，去除首尾空白并限制在 200 字符内 |
| `public_scope` | `scope_year` 与白名单公开范围字段：`school`、`college`、`department`、`program`、`major`、`track`、`category`、`degree`、`intake_year`、`region` |
| `public_sources` | 公开来源标题、发布方、年度、范围、正文与引用定位 |

个人事实、个人材料、用户导入件与未列入白名单的 `scope_attrs` 字段不进入模型请求。

## 8. 演示限制

- 不提供有效期、按用途分别授予、第三方服务商条款绑定或授权历史列表。
- 授权范围固定为当前事项的公开资料分析。
- 撤回只影响后续校验；已发出的外部请求由模型服务按其数据处理条款处理。
