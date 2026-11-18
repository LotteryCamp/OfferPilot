# Alpha 核心业务流程 API

| 项目 | 内容 |
| :--- | :--- |
| 接口前缀 | `/api/v1` |
| 数据格式 | JSON，UTF-8 |
| 适用范围 | Alpha 单用户本地演示 |
| 业务契约 | [`docs/development/alpha-scope-contract.md`](../development/alpha-scope-contract.md) |
| 数据库结构 | Alpha schema 迁移 `0001`—`0008` |

## 1. 范围

本接口覆盖 Alpha 核心演示的后端业务：

- 创建个人事项，读取事项列表与事项详情。
- 登记公开来源与快照，按事项读取来源链。
- 持久化候选要求、候选计划、计划项及计划项出处。
- 读取候选计划，由用户确认或拒绝。
- 确认后生成个人任务，读取任务及其来源定位。

本模块不执行网络抓取。调用方提供来源 URL、正文、发布信息和原文片段，接口负责登记来源与快照。候选要求与候选计划由 Agent 生成后通过本接口持久化，接口本身不调用模型。

## 2. 通用约定

### 2.1 请求与响应

- 请求体和响应体均为 JSON 对象。
- 标识使用 UUID 字符串。请求中的路径参数与 JSON 字段均为标准 UUID 格式。
- `date` 字段使用 `YYYY-MM-DD`。
- `timestamptz` 字段使用 ISO 8601 带时区时间，响应统一换算为 UTC，例如 `2026-09-09T01:00:00+00:00`。
- 请求字段执行严格校验，未声明的字段会被拒绝。
- 字符串字段在写入前去除首尾空白。

### 2.2 身份与数据边界

Alpha 当前没有登录能力，接口使用固定演示身份：

| 配置 | 环境变量 | 默认值 |
| :--- | :--- | :--- |
| 演示用户 | `OFFERPILOT_DEMO_USER_ID` | `00000000-0000-7000-8000-000000000001` |
| 演示工作区 | `OFFERPILOT_DEMO_WORKSPACE_ID` | `00000000-0000-7000-8000-000000000002` |

每次数据库事务都会设置 `app.current_workspace_id`，行级安全策略按该工作区过滤事项、要求、候选计划、计划项、计划项来源、计划和任务。事项、候选计划与任务的读取同时校验事项归属。

固定身份仅用于本地演示。它不等同于多用户认证，也不构成跨账户安全边界。演示用户或工作区不存在时，接口返回 `500 demo_identity_missing`。

### 2.3 错误结构

所有业务错误使用统一结构：

```json
{
  "error": {
    "code": "plan_already_decided",
    "message": "候选计划已有终态决定",
    "next": "重新读取候选计划状态",
    "details": {
      "status": "confirmed",
      "decision": "confirmed"
    }
  }
}
```

| 字段 | 说明 |
| :--- | :--- |
| `code` | 稳定错误码，调用方按该字段分支处理 |
| `message` | 可直接展示的中文说明 |
| `next` | 建议的下一步操作，可能省略 |
| `details` | 结构化补充信息，可能省略 |

请求字段校验失败时返回 `422 validation_error`，`details.issues` 列出字段路径、校验类型和说明：

```json
{
  "error": {
    "code": "validation_error",
    "message": "请求字段未通过校验",
    "next": "按 issues 修正请求后重试",
    "details": {
      "issues": [
        {
          "path": "body.scope_year",
          "code": "greater_than_equal",
          "message": "Input should be greater than or equal to 2020"
        }
      ]
    }
  }
}
```

### 2.4 主流程

```mermaid
sequenceDiagram
    participant Client as 前端
    participant API as 业务 API
    participant DB as PostgreSQL

    Client->>API: POST /matters
    API->>DB: 写入 core.matter
    API-->>Client: 事项

    Client->>API: POST /matters/{id}/sources
    API->>DB: 写入 ops.source / ops.snapshot
    API-->>Client: 来源与快照

    Client->>API: POST /matters/{id}/requirements
    API->>DB: 写入 core.requirement / ops.evidence
    API-->>Client: 候选要求

    Client->>API: POST /matters/{id}/candidate-plans
    API->>DB: 写入候选计划、计划项、项来源、依据指纹
    API-->>Client: 候选计划

    Client->>API: GET /candidate-plans/{plan_id}
    API-->>Client: 待确认候选及出处

    alt 用户确认
        Client->>API: POST /candidate-plans/{plan_id}/confirm
        API->>DB: 重算依据、记录决定、创建任务
        API-->>Client: 决定与任务
    else 用户拒绝
        Client->>API: POST /candidate-plans/{plan_id}/reject
        API->>DB: 记录拒绝决定
        API-->>Client: 拒绝决定
    end

    Client->>API: GET /matters/{id}/tasks
    API-->>Client: 已确认任务及来源定位
```

## 3. 事项

### 3.1 创建事项

`POST /api/v1/matters`

请求字段：

| 字段 | 类型 | 必填 | 约束 |
| :--- | :--- | :--- | :--- |
| `goal` | string | 是 | 1—200 字符 |
| `type_code` | string | 否 | 默认 `pre_recommend`，2—32 字符，须为已启用的事项类型 |
| `scope_year` | integer | 是 | 2020—2100 |
| `scope_attrs` | object | 否 | 适用范围属性，原样保存 |

