# 个人事实（成绩排名）接口

| 项目 | 内容 |
| :--- | :--- |
| 接口前缀 | `/api/v1` |
| 数据格式 | JSON，UTF-8 |
| 适用范围 | Alpha 单用户本地演示 |
| 业务契约 | [`api.md`](api.md) |
| 数据库结构 | 迁移 `0011_core_fact.sql` |

## 1. 范围与约束

本接口保存和读取当前演示用户的个人事实，维护事实版本，并在事实值变化时识别依赖旧版本的待确认候选计划。受影响候选在确认时按依据指纹转为过期。

Alpha 只注册成绩排名事实，`fact_type` 为 `gpa.rank`。其他事实类型返回 `422 unsupported_fact_type`。事实类型集合会在后续版本增长；保存、读取、版本、幂等和候选失效共用同一套事实层，类型差异由注册表隔离。

### 1.1 单值当前记录

- 事实属于用户，不绑定事项；同一用户的所有事项读取同一份当前确认版本。
- 每个 `(owner_id, fact_type)` 只有一条 `confirmed` 记录。
- 历史版本保留为 `superseded`；保存新值只改变当前记录，不删除历史。
- `scope` 和 `valid_from` 是当前值的属性，不参与事实身份；修改任一项会产生新版本并替代旧版本。
- 不提供同一类型多条当前记录、按事项覆盖或单条实例增删。
- 保存路径不包含 `fact_id` 或实例键；`PUT` 总是替换该类型的当前记录，同一类型无法保留两条并列的当前值。
- 该约束由 `core.fact` 的部分唯一索引保证，类型注册表不绕过该约束。
- 同一类型需要多条并列值时，需要在事实身份中增加实例键，并同步调整接口、版本规则和唯一约束；当前接口不提供该能力。
- 不提供草稿、撤回、删除和个人材料引用；保存请求即用户对事实值的确认。

### 1.2 与事项的关系

事项通过未拒绝要求的 `field_key` 和 `requirement_self_check.missing_fields` 确定相关事实键。Agent 运行读取相关事实的当前确认版本，并将事实条目写入候选计划的 `basis_input`。

事实保存只返回受影响的 `pending` 计划，不改变计划状态、决定或任务。计划确认时重新计算依据指纹；事实版本已变化时，计划转为 `expired`。

### 1.3 路径与资源

事实接口是用户级接口，路径不包含事项标识。事实归属来自当前演示身份，事项通过依据指纹引用事实版本。

`PUT /api/v1/facts/{fact_type}` 的路径标识事实类型。每个类型只有一条当前记录，`PUT` 替换该类型的当前值；读取接口按类型返回当前值与版本历史。类型进入路径后，读写、校验错误与版本历史都落在同一资源下，调用方无需在请求体中重复声明类型。

类型注册表与路由解耦：路由只解析 `{fact_type}` 并交给注册表，不为每个类型单独定义端点。类型集合增长时，URL 结构、请求模型和服务逻辑保持不变。

## 2. 类型注册表

事实层按 `fact_type` 解析注册项。每个注册项包含两个纯函数：

```python
@dataclass(frozen=True)
class FactRender:
    value_text: str
    agent_value: object | None


@dataclass(frozen=True)
class FactTypeSpec:
    normalize: Callable[[Mapping[str, Any]], dict[str, Any]]
    render: Callable[[Mapping[str, Any]], FactRender]
```

- `normalize` 校验请求值并返回规范化的 `value_json`。校验失败时返回问题列表，每项包含 `path`、`code`、`message`。
- `render` 从 `value_json` 生成展示文本和 Agent 使用的值。`agent_value` 为 `null` 时，该类型不参与 Agent 事实注入。
- 注册表的键就是 `fact_type`，也是事项要求的 `field_key` 和 Agent `confirmed_facts` 的键。
- 请求体中的 `value` 保持通用对象，由注册表校验。新增类型不修改请求模型、路由、服务、迁移或指纹逻辑。
- 新增类型需要注册校验器与渲染器，并补充该类型的接口测试和文档；工作量集中在校验规则、展示文本和 Agent 取值上。
- 注册表不改变单值当前记录约束。需要多实例的类型仍要扩展事实身份。

