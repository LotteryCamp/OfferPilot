# 模型传输同意接口

| 项目 | 内容 |
| :--- | :--- |
| 接口前缀 | `/api/v1` |
| 数据格式 | JSON，UTF-8 |
| 适用范围 | 多用户后端 |
| 业务契约 | [`api.md`](api.md) |
| 数据库结构 | 迁移 `0015_global_model_transfer_consent.sql` |

## 1. 范围与约束

模型传输同意归属于当前用户，覆盖该用户的全部事项。同意记录绑定用途、字段类别与授权版本；同一用户同时只有一条 `active` 记录，撤回后保留历史版本，重新授予产生新的 `version_no`。

授权对象为向外部模型传输公开资料的处理行为。同意记录不绑定服务商与模型，更换模型服务后既有同意继续有效。

事项的 `scope_attrs` 非空、运行请求携带 `confirmed_facts`，或事项事实档案存在已确认事实时，创建 Agent 运行必须具备有效的全局同意。

当前服务商与模型名称由服务端配置决定，仅用于授予前披露，前端不提交服务商、用途或字段类别。配置项：

| 配置 | 用途 | 默认值 |
| :--- | :--- | :--- |
| `OFFERPILOT_MODEL_PROVIDER` | 披露给用户的服务商名称 | `OpenAI 兼容模型服务` |
| `OFFERPILOT_MODEL_NAME` | 披露给用户的模型名称 | 空 |

同意覆盖两个用途与三类字段：

| 类别 | 值 |
| :--- | :--- |
| 用途 | `requirement_extraction`、`candidate_planning` |
| 字段类别 | `matter_goal`、`public_scope`、`public_sources` |

## 2. 路径与资源

| 方法 | 路径 | 用途 |
| :--- | :--- | :--- |
| `GET` | `/api/v1/model-transfer-consent` | 读取当前用户的授权状态与披露信息 |
| `POST` | `/api/v1/model-transfer-consent` | 授予同意；已有 `active` 记录时返回该记录 |
| `DELETE` | `/api/v1/model-transfer-consent/{consent_id}` | 撤回指定同意 |

## 3. 读取授权状态

`GET /api/v1/model-transfer-consent`

响应 `200`：

```json
{
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
    "consent_scope": "同意归属当前用户并覆盖全部事项；授权对象为向外部模型传输公开资料的处理行为，覆盖当前配置及后续更换的外部模型服务。",
    "data_handling": "仅发送本次运行的事项目标、白名单公开范围字段与公开来源正文；不发送个人事实、个人材料或用户导入件。模型服务按其自身数据处理条款处理请求。"
  },
  "consent": {
    "consent_id": "e0000000-0000-4000-8000-000000000001",
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

无有效同意时 `consent` 为 `null`。`disclosure` 用于授权前展示，服务商与模型名称反映读取时的服务端配置。

## 4. 授予同意

`POST /api/v1/model-transfer-consent`

请求体为空。服务端按当前配置写入用途与字段类别。已有 `active` 记录时直接返回该记录，`created` 为 `false`。

响应 `200`：

```json
{
  "consent": {
    "consent_id": "e0000000-0000-4000-8000-000000000001",
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

`DELETE /api/v1/model-transfer-consent/{consent_id}`

响应 `200`：

```json
{
  "consent": {
    "consent_id": "e0000000-0000-4000-8000-000000000001",
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

重复撤回同一条记录返回 `200`，`revoked` 为 `false`。记录不存在或不属于当前用户时返回 `404 transfer_consent_not_found`。

## 6. Agent 运行接入

前端在个人信息授权同意选项中完成一次授予，授予后全部事项的分析运行直接可用。创建 Agent 运行的请求体不携带同意标识，服务端按当前用户自动核对全局同意。

运行入口错误：

| HTTP 状态 | `code` | 含义 |
| :--- | :--- | :--- |
| 422 | `model_transfer_consent_required` | 需要同意但当前用户没有有效全局同意，未创建运行 |

用户撤回后，后续运行返回 `422 model_transfer_consent_required`；重新授予产生新的 `version_no`，运行随即恢复。

## 7. 出站校验

每个模型工具调用经 `ToolGateway` 进入统一出口，按工具核对用途与字段类别：

| 工具 | 用途 | 必需字段类别 |
| :--- | :--- | :--- |
| `extract_requirements` | `requirement_extraction` | `matter_goal`、`public_sources` |
| `generate_candidate_plan` | `candidate_planning` | `matter_goal`、`public_scope`、`public_sources` |
| `persist_candidate_artifacts` | `candidate_planning` | `matter_goal`、`public_scope`、`public_sources` |

`persist_candidate_artifacts` 不发起外部请求。该步骤在写入候选前复核同意，撤回后的模型结果不写入候选稿。

服务端校验项：

- 同意记录属于当前用户与当前工作区。
- 记录状态为 `active`。
- `purposes` 覆盖本次工具用途，`field_categories` 覆盖本次发送类别。
- 运行入口在创建运行前核对全部用途；网关在每次工具调用前再次核对。

出站内容边界：

| 字段类别 | 实际内容 |
| :--- | :--- |
| `matter_goal` | 当前运行的目标描述，去除首尾空白并限制在 200 字符内 |
| `public_scope` | `scope_year` 与白名单公开范围字段：`school`、`college`、`department`、`program`、`major`、`track`、`category`、`degree`、`intake_year`、`region` |
| `public_sources` | 公开来源标题、发布方、年度、范围、正文与引用定位 |

个人事实、个人材料、用户导入件与未列入白名单的 `scope_attrs` 字段不进入模型请求。

## 8. 演示限制

- 不提供有效期、按用途分别授予、第三方服务商条款绑定或授权历史列表。
- 授权范围固定为公开资料分析，覆盖用户的全部事项。
- 撤回只影响后续校验；已发出的外部请求由模型服务按其数据处理条款处理。