请求示例：

```json
{
  "goal": "申请 2027 年福州大学数学与统计学院推免",
  "type_code": "pre_recommend",
  "scope_year": 2027,
  "scope_attrs": {
    "school": "福州大学",
    "college": "数学与统计学院",
    "batch": "2027 届"
  }
}
```

响应 `201`：

```json
{
  "matter": {
    "id": "a0000000-0000-4000-8000-000000000001",
    "workspace_id": "00000000-0000-7000-8000-000000000002",
    "type_code": "pre_recommend",
    "type_name": "推免",
    "goal": "申请 2027 年福州大学数学与统计学院推免",
    "status": "draft",
    "scope_year": 2027,
    "scope_attrs": {
      "school": "福州大学",
      "college": "数学与统计学院",
      "batch": "2027 届"
    },
    "archived_at": null,
    "created_at": "2026-09-09T01:00:00+00:00",
    "updated_at": "2026-09-09T01:00:00+00:00",
    "tasks": {
      "total": 0,
      "done": 0,
      "open": 0
    },
    "latest_plan": null
  }
}
```

事项创建后状态为 `draft`。`latest_plan` 返回该事项最新候选计划的标识、状态和版本号。

### 3.2 读取事项列表

`GET /api/v1/matters`

返回当前演示工作区中的事项，按 `updated_at` 倒序排列：

```json
{
  "matters": [
    {
      "id": "a0000000-0000-4000-8000-000000000001",
      "workspace_id": "00000000-0000-7000-8000-000000000002",
      "type_code": "pre_recommend",
      "type_name": "推免",
      "goal": "申请 2027 年福州大学数学与统计学院推免",
      "status": "draft",
      "scope_year": 2027,
      "scope_attrs": {
        "school": "福州大学",
        "college": "数学与统计学院"
      },
      "archived_at": null,
      "created_at": "2026-09-09T01:00:00+00:00",
      "updated_at": "2026-09-09T01:00:00+00:00",
      "tasks": {
        "total": 0,
        "done": 0,
        "open": 0
      },
      "latest_plan": null
    }
  ]
}
```

### 3.3 读取事项详情

`GET /api/v1/matters/{matter_id}`

响应结构同创建事项的 `matter` 对象。事项不存在或不属于当前工作区时返回 `404 matter_not_found`。

## 4. 来源与要求

### 4.1 登记来源与快照

`POST /api/v1/matters/{matter_id}/sources`

请求字段：

| 字段 | 类型 | 必填 | 约束 |
| :--- | :--- | :--- | :--- |
| `url` | string | 是 | HTTP/HTTPS URL，最长 500 字符，不允许内嵌凭据 |
| `publisher` | string | 是 | 1—160 字符 |
| `title` | string | 是 | 1—500 字符，保存到快照提取结果 |
| `scope` | string | 否 | 最长 200 字符 |
| `scope_year` | integer | 是 | 2020—2100 |
| `published_date` | date | 否 | 来源发布日期 |
| `valid_from` / `valid_to` | date | 否 | `valid_to` 不得早于 `valid_from` |
| `content` | string | 是 | 来源正文 |
| `content_hash` | string | 否 | 64 位小写十六进制 SHA-256；省略时按 UTF-8 正文计算 |
| `fetched_at` | timestamptz | 否 | 省略时使用服务端当前时间 |
| `status` | string | 否 | `active`、`withdrawn`、`invalid`，默认 `active` |
| `auto_check_status` | string | 否 | `pending`、`passed`、`failed`、`conflict`，默认 `pending` |
| `roi_status` | string | 否 | `original`、`reposted`、`expired`、`ambiguous`，默认 `original` |
| `fragments` | array | 否 | 原文定位片段，元素含 `locator_kind`、`locator`、`quote` |
| `source_id` | UUID | 否 | 指定来源标识；省略时按 URL 生成稳定标识 |
| `snapshot_id` | UUID | 否 | 指定快照标识；省略时按 URL 与内容哈希生成稳定标识 |

`locator_kind` 可取 `section`、`page`、`text_span`、`table_row`、`list_item`。

请求示例：

```json
{
  "url": "https://math.fzu.edu.cn/info/1171/10393.htm",
  "publisher": "福州大学数学与统计学院",
  "title": "福州大学数学与统计学院2027年推荐优秀应届本科毕业生免试攻读研究生的工作方案",
  "scope": "2027 届、本院、校内推免推荐",
  "scope_year": 2027,
  "published_date": "2026-09-08",
  "content": "（5）符合推荐条件的学生，由本人自愿向学院提出申请，并于2026年9月10日下午15:00前提交《推荐免试攻读研究生资格申请表》以及相应科研成果和学科竞赛等奖项证明材料及成绩单（符合推免条件但放弃的同学需要提供放弃推免资格承诺书，本人签字按手印）。",
  "fragments": [
    {
      "locator_kind": "section",
      "locator": "第（5）项",
      "quote": "（5）符合推荐条件的学生，由本人自愿向学院提出申请，并于2026年9月10日下午15:00前提交《推荐免试攻读研究生资格申请表》以及相应科研成果和学科竞赛等奖项证明材料及成绩单（符合推免条件但放弃的同学需要提供放弃推免资格承诺书，本人签字按手印）。"
    }
  ]
}
```

响应 `201`：