初始注册项：

| `fact_type` | 值写法 | `value_json` | `value_text` | `agent_value` |
| :--- | :--- | :--- | :--- | :--- |
| `gpa.rank` | `{position, cohort_size}` 或 `{percentile}` | `{position, cohort_size, percentile}` | `5/120` 或 `前 4.2%` | `percentile` |

## 3. 事实对象

```json
{
  "id": "d0000000-0000-4000-8000-000000000001",
  "fact_type": "gpa.rank",
  "value": {
    "position": 5,
    "cohort_size": 120,
    "percentile": 4.1667
  },
  "value_text": "5/120",
  "scope": "2027 届本科",
  "valid_from": "2026-09-01",
  "trust_level": "self",
  "status": "confirmed",
  "version_no": 1,
  "value_hash": "b1e4c7d9a0f2c3e5b7d9f1a3c5e7b9d1f3a5c7e9b1d3f5a7c9e1b3d5f7a9c1e3",
  "confirmed_at": "2026-09-09T01:00:00+00:00",
  "superseded_at": null,
  "created_at": "2026-09-09T01:00:00+00:00"
}
```

| 字段 | 类型 | 说明 |
| :--- | :--- | :--- |
| `id` | UUID | 事实版本标识；同一版本不可复用 |
| `fact_type` | string | 事实类型，Alpha 为 `gpa.rank` |
| `value` | object | 规范化后的 `value_json` |
| `value_text` | string | 服务端生成的展示文本 |
| `scope` | string \| null | 适用范围，最长 200 字符 |
| `valid_from` | date \| null | 值生效日期 |
| `trust_level` | string | 固定为 `self` |
| `status` | string | `confirmed` 或 `superseded` |
| `version_no` | integer | 同一用户、同一类型内递增，从 1 开始 |
| `value_hash` | string | 规范化事实内容的 SHA-256 |
| `confirmed_at` | timestamptz | 确认时间 |
| `superseded_at` | timestamptz \| null | 被新版本替代的时间 |
| `created_at` | timestamptz | 版本创建时间 |

### 3.1 `gpa.rank` 值

`gpa.rank` 接受两种互斥写法。

| 写法 | 示例 | 约束 |
| :--- | :--- | :--- |
| 名次与人数 | `{"position": 5, "cohort_size": 120}` | 两者均为正整数，`1 <= position <= cohort_size` |
| 百分位 | `{"percentile": 4.2}` | 大于 0 且不大于 100 |

百分位表示排名位于前百分之多少，数值越小越靠前。名次写法按 `position / cohort_size * 100` 计算，四舍五入保留 4 位小数；百分位写法同样保留 4 位小数。输出去掉无意义的尾零。

`value` 始终包含 `position`、`cohort_size`、`percentile` 三个键，不适用的键为 `null`：

```json
{
  "position": null,
  "cohort_size": null,
  "percentile": 4.2
}
```

`value_text` 由服务端生成：名次写法为 `5/120`，百分位写法为 `前 4.2%`。

### 3.2 `value_hash`

`value_hash` 对以下对象做规范化 JSON 编码后计算 SHA-256：

```json
{
  "fact_type": "gpa.rank",
  "scope": "2027 届本科",
  "valid_from": "2026-09-01",
  "value_json": {
    "position": 5,
    "cohort_size": 120,
    "percentile": 4.1667
  },
  "value_text": "5/120"
}
```

对象键按字典序排列，缺失的可选字段使用显式 `null`，以 UTF-8 紧凑 JSON 编码。

## 4. 保存事实

`PUT /api/v1/facts/{fact_type}`

`fact_type` 必须已注册，Alpha 只接受 `gpa.rank`。

请求体：