```json
{
  "source": {
    "id": "b0000000-0000-4000-8000-000000000001",
    "publisher": "福州大学数学与统计学院",
    "url": "https://math.fzu.edu.cn/info/1171/10393.htm",
    "scope": "2027 届、本院、校内推免推荐",
    "scope_year": 2027,
    "valid_from": null,
    "valid_to": null,
    "status": "active",
    "auto_check_status": "pending",
    "roi_status": "original",
    "last_fetched_at": "2026-09-09T01:00:00+00:00",
    "created_at": "2026-09-09T01:00:00+00:00"
  },
  "snapshot": {
    "id": "b0000000-0000-4000-8000-000000000002",
    "source_id": "b0000000-0000-4000-8000-000000000001",
    "version_no": 1,
    "content_hash": "34599dc85bf72ca19837918f55c7cd275b9505bde994bbbea898ac7fa7b3abea",
    "title": "福州大学数学与统计学院2027年推荐优秀应届本科毕业生免试攻读研究生的工作方案",
    "published_date": "2026-09-08",
    "text": "（5）符合推荐条件的学生，由本人自愿向学院提出申请，并于2026年9月10日下午15:00前提交《推荐免试攻读研究生资格申请表》以及相应科研成果和学科竞赛等奖项证明材料及成绩单（符合推免条件但放弃的同学需要提供放弃推免资格承诺书，本人签字按手印）。",
    "fragments": [
      {
        "locator_kind": "section",
        "locator": "第（5）项",
        "quote": "（5）符合推荐条件的学生，由本人自愿向学院提出申请，并于2026年9月10日下午15:00前提交《推荐免试攻读研究生资格申请表》以及相应科研成果和学科竞赛等奖项证明材料及成绩单（符合推免条件但放弃的同学需要提供放弃推免资格承诺书，本人签字按手印）。"
      }
    ],
    "fetched_at": "2026-09-09T01:00:00+00:00",
    "is_current": true
  },
  "created": {
    "source": true,
    "snapshot": true
  }
}
```

登记规则：

- 来源按 URL 去重。同一 URL 的发布主体、适用年度或事项类型不一致时返回 `409 source_conflict`。
- 快照按来源与 `content_hash` 去重。同一内容重复登记时返回既有快照，`created.snapshot` 为 `false`。
- 新内容按来源自动分配递增的 `version_no`，并成为当前快照。
- `created.source` 与 `created.snapshot` 分别表示本次请求是否创建了新记录。
- `title`、`published_date`、`content` 和 `fragments` 保存在快照的提取结果中。

### 4.2 读取事项来源链

`GET /api/v1/matters/{matter_id}/sources`

返回与当前事项关联的来源。关联路径为：来源快照被该事项的候选要求引用，或来源快照被该事项候选计划项引用。已登记但尚未被要求或计划项引用的来源不出现在结果中。

```json
{
  "sources": [
    {
      "id": "b0000000-0000-4000-8000-000000000001",
      "publisher": "福州大学数学与统计学院",
      "url": "https://math.fzu.edu.cn/info/1171/10393.htm",
      "scope": "2027 届、本院、校内推免推荐",
      "scope_year": 2027,
      "valid_from": null,
      "valid_to": null,
      "status": "active",
      "auto_check_status": "pending",
      "roi_status": "original",
      "last_fetched_at": "2026-09-09T01:00:00+00:00",
      "created_at": "2026-09-09T01:00:00+00:00",
      "snapshots": [
        {
          "id": "b0000000-0000-4000-8000-000000000002",
          "source_id": "b0000000-0000-4000-8000-000000000001",
          "version_no": 1,
          "content_hash": "34599dc85bf72ca19837918f55c7cd275b9505bde994bbbea898ac7fa7b3abea",
          "title": "福州大学数学与统计学院2027年推荐优秀应届本科毕业生免试攻读研究生的工作方案",
          "published_date": "2026-09-08",
          "text": "（5）符合推荐条件的学生，由本人自愿向学院提出申请，并于2026年9月10日下午15:00前提交《推荐免试攻读研究生资格申请表》以及相应科研成果和学科竞赛等奖项证明材料及成绩单（符合推免条件但放弃的同学需要提供放弃推免资格承诺书，本人签字按手印）。",
          "fragments": [
            {
              "locator_kind": "section",
              "locator": "第（5）项",
              "quote": "（5）符合推荐条件的学生，由本人自愿向学院提出申请，并于2026年9月10日下午15:00前提交《推荐免试攻读研究生资格申请表》以及相应科研成果和学科竞赛等奖项证明材料及成绩单（符合推免条件但放弃的同学需要提供放弃推免资格承诺书，本人签字按手印）。"
            }
          ],
          "fetched_at": "2026-09-09T01:00:00+00:00",
          "is_current": true,
          "requirements": [
            {
              "id": "c0000000-0000-4000-8000-000000000001",
              "matter_id": "a0000000-0000-4000-8000-000000000001",
              "snapshot_id": "b0000000-0000-4000-8000-000000000002",
              "field_key": "application.deadline",
              "label": "提交申请与材料截止",
              "obligation_nature": "required",
              "extract_status": "checked",
              "scope": "2027 届、本院",
              "value_text": "2026-09-10T15:00:00+08:00",
              "value_type": "text",
              "confidence": 0.9,
              "checked_at": "2026-09-09T01:00:00+00:00",
              "created_at": "2026-09-09T01:00:00+00:00",
              "updated_at": "2026-09-09T01:00:00+00:00",
              "evidence": [
                {
                  "id": "d0000000-0000-4000-8000-000000000001",
                  "source_id": "b0000000-0000-4000-8000-000000000001",
                  "snapshot_id": "b0000000-0000-4000-8000-000000000002",
                  "locator_kind": "section",
                  "locator": "第（5）项",
                  "quote": "（5）符合推荐条件的学生，由本人自愿向学院提出申请，并于2026年9月10日下午15:00前提交《推荐免试攻读研究生资格申请表》以及相应科研成果和学科竞赛等奖项证明材料及成绩单（符合推免条件但放弃的同学需要提供放弃推免资格承诺书，本人签字按手印）。",
                  "quote_hash": "34599dc85bf72ca19837918f55c7cd275b9505bde994bbbea898ac7fa7b3abea",
                  "fetched_at": "2026-09-09T01:00:00+00:00"
                }
              ]
            }
          ]
        }
      ]
    }
  ]
}
```