| 字段 | 类型 | 必填 | 约束 |
| :--- | :--- | :--- | :--- |
| `value` | object | 是 | 由类型注册表校验 |
| `scope` | string | 否 | 最长 200 字符；空字符串归一为 `null` |
| `valid_from` | date | 否 | `YYYY-MM-DD` |

名次写法：

```json
{
  "value": {
    "position": 5,
    "cohort_size": 120
  },
  "scope": "2027 届本科",
  "valid_from": "2026-09-01"
}
```

百分位写法：

```json
{
  "value": {
    "percentile": 4.2
  },
  "scope": "2027 届本科",
  "valid_from": "2026-09-01"
}
```

响应 `200`：

```json
{
  "fact": {
    "id": "d0000000-0000-4000-8000-000000000001",
    "fact_type": "gpa.rank",
    "value": {
      "position": 5,
      "cohort_size": 120,
      "percentile": 4.1667
    },
    "value_text": "5/120",
    "scope": "2027 届本科",
    "valid_from": "2026-09-01",
    "trust_level": "self",
    "status": "confirmed",
    "version_no": 1,
    "value_hash": "b1e4c7d9a0f2c3e5b7d9f1a3c5e7b9d1f3a5c7e9b1d3f5a7c9e1b3d5f7a9c1e3",
    "confirmed_at": "2026-09-09T01:00:00+00:00",
    "superseded_at": null,
    "created_at": "2026-09-09T01:00:00+00:00"
  },
  "created": true,
  "affected_plans": [
    {
      "plan_id": "e0000000-0000-4000-8000-000000000001",
      "matter_id": "a0000000-0000-4000-8000-000000000001",
      "version_no": 1,
      "stored_version_no": null
    }
  ]
}
```

`created` 表示本次请求是否写入新版本。值、`scope`、`valid_from` 全部相同且当前版本未变化时，返回当前事实，`created` 为 `false`，不递增版本号。`affected_plans` 仍按当前状态重新计算。

保存新值时：

1. 在事务内获取 `(owner_id, fact_type)` 级 advisory lock。
2. 读取当前 `confirmed` 版本。
3. 新内容与当前内容一致时直接返回。
4. 内容不同时写入 `version_no = 当前最大版本 + 1` 的新记录。
5. 旧 `confirmed` 版本写为 `superseded`，并写入 `superseded_at`。
6. 同一事务提交新版本和旧版本状态。

新版本写入后，旧版本仍可通过读取接口的 `versions` 查看。接口不提供删除历史版本的操作。

## 5. 读取事实

### 5.1 读取当前事实列表

`GET /api/v1/facts`

```json
{
  "facts": [
    {
      "id": "d0000000-0000-4000-8000-000000000001",
      "fact_type": "gpa.rank",
      "value": {
        "position": 5,
        "cohort_size": 120,
        "percentile": 4.1667
      },
      "value_text": "5/120",
      "scope": "2027 届本科",
      "valid_from": "2026-09-01",
      "trust_level": "self",
      "status": "confirmed",
      "version_no": 1,
      "value_hash": "b1e4c7d9a0f2c3e5b7d9f1a3c5e7b9d1f3a5c7e9b1d3f5a7c9e1b3d5f7a9c1e3",
      "confirmed_at": "2026-09-09T01:00:00+00:00",
      "superseded_at": null,
      "created_at": "2026-09-09T01:00:00+00:00"
    }
  ]
}
```

只返回当前 `confirmed` 版本，按 `fact_type` 字典序排列。没有当前事实时返回空数组。

### 5.2 读取单类型事实与版本

`GET /api/v1/facts/{fact_type}`

```json
{
  "fact": {
    "id": "d0000000-0000-4000-8000-000000000002",
    "fact_type": "gpa.rank",
    "value": {
      "position": 5,
      "cohort_size": 120,
      "percentile": 4.1667
    },
    "value_text": "5/120",
    "scope": "2027 届本科",
    "valid_from": "2026-09-01",
    "trust_level": "self",
    "status": "confirmed",
    "version_no": 2,
    "value_hash": "b1e4c7d9a0f2c3e5b7d9f1a3c5e7b9d1f3a5c7e9b1d3f5a7c9e1b3d5f7a9c1e3",
    "confirmed_at": "2026-09-09T01:00:00+00:00",
    "superseded_at": null,
    "created_at": "2026-09-09T01:00:00+00:00"
  },
  "versions": [
    {
      "id": "d0000000-0000-4000-8000-000000000002",
      "fact_type": "gpa.rank",
      "value": {
        "position": 5,
        "cohort_size": 120,
        "percentile": 4.1667
      },
      "value_text": "5/120",
      "scope": "2027 届本科",
      "valid_from": "2026-09-01",
      "trust_level": "self",
      "status": "confirmed",
      "version_no": 2,
      "value_hash": "b1e4c7d9a0f2c3e5b7d9f1a3c5e7b9d1f3a5c7e9b1d3f5a7c9e1b3d5f7a9c1e3",
      "confirmed_at": "2026-09-09T01:00:00+00:00",
      "superseded_at": null,
      "created_at": "2026-09-09T01:00:00+00:00"
    },
    {
      "id": "d0000000-0000-4000-8000-000000000001",
      "fact_type": "gpa.rank",
      "value": {
        "position": 8,
        "cohort_size": 120,
        "percentile": 6.6667
      },
      "value_text": "8/120",
      "scope": "2027 届本科",
      "valid_from": "2026-09-01",
      "trust_level": "self",
      "status": "superseded",
      "version_no": 1,
      "value_hash": "c2f5d8e0b1a3d4f6c8e0b2a4d6f8c0e2b4a6d8f0c2e4b6a8d0f2c4e6b8a0d2f4",
      "confirmed_at": "2026-09-08T01:00:00+00:00",
      "superseded_at": "2026-09-09T01:00:00+00:00",
      "created_at": "2026-09-08T01:00:00+00:00"
    }
  ]
}
```

`fact` 为当前确认版本；没有当前事实时为 `null`。`versions` 按 `version_no` 倒序排列，包含当前版本与全部历史版本。

## 6. 版本、幂等与并发

- `version_no` 在同一 `(owner_id, fact_type)` 内递增，初始为 1。
- 同一类型同时只允许一条 `confirmed` 记录；旧版本写入 `superseded` 后不再参与当前事实读取。
- 保存请求在事务内获取 `owner_id + fact_type` 级 advisory lock，避免并发请求写入重复版本号。
- 幂等比较使用规范化后的 `value_json`、`scope` 和 `valid_from`；三者全部相同即视为同一次保存。
- `value_hash` 参与候选计划依据指纹，版本号变化或值内容变化都会改变指纹。
- `scope` 与 `valid_from` 变化会产生新版本，即使 `value` 相同。

## 7. 受影响计划与旧候选失效

### 7.1 相关事实键

计划的相关事实键由以下来源合并，去重后按字典序排列：

- 事项下未拒绝要求的 `field_key`；
- `requirement_self_check.missing_fields`。

已注册且有当前确认版本的事实键写入事实条目；已注册但无当前版本的事实键写入显式空占位。未注册的事实键保留在运行级 `confirmed_facts` 中，并在依据输入中保留显式空占位。

### 7.2 保存后返回的受影响计划

保存事实后，查询同一用户工作区内状态为 `pending` 的候选计划。满足任一条件即列入 `affected_plans`：

- `basis_input.confirmed_facts` 中存在该 `fact_type` 的条目，且条目版本与当前确认版本不同；空占位条目按 `version_no = null` 参与比较。
- `basis_input.confirmed_facts` 中缺少该 `fact_type` 的条目，且计划相关事实键包含该 `fact_type`。

`affected_plans` 每项包含：

| 字段 | 说明 |
| :--- | :--- |
| `plan_id` | 候选计划标识 |
| `matter_id` | 事项标识 |
| `version_no` | 计划版本号 |
| `stored_version_no` | 计划记录的事实版本；缺少条目或空占位时为 `null` |