每个来源返回其全部快照版本，`is_current` 标识当前版本；要求嵌套在对应快照下，证据嵌套在要求下。候选要求没有独立的列表接口，读取入口为来源链。

### 4.3 写入候选要求

`POST /api/v1/matters/{matter_id}/requirements`

请求体为一个批次：

```json
{
  "requirements": [
    {
      "field_key": "application.deadline",
      "label": "提交申请与材料截止",
      "obligation_nature": "required",
      "extract_status": "checked",
      "scope": "2027 届、本院",
      "value_text": "2026-09-10T15:00:00+08:00",
      "value_type": "text",
      "confidence": 0.9,
      "snapshot_id": "b0000000-0000-4000-8000-000000000002",
      "evidence": [
        {
          "source_id": "b0000000-0000-4000-8000-000000000001",
          "snapshot_id": "b0000000-0000-4000-8000-000000000002",
          "locator_kind": "section",
          "locator": "第（5）项",
          "quote": "（5）符合推荐条件的学生，由本人自愿向学院提出申请，并于2026年9月10日下午15:00前提交《推荐免试攻读研究生资格申请表》以及相应科研成果和学科竞赛等奖项证明材料及成绩单（符合推免条件但放弃的同学需要提供放弃推免资格承诺书，本人签字按手印）。"
        }
      ]
    }
  ]
}
```

要求字段：

| 字段 | 类型 | 必填 | 约束 |
| :--- | :--- | :--- | :--- |
| `field_key` | string | 是 | 小写字母开头，允许小写字母、数字、下划线和点，2—64 字符 |
| `label` | string | 是 | 1—120 字符 |
| `obligation_nature` | string | 否 | `required`、`advised`、`optional`、`to_verify`，默认 `to_verify` |
| `extract_status` | string | 否 | `extracted`、`checked`、`to_review`、`rejected`，默认 `extracted` |
| `scope` | string | 否 | 最长 200 字符 |
| `value_text` | string | 否 | 按 `value_type` 校验规范值 |
| `value_type` | string | 否 | `text`、`date`、`number`、`boolean`、`enum`，默认 `text` |
| `confidence` | number | 否 | 0—1 |
| `snapshot_id` | UUID | 是 | 必须属于已登记快照 |
| `evidence` | array | 是 | 至少一条证据 |

`value_text` 校验规则：

| `value_type` | 规范值 |
| :--- | :--- |
| `date` | `YYYY-MM-DD` |
| `number` | 不带千位分隔符的十进制数 |
| `boolean` | `true` 或 `false` |
| `text` / `enum` | 保留原意的文本 |

写入约束：

- 快照必须存在，其来源状态必须为 `active`。
- 来源适用年度与事项年度同时存在时必须一致。
- 每条证据的 `snapshot_id` 必须等于要求的 `snapshot_id`。
- 每条证据的 `source_id` 必须等于快照所属来源。
- `extract_status` 为 `checked` 时写入 `checked_at`。
- 证据引文非空时计算 SHA-256 并保存为 `quote_hash`。

响应 `201`：

```json
{
  "requirements": [
    {
      "id": "c0000000-0000-4000-8000-000000000001",
      "matter_id": "a0000000-0000-4000-8000-000000000001",
      "snapshot_id": "b0000000-0000-4000-8000-000000000002",
      "field_key": "application.deadline",
      "label": "提交申请与材料截止",
      "obligation_nature": "required",
      "extract_status": "checked",
      "scope": "2027 届、本院",
      "value_text": "2026-09-10T15:00:00+08:00",
      "value_type": "text",
      "confidence": 0.9,
      "checked_at": "2026-09-09T01:00:00+00:00",
      "created_at": "2026-09-09T01:00:00+00:00",
      "updated_at": "2026-09-09T01:00:00+00:00",
      "evidence": [
        {
          "id": "d0000000-0000-4000-8000-000000000001",
          "source_id": "b0000000-0000-4000-8000-000000000001",
          "snapshot_id": "b0000000-0000-4000-8000-000000000002",
          "locator_kind": "section",
          "locator": "第（5）项",
          "quote": "（5）符合推荐条件的学生，由本人自愿向学院提出申请，并于2026年9月10日下午15:00前提交《推荐免试攻读研究生资格申请表》以及相应科研成果和学科竞赛等奖项证明材料及成绩单（符合推免条件但放弃的同学需要提供放弃推免资格承诺书，本人签字按手印）。",
          "quote_hash": "34599dc85bf72ca19837918f55c7cd275b9505bde994bbbea898ac7fa7b3abea",
          "fetched_at": "2026-09-09T01:00:00+00:00"
        }
      ]
    }
  ]
}
```