该查询只返回列表，不修改计划状态、`expired_at`、决定或任务。已确认、已拒绝和已过期计划不进入结果。

### 7.3 确认时失效

确认候选计划时，服务端在锁定事务内重新采集依据输入并计算指纹。事实版本变化导致指纹不一致时：

- 计划状态写为 `expired`，写入 `expired_at`；
- 不写计划决定；
- 不写任务；
- 返回 `409 basis_changed`。

`details` 包含：

```json
{
  "current_basis_version": "7f5c5a5fd8d1f3e5f4b4f4f6a9d2c0e9d7f2b3c4a5e6f708192a3b4c5d6e7f80",
  "stale_facts": [
    {
      "fact_type": "gpa.rank",
      "stored_version_no": 1,
      "current_version_no": 2,
      "current_fact_id": "d0000000-0000-4000-8000-000000000002"
    }
  ]
}
```

没有当前确认版本时，`current_version_no` 和 `current_fact_id` 为 `null`。依据指纹因其他输入变化而不一致时，`stale_facts` 为空数组。

### 7.4 计划读取的依据状态

候选计划列表、详情和事项的 `latest_plan` 返回 `basis_status` 与 `stale_facts`。

| `basis_status` | 条件 |
| :--- | :--- |
| `current` | 计划为 `pending`，存在相关事实键，且所有事实条目与当前确认版本一致 |
| `stale` | 计划为 `pending`，且至少一个事实条目与当前确认版本不一致 |
| `not_applicable` | 计划不是 `pending`，或计划没有相关事实键 |

`stale_facts` 仅在 `stale` 时非空，条目结构与确认失效响应一致。

## 8. Agent 运行

`POST /api/v1/matters/{matter_id}/agent-runs` 继续接受可选的 `confirmed_facts`，用于未进入事实档案的运行级字段。`gpa.rank` 以后端从 `core.fact` 读取的当前确认版本为准；请求中同时出现 `gpa.rank` 时，以已确认版本覆盖请求值。

后端按事项的相关事实键读取已注册类型的当前确认版本，并将事实条目写入候选计划的 `basis_input`。运行级 `confirmed_facts` 不形成事实版本，不进入依据指纹。

运行开始时记录所用事实版本。候选持久化前重新读取当前版本；版本已变化时运行失败，`error.code` 为 `VERSION_CONFLICT`，不写入依据已过时的候选计划。

规则评估使用渲染器提供的 `agent_value`。`gpa.rank` 使用 `percentile`，数值越小表示排名越靠前。没有确认事实时，自查结论为 `missing_info`，`missing_fields` 包含 `gpa.rank`，缺口为 `missing_personal_fact`。

## 9. 错误

| HTTP | `code` | 说明 |
| :--- | :--- | :--- |
| 422 | `unsupported_fact_type` | 路径事实类型未注册；`details.supported_fact_types` 列出当前类型 |
| 422 | `invalid_fact_value` | 事实值写法或范围不合法；`details.issues` 列出 `path`、`code`、`message` |
| 409 | `basis_changed` | 确认时依据指纹与生成时不一致；计划转为 `expired` |
| 500 | `demo_identity_missing` | 演示用户或工作区不存在 |

`invalid_fact_value` 示例：

```json
{
  "error": {
    "code": "invalid_fact_value",
    "message": "事实值不合法",
    "details": {
      "issues": [
        {
          "path": "value.position",
          "code": "greater_than_cohort",
          "message": "名次不得大于总人数"
        }
      ]
    }
  }
}
```

## 10. 数据模型

迁移 `0011_core_fact.sql`：

```sql
CREATE TYPE core.fact_status AS ENUM ('draft', 'confirmed', 'superseded', 'revoked');

CREATE TABLE core.fact (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id        uuid NOT NULL,
    fact_type       varchar(48) NOT NULL,
    value_text      text NOT NULL,
    value_json      jsonb NOT NULL DEFAULT '{}'::jsonb,
    value_hash      char(64) NOT NULL,
    scope           varchar(200),
    valid_from      date,
    trust_level     varchar(16) NOT NULL DEFAULT 'self',
    confirm_status  core.fact_status NOT NULL DEFAULT 'draft',
    version_no      integer NOT NULL,
    confirmed_at    timestamptz,
    superseded_at   timestamptz,
    created_at      timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_fact_type_version UNIQUE (owner_id, fact_type, version_no),
    CONSTRAINT ck_fact_version CHECK (version_no > 0),
    CONSTRAINT ck_fact_value_json CHECK (jsonb_typeof(value_json) = 'object'),
    CONSTRAINT ck_fact_value_hash CHECK (value_hash ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_fact_confirm CHECK (
        (confirm_status IN ('confirmed', 'superseded') AND confirmed_at IS NOT NULL)
        OR (confirm_status IN ('draft', 'revoked') AND confirmed_at IS NULL)
    ),
    CONSTRAINT ck_fact_superseded CHECK (
        (confirm_status = 'superseded') = (superseded_at IS NOT NULL)
    ),
    CONSTRAINT fk_fact_owner FOREIGN KEY (owner_id)
        REFERENCES core.app_user (id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX uq_fact_current ON core.fact (owner_id, fact_type)
    WHERE confirm_status = 'confirmed';
CREATE INDEX ix_fact_owner ON core.fact (owner_id, fact_type);

ALTER TABLE core.fact ENABLE ROW LEVEL SECURITY;

CREATE POLICY fact_owner ON core.fact
    USING (owner_id = (
        SELECT w.owner_id FROM core.workspace w
        WHERE w.id = NULLIF(current_setting('app.current_workspace_id', true), '')::uuid))
    WITH CHECK (owner_id = (
        SELECT w.owner_id FROM core.workspace w
        WHERE w.id = NULLIF(current_setting('app.current_workspace_id', true), '')::uuid));

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'offerpilot_app') THEN
        GRANT SELECT, INSERT, UPDATE ON core.fact TO offerpilot_app;
    END IF;
END $$;
```

接口只写入 `confirmed` 与 `superseded`。`draft` 和 `revoked` 保留在 schema 中，当前接口不提供对应操作。

`uq_fact_current` 是单值当前记录的数据库保证。同一用户、同一事实类型无法同时存在两条 `confirmed` 记录。

## 11. 验收场景

| 编号 | 场景 | 预期 |
| :--- | :--- | :--- |
| F-01 | 首次保存名次 | 返回版本 1，`created` 为 `true`，`value_text` 为 `5/120` |
| F-02 | 首次保存百分位 | 返回版本 1，`value_text` 为 `前 4.2%`，`percentile` 为 4.2 |
| F-03 | 保存相同值、范围和生效日 | 不新增版本，`created` 为 `false` |
| F-04 | 保存新值 | 新版本号递增，旧版本转为 `superseded` 并写入 `superseded_at` |
| F-05 | 读取当前事实 | 只返回 `confirmed` 版本 |
| F-06 | 读取版本历史 | 按 `version_no` 倒序返回当前与历史版本 |
| F-07 | 保存后查询受影响计划 | 返回记录旧事实版本或缺少事实条目的 `pending` 计划，不改变计划状态 |
| F-08 | 事实版本变化后确认计划 | 计划转为 `expired`，返回 `409 basis_changed` 与 `stale_facts` |
| F-09 | 读取计划列表、详情与事项最新计划 | 返回 `basis_status` 与 `stale_facts` |
| F-10 | 未注册类型 | 返回 `422 unsupported_fact_type` |
| F-11 | 名次大于总人数 | 返回 `422 invalid_fact_value`，`details.issues` 定位到 `value.position` |
| F-12 | Agent 运行使用持久化事实 | 候选依据记录当前事实版本，`gpa.rank` 使用 `percentile` |
| F-13 | 运行期间事实版本变化 | 运行失败为 `VERSION_CONFLICT`，不写入旧依据候选 |