## 5. 候选计划

### 5.1 创建候选计划

`POST /api/v1/matters/{matter_id}/candidate-plans`

请求体：

```json
{
  "items": [
    {
      "client_item_id": "t1",
      "title": "提交申请表",
      "detail": "按学院要求提交资格申请表",
      "obligation_nature": "required",
      "official_deadline_date": "2026-09-10",
      "official_deadline_at": "2026-09-10T15:00:00+08:00",
      "suggested_date": "2026-09-09",
      "depends_on": [],
      "evidence_required": true,
      "requirement_id": "c0000000-0000-4000-8000-000000000001",
      "sources": [
        {
          "source_id": "b0000000-0000-4000-8000-000000000001",
          "snapshot_id": "b0000000-0000-4000-8000-000000000002",
          "locator_kind": "section",
          "locator": "第（5）项",
          "quote": "（5）符合推荐条件的学生，由本人自愿向学院提出申请，并于2026年9月10日下午15:00前提交《推荐免试攻读研究生资格申请表》以及相应科研成果和学科竞赛等奖项证明材料及成绩单（符合推免条件但放弃的同学需要提供放弃推免资格承诺书，本人签字按手印）。"
        }
      ]
    },
    {
      "client_item_id": "t2",
      "title": "准备成绩单",
      "detail": "准备教务盖章成绩单",
      "obligation_nature": "required",
      "official_deadline_date": "2026-09-10",
      "suggested_date": "2026-09-09",
      "depends_on": ["t1"],
      "evidence_required": true,
      "sources": []
    }
  ]
}
```

计划项字段：

| 字段 | 类型 | 必填 | 约束 |
| :--- | :--- | :--- | :--- |
| `client_item_id` | string | 是 | 计划内唯一，1—80 字符 |
| `title` | string | 是 | 1—160 字符 |
| `detail` | string | 否 | 计划项说明 |
| `obligation_nature` | string | 否 | `required`、`advised`、`optional`、`to_verify`，默认 `to_verify` |
| `official_deadline_date` | date | 否 | 来源明确给出的日期 |
| `official_deadline_at` | timestamptz | 否 | 来源明确给出的时刻 |
| `suggested_date` | date | 否 | 个人建议准备日 |
| `depends_on` | string[] | 否 | 同一计划内的 `client_item_id` |
| `evidence_required` | boolean | 否 | 默认 `false` |
| `requirement_id` | UUID | 否 | 必须属于当前事项 |
| `sources` | array | 否 | 计划项出处，元素含 `source_id`、`snapshot_id`、`locator_kind`、`locator`、`quote` |

校验规则：

- `client_item_id` 在同一计划内唯一。
- `depends_on` 不得重复、不得自引用、不得引用未知条目。
- 依赖关系不得成环。
- `official_deadline_at` 存在时，按 `Asia/Shanghai` 换算出的日期必须与 `official_deadline_date` 一致；省略日期时自动写入该换算日期。
- `requirement_id` 必须属于当前事项。
- `sources` 中的来源与快照必须匹配；来源状态必须为 `active`，快照必须为当前版本。

响应 `201`：

```json
{
  "plan": {
    "id": "e0000000-0000-4000-8000-000000000001",
    "matter_id": "a0000000-0000-4000-8000-000000000001",
    "version_no": 1,
    "status": "pending",
    "basis_version": "7f5c5a5fd8d1f3e5f4b4f4f6a9d2c0e9d7f2b3c4a5e6f708192a3b4c5d6e7f80",
    "generated_at": "2026-09-09T01:00:00+00:00",
    "confirmed_at": null,
    "expired_at": null,
    "confirmed_by": null,
    "op_id": null,
    "matter": {
      "id": "a0000000-0000-4000-8000-000000000001",
      "goal": "申请 2027 年福州大学数学与统计学院推免",
      "type_code": "pre_recommend",
      "scope_year": 2027,
      "scope_attrs": {
        "school": "福州大学",
        "college": "数学与统计学院"
      }
    },
    "items": [
      {
        "id": "f0000000-0000-4000-8000-000000000001",
        "seq": 1,
        "title": "提交申请表",
        "detail": "按学院要求提交资格申请表",
        "obligation_nature": "required",
        "official_deadline_date": "2026-09-10",
        "official_deadline_at": "2026-09-10T07:00:00+00:00",
        "suggested_date": "2026-09-09",
        "depends_on_item_ids": [],
        "evidence_required": true,
        "requirement_id": "c0000000-0000-4000-8000-000000000001",
        "created_at": "2026-09-09T01:00:00+00:00",
        "requirement": {
          "id": "c0000000-0000-4000-8000-000000000001",
          "field_key": "application.deadline",
          "label": "提交申请与材料截止",
          "obligation_nature": "required",
          "extract_status": "checked"
        },
        "sources": [
          {
            "id": "f1000000-0000-4000-8000-000000000001",
            "source_id": "b0000000-0000-4000-8000-000000000001",
            "publisher": "福州大学数学与统计学院",
            "url": "https://math.fzu.edu.cn/info/1171/10393.htm",
            "source_status": "active",
            "snapshot_id": "b0000000-0000-4000-8000-000000000002",
            "version_no": 1,
            "content_hash": "34599dc85bf72ca19837918f55c7cd275b9505bde994bbbea898ac7fa7b3abea",
            "fetched_at": "2026-09-09T01:00:00+00:00",
            "is_current": true,
            "locator_kind": "section",
            "locator": "第（5）项",
            "quote": "（5）符合推荐条件的学生，由本人自愿向学院提出申请，并于2026年9月10日下午15:00前提交《推荐免试攻读研究生资格申请表》以及相应科研成果和学科竞赛等奖项证明材料及成绩单（符合推免条件但放弃的同学需要提供放弃推免资格承诺书，本人签字按手印）。"
          }
        ]
      },
      {
        "id": "f0000000-0000-4000-8000-000000000002",
        "seq": 2,
        "title": "准备成绩单",
        "detail": "准备教务盖章成绩单",
        "obligation_nature": "required",
        "official_deadline_date": "2026-09-10",
        "official_deadline_at": null,
        "suggested_date": "2026-09-09",
        "depends_on_item_ids": [
          "f0000000-0000-4000-8000-000000000001"
        ],
        "evidence_required": true,
        "requirement_id": null,
        "created_at": "2026-09-09T01:00:00+00:00",
        "requirement": null,
        "sources": []
      }
    ],
    "decision": null,
    "tasks": []
  }
}
```

计划项在确认前即可读取。计划状态固定从 `pending` 开始，`basis_version` 由服务端在计划项与来源写入后计算。

### 5.2 读取候选计划列表

`GET /api/v1/matters/{matter_id}/candidate-plans`

```json
{
  "plans": [
    {
      "id": "e0000000-0000-4000-8000-000000000001",
      "matter_id": "a0000000-0000-4000-8000-000000000001",
      "version_no": 1,
      "status": "pending",
      "basis_version": "7f5c5a5fd8d1f3e5f4b4f4f6a9d2c0e9d7f2b3c4a5e6f708192a3b4c5d6e7f80",
      "generated_at": "2026-09-09T01:00:00+00:00",
      "confirmed_at": null,
      "expired_at": null,
      "item_count": 2,
      "requirement_linked_count": 1,
      "source_count": 1,
      "decision": null
    }
  ]
}
```

列表按 `version_no` 倒序排列。`decision` 非空时包含 `decision`、`decided_by`、`decided_at` 和 `operation_id`。

### 5.3 读取候选计划详情

`GET /api/v1/candidate-plans/{plan_id}`

响应结构同创建候选计划的 `plan` 对象。详情包含按 `seq` 排列的全部计划项、每项关联的要求摘要、每项出处，以及已有决定和任务。计划不存在或不属于当前工作区时返回 `404 plan_not_found`。

### 5.4 确认候选计划

`POST /api/v1/candidate-plans/{plan_id}/confirm`

请求头：

| 请求头 | 必填 | 约束 |
| :--- | :--- | :--- |
| `Idempotency-Key` | 是 | UUID 字符串 |

请求体为空。

响应 `200`：

```json
{
  "plan_id": "e0000000-0000-4000-8000-000000000001",
  "status": "confirmed",
  "decision": {
    "id": "e1000000-0000-4000-8000-000000000001",
    "plan_id": "e0000000-0000-4000-8000-000000000001",
    "decision": "confirmed",
    "decided_by": "00000000-0000-7000-8000-000000000001",
    "decided_at": "2026-09-09T01:05:00+00:00",
    "operation_id": "70000000-0000-4000-8000-000000000001"
  },
  "tasks": [
    {
      "id": "71000000-0000-4000-8000-000000000001",
      "matter_id": "a0000000-0000-4000-8000-000000000001",
      "plan_id": "e0000000-0000-4000-8000-000000000001",
      "plan_item_id": "f0000000-0000-4000-8000-000000000001",
      "title": "提交申请表",
      "status": "pending",
      "due_at": "2026-09-10T07:00:00+00:00",
      "official_deadline_date": "2026-09-10",
      "official_deadline_at": "2026-09-10T07:00:00+00:00",
      "suggested_date": "2026-09-09",
      "depends_on": [],
      "completion_evidence": null,
      "created_at": "2026-09-09T01:05:00+00:00",
      "updated_at": "2026-09-09T01:05:00+00:00"
    },
    {
      "id": "71000000-0000-4000-8000-000000000002",
      "matter_id": "a0000000-0000-4000-8000-000000000001",
      "plan_id": "e0000000-0000-4000-8000-000000000001",
      "plan_item_id": "f0000000-0000-4000-8000-000000000002",
      "title": "准备成绩单",
      "status": "pending",
      "due_at": null,
      "official_deadline_date": "2026-09-10",
      "official_deadline_at": null,
      "suggested_date": "2026-09-09",
      "depends_on": [
        "71000000-0000-4000-8000-000000000001"
      ],
      "completion_evidence": null,
      "created_at": "2026-09-09T01:05:00+00:00",
      "updated_at": "2026-09-09T01:05:00+00:00"
    }
  ],
  "replayed": false
}
```

确认执行顺序：

| 顺序 | 检查 | 失败结果 |
| :--- | :--- | :--- |
| 1 | 计划存在且属于当前工作区 | `404 plan_not_found` |
| 2 | 幂等键是否已用于同一计划与同一决定 | 已用于其他计划或决定时返回 `409 operation_conflict`；同计划同决定时返回既有结果 |
| 3 | 计划是否已有终态决定 | `409 plan_already_decided` |
| 4 | 计划状态是否可决定 | `409 plan_expired` 或 `409 plan_not_pending` |
| 5 | 官方期限是否已过 | `409 official_deadline_passed`，计划保持原状态 |
| 6 | 当前依据指纹是否与生成时一致 | `409 basis_changed`，计划转为 `expired` 并写入 `expired_at` |
| 7 | 依据来源是否可用 | `409 source_unavailable` |
| 8 | 写入确认决定、计划状态与全部任务 | 同一数据库事务提交 |

确认成功后：

- 计划状态为 `confirmed`，写入 `confirmed_at`、`confirmed_by` 和 `op_id`。
- 写入一条 `confirmed` 计划决定。
- 每个计划项创建一条 `core.task`，`plan_item_id` 唯一。
- 计划项依赖映射为任务 ID 依赖。
- `official_deadline_at` 原样写入 `due_at`；只有日期型期限时 `due_at` 为空。

### 5.5 拒绝候选计划

`POST /api/v1/candidate-plans/{plan_id}/reject`

请求头与确认接口相同。拒绝只记录 `rejected` 决定，不创建任务，也不写计划 `op_id`。

响应 `200`：

```json
{
  "plan_id": "e0000000-0000-4000-8000-000000000001",
  "status": "rejected",
  "decision": {
    "id": "e1000000-0000-4000-8000-000000000002",
    "plan_id": "e0000000-0000-4000-8000-000000000001",
    "decision": "rejected",
    "decided_by": "00000000-0000-7000-8000-000000000001",
    "decided_at": "2026-09-09T01:05:00+00:00",
    "operation_id": "70000000-0000-4000-8000-000000000002"
  },
  "tasks": [],
  "replayed": false
}
```

拒绝不校验依据指纹与官方期限。只有 `pending` 状态的计划可以拒绝。

### 5.6 确认与拒绝的幂等规则

| 场景 | 结果 |
| :--- | :--- |
| 同一计划、同一决定、同一 `Idempotency-Key` | `200`，返回既有决定与任务，`replayed` 为 `true` |
| 同一幂等键用于其他计划或其他决定 | `409 operation_conflict` |
| 已有终态决定，使用新幂等键再次确认或拒绝 | `409 plan_already_decided`，`details` 返回当前状态与既有决定 |
| `Idempotency-Key` 不是合法 UUID | `400 invalid_idempotency_key` |
| 缺少 `Idempotency-Key` | `422 validation_error` |

幂等键在数据库中全局唯一。调用方应为每次用户决定生成一个 UUID，并在网络重试时原样复用。

## 6. 个人任务

### 6.1 读取事项任务

`GET /api/v1/matters/{matter_id}/tasks`

```json
{
  "tasks": [
    {
      "id": "71000000-0000-4000-8000-000000000001",
      "matter_id": "a0000000-0000-4000-8000-000000000001",
      "plan_id": "e0000000-0000-4000-8000-000000000001",
      "plan_item_id": "f0000000-0000-4000-8000-000000000001",
      "title": "提交申请表",
      "status": "pending",
      "due_at": "2026-09-10T07:00:00+00:00",
      "official_deadline_date": "2026-09-10",
      "official_deadline_at": "2026-09-10T07:00:00+00:00",
      "suggested_date": "2026-09-09",
      "depends_on": [],
      "completion_evidence": null,
      "created_at": "2026-09-09T01:05:00+00:00",
      "updated_at": "2026-09-09T01:05:00+00:00",
      "sources": [
        {
          "source_id": "b0000000-0000-4000-8000-000000000001",
          "publisher": "福州大学数学与统计学院",
          "url": "https://math.fzu.edu.cn/info/1171/10393.htm",
          "source_status": "active",
          "snapshot_id": "b0000000-0000-4000-8000-000000000002",
          "version_no": 1,
          "content_hash": "34599dc85bf72ca19837918f55c7cd275b9505bde994bbbea898ac7fa7b3abea",
          "fetched_at": "2026-09-09T01:00:00+00:00",
          "is_current": true,
          "locator_kind": "section",
          "locator": "第（5）项",
          "quote": "（5）符合推荐条件的学生，由本人自愿向学院提出申请，并于2026年9月10日下午15:00前提交《推荐免试攻读研究生资格申请表》以及相应科研成果和学科竞赛等奖项证明材料及成绩单（符合推免条件但放弃的同学需要提供放弃推免资格承诺书，本人签字按手印）。"
        }
      ]
    }
  ]
}
```

任务读取通过 `plan_item_id` 关联计划项来源，返回快照、定位和引文。仅确认候选计划会创建任务；拒绝、过期或待确认计划不会产生任务。

## 7. 依据指纹

`basis_version` 是规范化依据输入的 SHA-256。输入使用对象键排序、数组按稳定标识排序、保留显式空值、紧凑 UTF-8 JSON 编码。生成时间和请求随机标识不进入指纹。

当前指纹输入包含：

| 分组 | 内容 |
| :--- | :--- |
| 契约版本 | `agent_output` 与 `plan_strategy`，当前均为 `alpha-1` |
| 事项 | 标识、类型、模板版本、适用年度、适用范围属性、更新时间 |
| 要求 | 当前事项下全部未拒绝要求的标识、快照、字段、义务性质、提取状态、范围、规范值、置信度和更新时间 |
| 来源 | 上述要求及计划项所引用快照所属来源的标识、生命周期状态、快照版本、内容哈希、当前标记和获取时间 |
| 已确认事实 | 当前为空数组 |

确认时在锁定工作区、候选计划和依据来源后重新采集同一输入并计算指纹。指纹不一致时：

- 计划状态写为 `expired`，写入 `expired_at`。
- 不写计划决定。
- 不写任务。
- 返回 `409 basis_changed`，`details.current_basis_version` 返回当前指纹。

候选计划进入 `pending` 后，计划项与来源关联保持不变。需要修改内容时，创建新的候选计划版本。

## 8. 状态值

| 对象 | 字段 | 允许值 |
| :--- | :--- | :--- |
| 事项 | `status` | `draft`、`active`、`paused`、`archived`、`cancelled` |
| 来源 | `status` | `active`、`withdrawn`、`invalid` |
| 来源 | `auto_check_status` | `pending`、`passed`、`failed`、`conflict` |
| 来源 | `roi_status` | `original`、`reposted`、`expired`、`ambiguous` |
| 要求 | `obligation_nature` | `required`、`advised`、`optional`、`to_verify` |
| 要求 | `extract_status` | `extracted`、`checked`、`to_review`、`rejected` |
| 候选计划 | `status` | `draft`、`pending`、`confirmed`、`rejected`、`expired` |
| 计划决定 | `decision` | `confirmed`、`rejected` |
| 任务 | `status` | `pending`、`ready`、`in_progress`、`blocked`、`done`、`cancelled` |

本接口创建的事项为 `draft`，创建的候选计划为 `pending`，确认后创建的任务为 `pending`。

## 9. 错误码

| HTTP 状态 | `code` | 含义 |
| :--- | :--- | :--- |
| 400 | `invalid_idempotency_key` | `Idempotency-Key` 不是 UUID |
| 404 | `matter_not_found` | 事项不存在或不属于当前工作区 |
| 404 | `plan_not_found` | 候选计划不存在或不属于当前工作区 |
| 409 | `source_conflict` | 同一 URL 的来源元数据不一致，或来源标识冲突 |
| 409 | `snapshot_conflict` | 快照标识或内容归属冲突 |
| 409 | `operation_conflict` | 幂等键已用于其他计划或决定 |
| 409 | `plan_already_decided` | 候选计划已有终态决定 |
| 409 | `plan_expired` | 候选计划已过期 |
| 409 | `plan_not_pending` | 候选计划不在待确认状态 |
| 409 | `official_deadline_passed` | 候选计划包含已过的官方期限 |
| 409 | `basis_changed` | 依据指纹变化，候选计划已转为过期 |
| 409 / 422 | `source_unavailable` | 来源当前不可用；确认阶段返回 409，要求与计划写入阶段返回 422 |
| 409 | `data_conflict` | 数据库约束冲突 |
| 422 | `validation_error` | 请求字段校验失败 |
| 422 | `unknown_matter_type` | 事项类型不存在或未启用 |
| 422 | `unknown_snapshot` | 要求引用的快照不存在 |
| 422 | `scope_year_mismatch` | 来源适用年度与事项年度不一致 |
| 422 | `evidence_snapshot_mismatch` | 证据快照与要求快照不一致 |
| 422 | `evidence_source_mismatch` | 证据来源与快照所属来源不一致 |
| 422 | `unknown_requirement` | 计划项引用了不属于当前事项的要求 |
| 422 | `unknown_source_snapshot` | 计划项引用的来源与快照不存在或彼此不匹配 |
| 500 | `demo_identity_missing` | 演示用户或工作区不存在 |
| 500 | `internal_error` | 未预期的服务错误 |

## 10. 数据库依赖

接口依赖以下 Alpha 结构：

| 结构 | 用途 |
| :--- | :--- |
| `core.app_user`、`core.workspace` | 演示身份与工作区 |
| `core.matter_type`、`core.matter` | 事项类型与事项 |
| `ops.source`、`ops.snapshot` | 来源与版本化快照 |
| `core.requirement`、`ops.evidence` | 候选要求与原文证据 |
| `core.candidate_plan`、`core.candidate_plan_item` | 候选计划与计划项 |
| `core.candidate_plan_item_source` | 计划项出处 |
| `core.candidate_plan_decision` | 确认与拒绝决定 |
| `core.task` | 个人任务 |
| `core.v_matter_overview`、`core.v_plan_detail` | 事项与计划读取视图 |

数据库须启用行级安全，API 使用非所有者角色 `offerpilot_app` 连接。表所有者会绕过行级安全，不应用于 API 连接。

## 11. 演示限制

- 无登录与账户切换，所有请求使用固定演示身份。
- 不提供任务状态更新、事项归档或候选计划修改接口。
- 不执行网络抓取、模型调用、材料生成或外部提交。
- 不提供跨设备、多用户共享与权限管理。
- 官方期限只按调用方提供的计划项字段判断；接口不推断未给出的时刻。

