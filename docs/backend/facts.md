# 个人事实（成绩、排名、英语、证书与竞赛）接口

| 项目 | 内容 |
| :--- | :--- |
| 接口前缀 | `/api/v1` |
| 数据格式 | JSON，UTF-8 |
| 适用范围 | Alpha 单用户本地演示 |
| 业务契约 | [`api.md`](api.md) |
| 数据库结构 | 迁移 `0012_core_fact_matter.sql` |

## 1. 范围与约束

本接口按事项保存和读取当前演示用户的个人事实，维护事项内的事实版本，并在当前事项的事实值变化时识别依赖旧版本的待确认候选计划。受影响候选在确认时按依据指纹转为过期。

Alpha 注册 `gpa.rank`、`gpa.score`、`cet4`、`cet6`、`toefl`、`ielts`、`cert`、`comp` 八种事实。其他事实类型返回 `422 unsupported_fact_type`。事实类型集合会在后续版本增长；保存、读取、版本、幂等和候选失效共用同一套事实层，类型差异由注册表隔离。

### 1.1 事项内单值当前记录

- 事实归属由 `owner_id` 与 `matter_id` 共同确定；同一用户在不同事项中各自维护独立的事实档案。
- 每个 `(owner_id, matter_id, fact_type)` 只有一条 `confirmed` 记录。
- 历史版本保留为 `superseded`；保存新值只改变当前事项的当前记录，不删除历史。
- `scope` 和 `valid_from` 是当前值的属性，不参与事实身份；修改任一项会在当前事项中产生新版本并替代旧版本。
- `scope` 只描述统计范围；事实归属由 `matter_id` 决定，两个事项各自维护独立记录。
- 不提供同一事项同一类型多条当前记录、单条实例增删或跨事项引用。
- 保存路径不包含 `fact_id` 或实例键；`PUT` 总是替换当前事项该类型的当前记录。
- 不提供草稿、撤回、删除和个人材料引用；保存请求即用户对当前事项事实值的确认。

### 1.2 与事项的关系

事项通过未拒绝要求的 `field_key` 和 `requirement_self_check.missing_fields` 确定相关事实键。Agent 运行读取当前事项相关事实的当前确认版本，并将事实条目写入候选计划的 `basis_input`。

事实保存只返回当前事项内受影响的 `pending` 计划，不改变计划状态、决定或任务。计划确认时重新计算当前事项的依据指纹；事实版本已变化时，计划转为 `expired`。

### 1.3 路径与资源

事项标识通过路径参数 `{matter_id}` 传递。服务端在每次保存或读取前校验该事项属于当前工作区，校验失败返回 `404 matter_not_found`。事实类型通过路径参数 `{fact_type}` 传递。

事实接口以事项为资源边界，路径必须包含 `matter_id`；服务端不提供用户级事实读写端点。

| 方法 | 路径 | 用途 |
| :--- | :--- | :--- |
| `PUT` | `/api/v1/matters/{matter_id}/facts/{fact_type}` | 保存当前事项的当前值 |
| `GET` | `/api/v1/matters/{matter_id}/facts` | 读取当前事项的当前确认事实列表 |
| `GET` | `/api/v1/matters/{matter_id}/facts/{fact_type}` | 读取当前事项的单类型当前值与版本历史 |

类型注册表与路由解耦：路由只解析 `{fact_type}` 并交给注册表，不为每个类型单独定义端点。类型集合增长时，URL 结构、请求模型和服务逻辑保持不变。

### 1.4 历史用户级记录

迁移 `0012` 之前的用户级事实保留在 `core.fact` 中，`matter_id` 为空。这类记录标记为未归属历史：

- 任何事项的事实读取只查询 `matter_id` 等于当前事项的记录，未归属记录不会返回。
- Agent 运行、候选依据、`affected_plans`、`basis_status` 和确认校验都不读取未归属记录。
- 用户在当前事项重新保存同类型事实时，从版本 1 开始建立该事项的档案。

## 2. 类型注册表

事实层按 `fact_type` 解析注册项。每个注册项包含两个纯函数：

```python
@dataclass(frozen=True)
class FactRender:
    value_text: str
    agent_value: object | None


@dataclass(frozen=True)
class FactTypeSpec:
    fact_type: str
    normalize: Callable[[Mapping[str, Any]], dict[str, Any]]
    render: Callable[[Mapping[str, Any]], FactRender]
```

- `normalize` 校验请求值并返回规范化的 `value_json`。校验失败时返回问题列表，每项包含 `path`、`code`、`message`。
- `render` 从 `value_json` 生成展示文本和 Agent 使用的值。`agent_value` 为 `null` 时，该类型不参与 Agent 事实注入。
- 注册表的键就是 `fact_type`，也是事项要求的 `field_key` 和 Agent `confirmed_facts` 的键。
- 请求体中的 `value` 保持通用对象，由注册表校验。新增类型不修改请求模型、路由、服务、迁移或指纹逻辑。
- 新增类型需要注册校验器与渲染器，并补充该类型的接口测试和文档；工作量集中在校验规则、展示文本和 Agent 取值上。
- 注册表不改变事项内单值当前记录约束。

初始注册项：

| `fact_type` | 值写法 | `value_json` | `value_text` | `agent_value` |
| :--- | :--- | :--- | :--- | :--- |
| `gpa.rank` | `{position, cohort_size}` 或 `{percentile}` | `{position, cohort_size, percentile}` | `5/120` 或 `前 4.2%` | `percentile` |
| `gpa.score` | `{value}` | `{value, scale}` | `3.72/4.0` | `value` |
| `cet4` | `{score}` | `{score}` | `CET-4 500` | `score` |
| `cet6` | `{score}` | `{score}` | `CET-6 580` | `score` |
| `toefl` | `{score}` | `{score}` | `TOEFL 105` | `score` |
| `ielts` | `{overall}` | `{overall}` | `IELTS 7.5` | `overall` |
| `cert` | `{level}` | `{level}` | `证书 高级` | `level` |
| `comp` | `{level}` | `{level}` | `竞赛 国家级一等奖` | `level` |

## 3. 事实对象

```json
{
  "id": "d0000000-0000-4000-8000-000000000001",
  "matter_id": "a0000000-0000-4000-8000-000000000001",
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
| `matter_id` | UUID | 事实所属事项 |
| `fact_type` | string | 事实类型，Alpha 为 `gpa.rank`、`gpa.score`、`cet4`、`cet6`、`toefl`、`ielts`、`cert`、`comp` |
| `value` | object | 规范化后的 `value_json` |
| `value_text` | string | 服务端生成的展示文本 |
| `scope` | string \| null | 统计范围，最长 200 字符 |
| `valid_from` | date \| null | 值生效日期 |
| `trust_level` | string | 固定为 `self` |
| `status` | string | `confirmed` 或 `superseded` |
| `version_no` | integer | 同一用户、同一事项、同一类型内递增，从 1 开始 |
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

### 3.2 `gpa.score` 值

`gpa.score` 使用 4.0 制，请求值只包含 `value`：

```json
{
  "value": {
    "value": 3.72
  }
}
```

`value` 为 0 到 4.0 之间的数值，四舍五入保留 2 位小数。规范化后的 `value_json` 固定包含满分：

```json
{
  "value": 3.72,
  "scale": 4.0
}
```

`value_text` 为 `3.72/4.0`，`agent_value` 为 4.0 制 GPA 数值。请求中不接受 `scale` 字段；满分调整需要新增事实类型。

### 3.3 英语分数

| `fact_type` | 请求值 | 约束 | `value_text` | `agent_value` |
| :--- | :--- | :--- | :--- | :--- |
| `cet4` | `{"score": 500}` | 0—710 的整数 | `CET-4 500` | `500` |
| `cet6` | `{"score": 580}` | 0—710 的整数 | `CET-6 580` | `580` |
| `toefl` | `{"score": 105}` | 0—120 的整数 | `TOEFL 105` | `105` |
| `ielts` | `{"overall": 7.5}` | 0—9 的数值，保留 1 位小数 | `IELTS 7.5` | `7.5` |

这四个键与要求自查 `any_minimum` 规则中的替代项键一致，可直接参与英语水平条件比较。`ielts` 的 `overall` 四舍五入保留 1 位小数，展示文本至少保留 1 位小数。

### 3.4 `cert` 与 `comp` 等级

证书与竞赛使用通用等级字符串：

```json
{
  "value": {
    "level": "高级"
  }
}
```

```json
{
  "value": {
    "level": "国家级一等奖"
  }
}
```

`level` 去除首尾空白后必须为非空字符串，最长 32 字符。等级文本保持用户输入，不转换为固定枚举，以覆盖不同证书与竞赛体系。`cert` 的 `value_text` 为 `证书 {level}`，`comp` 的 `value_text` 为 `竞赛 {level}`，`agent_value` 为等级文本本身。

### 3.5 `value_hash`

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

对象键按字典序排列，缺失的可选字段使用显式 `null`，以 UTF-8 紧凑 JSON 编码。`matter_id` 属于记录归属维度，不参与 `value_hash`。

## 4. 保存事实

`PUT /api/v1/matters/{matter_id}/facts/{fact_type}`

`fact_type` 必须已注册，Alpha 接受 `gpa.rank`、`gpa.score`、`cet4`、`cet6`、`toefl`、`ielts`、`cert`、`comp`。

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

其他类型请求体：

| `fact_type` | 请求体 |
| :--- | :--- |
| `gpa.score` | `{"value": {"value": 3.72}}` |
| `cet4` | `{"value": {"score": 500}}` |
| `cet6` | `{"value": {"score": 580}}` |
| `toefl` | `{"value": {"score": 105}}` |
| `ielts` | `{"value": {"overall": 7.5}}` |
| `cert` | `{"value": {"level": "高级"}}` |
| `comp` | `{"value": {"level": "国家级一等奖"}}` |

响应 `200`：

```json
{
  "fact": {
    "id": "d0000000-0000-4000-8000-000000000001",
    "matter_id": "a0000000-0000-4000-8000-000000000001",
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

`created` 表示本次请求是否写入新版本。值、`scope`、`valid_from` 全部相同且当前事项的当前版本未变化时，返回当前事实，`created` 为 `false`，不递增版本号。`affected_plans` 仍按当前事项状态重新计算。

保存新值时：

1. 校验事项属于当前工作区。
2. 在事务内获取 `(owner_id, matter_id, fact_type)` 级 advisory lock。
3. 读取当前事项的 `confirmed` 版本。
4. 新内容与当前内容一致时直接返回。
5. 内容不同时写入 `version_no = 当前事项最大版本 + 1` 的新记录。
6. 旧 `confirmed` 版本写为 `superseded`，并写入 `superseded_at`。
7. 同一事务提交新版本和旧版本状态。

新版本写入后，旧版本仍可通过读取接口的 `versions` 查看。接口不提供删除历史版本的操作。

## 5. 读取事实

### 5.1 读取当前事实列表

`GET /api/v1/matters/{matter_id}/facts`

```json
{
  "facts": [
    {
      "id": "d0000000-0000-4000-8000-000000000001",
      "matter_id": "a0000000-0000-4000-8000-000000000001",
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

只返回当前事项的当前 `confirmed` 版本，按 `fact_type` 字典序排列。没有当前事实时返回空数组。

### 5.2 读取单类型事实与版本

`GET /api/v1/matters/{matter_id}/facts/{fact_type}`

```json
{
  "fact": {
    "id": "d0000000-0000-4000-8000-000000000002",
    "matter_id": "a0000000-0000-4000-8000-000000000001",
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
      "matter_id": "a0000000-0000-4000-8000-000000000001",
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
      "matter_id": "a0000000-0000-4000-8000-000000000001",
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

`fact` 为当前事项的当前确认版本；没有当前事实时为 `null`。`versions` 按 `version_no` 倒序排列，包含当前事项的当前版本与全部历史版本。

## 6. 版本、幂等与并发

- `version_no` 在同一 `(owner_id, matter_id, fact_type)` 内递增，初始为 1。
- 同一事项同一类型同时只允许一条 `confirmed` 记录；旧版本写入 `superseded` 后不再参与当前事实读取。
- 保存请求在事务内获取 `owner_id + matter_id + fact_type` 级 advisory lock，避免并发请求写入重复版本号。
- 幂等比较使用规范化后的 `value_json`、`scope` 和 `valid_from`；三者全部相同即视为同一次保存。
- `value_hash` 参与当前事项候选计划的依据指纹，版本号变化或值内容变化都会改变指纹。
- `scope` 与 `valid_from` 变化会产生新版本，即使 `value` 相同。
- 不同事项的同类型事实使用独立版本序列；修改 A 事项不会改变 B 事项的版本号。

## 7. 受影响计划与旧候选失效

### 7.1 相关事实键

计划的相关事实键由以下来源合并，去重后按字典序排列：

- 当前事项下未拒绝要求的 `field_key`；
- 当前事项的 `requirement_self_check.missing_fields`。

已注册且有当前确认版本的事实键写入事实条目；已注册但无当前版本的事实键写入显式空占位。未注册的事实键保留在运行级 `confirmed_facts` 中，并在依据输入中保留显式空占位。

### 7.2 保存后返回的受影响计划

保存事实后，只查询该 `matter_id` 下状态为 `pending` 的候选计划。满足任一条件即列入 `affected_plans`：

- `basis_input.confirmed_facts` 中存在该 `fact_type` 的条目，且条目版本与当前事项的当前确认版本不同；空占位条目按 `version_no = null` 参与比较。
- `basis_input.confirmed_facts` 中缺少该 `fact_type` 的条目，且计划相关事实键包含该 `fact_type`。

`affected_plans` 每项包含：

| 字段 | 说明 |
| :--- | :--- |
| `plan_id` | 候选计划标识 |
| `matter_id` | 事项标识，等于请求路径中的 `matter_id` |
| `version_no` | 计划版本号 |
| `stored_version_no` | 计划记录的事实版本；缺少条目或空占位时为 `null` |

该查询只返回列表，不修改计划状态、`expired_at`、决定或任务。其他事项的候选计划不进入结果。

### 7.3 确认时失效

确认候选计划时，服务端在锁定事务内重新采集当前事项的依据输入并计算指纹。事实版本变化导致指纹不一致时：

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

没有当前确认版本时，`current_version_no` 和 `current_fact_id` 为 `null`。依据指纹因其他输入变化而不一致时，`stale_facts` 为空数组。确认校验只比较当前事项的事实版本。

### 7.4 计划读取的依据状态

候选计划列表、详情和事项的 `latest_plan` 返回 `basis_status` 与 `stale_facts`。

| `basis_status` | 条件 |
| :--- | :--- |
| `current` | 计划为 `pending`，存在相关事实键，且所有事实条目与当前事项的当前确认版本一致 |
| `stale` | 计划为 `pending`，且至少一个事实条目与当前事项的当前确认版本不一致 |
| `not_applicable` | 计划不是 `pending`，或计划没有相关事实键 |

`stale_facts` 仅在 `stale` 时非空，条目结构与确认失效响应一致。计划读取只使用计划所属事项的事实。

## 8. Agent 运行

`POST /api/v1/matters/{matter_id}/agent-runs` 继续接受可选的 `confirmed_facts`，用于未进入事实档案的运行级字段。

- 已注册事实类型由后端从当前事项的 `core.fact` 记录读取当前确认版本；请求中的 `confirmed_facts` 出现已注册类型时返回 `422 managed_fact_type`。
- 未注册键仍作为运行级事实参与自查，不形成事实版本，不进入依据指纹。
- 后端按当前事项的相关事实键读取已注册类型的当前确认版本，并将事实条目写入候选计划的 `basis_input`。
- 运行开始时记录当前事项所用事实版本。候选持久化前重新读取同一事项的当前版本；版本已变化时运行失败，`error.code` 为 `VERSION_CONFLICT`，不写入依据已过时的候选计划。
- 其他事项的同类事实不参与读取、版本校验或依据指纹。

规则评估使用渲染器提供的 `agent_value`。`gpa.rank` 使用 `percentile`，数值越小表示排名越靠前；`gpa.score` 使用 4.0 制 GPA 数值；`cet4`、`cet6`、`toefl` 使用整数分数；`ielts` 使用总分；`cert` 与 `comp` 使用等级文本。没有确认事实时，自查结论为 `missing_info`，`missing_fields` 包含对应事实键，缺口为 `missing_personal_fact`。

## 9. 错误

| HTTP | `code` | 说明 |
| :--- | :--- | :--- |
| 404 | `matter_not_found` | 事项不存在或不属于当前工作区；保存与读取均拒绝 |
| 422 | `unsupported_fact_type` | 路径事实类型未注册；`details.supported_fact_types` 列出当前类型 |
| 422 | `invalid_fact_value` | 事实值写法或范围不合法；`details.issues` 列出 `path`、`code`、`message` |
| 422 | `managed_fact_type` | Agent 运行的 `confirmed_facts` 包含已注册事实类型；`details.fact_types` 列出冲突键 |
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

迁移 `0012_core_fact_matter.sql` 在 `0011` 的基础上增加事项归属：

```sql
ALTER TABLE core.fact ADD COLUMN matter_id uuid;

ALTER TABLE core.fact
    ADD CONSTRAINT fk_fact_matter FOREIGN KEY (matter_id)
    REFERENCES core.matter (id) ON DELETE CASCADE;

ALTER TABLE core.fact DROP CONSTRAINT uq_fact_type_version;
ALTER TABLE core.fact
    ADD CONSTRAINT uq_fact_type_version
    UNIQUE (owner_id, matter_id, fact_type, version_no);

CREATE UNIQUE INDEX uq_fact_current
    ON core.fact (owner_id, matter_id, fact_type)
    WHERE confirm_status = 'confirmed' AND matter_id IS NOT NULL;

CREATE INDEX ix_fact_owner
    ON core.fact (owner_id, matter_id, fact_type);
```

最终列结构：

| 字段 | 类型 | 说明 |
| :--- | :--- | :--- |
| `id` | uuid | 版本标识 |
| `owner_id` | uuid | 事实所属用户 |
| `matter_id` | uuid | 事实所属事项；未归属历史为 `null` |
| `fact_type` | varchar(48) | 事实类型 |
| `value_text` | text | 服务端展示文本 |
| `value_json` | jsonb | 规范化值对象 |
| `value_hash` | char(64) | 规范化内容 SHA-256 |
| `scope` | varchar(200) | 统计范围，不参与事实身份 |
| `valid_from` | date | 值生效日期，不参与事实身份 |
| `trust_level` | varchar(16) | 固定为 `self` |
| `confirm_status` | fact_status | `confirmed` 或 `superseded` |
| `version_no` | integer | 同用户、同事项、同类型内递增 |
| `confirmed_at` | timestamptz | 确认时间 |
| `superseded_at` | timestamptz | 替代时间，仅 `superseded` 非空 |
| `created_at` | timestamptz | 版本创建时间 |

`uq_fact_current` 是事项内单值当前记录的数据库保证。`uq_fact_type_version` 保证同一用户、同一事项、同一类型的版本号唯一。

行级安全策略要求事实所属事项位于当前工作区，且事实所有者等于工作区所有者：

```sql
CREATE POLICY fact_by_matter ON core.fact
    USING (EXISTS (
        SELECT 1
        FROM core.matter m
        JOIN core.workspace w ON w.id = m.workspace_id
        WHERE m.id = fact.matter_id
          AND m.workspace_id = NULLIF(current_setting('app.current_workspace_id', true), '')::uuid
          AND w.owner_id = fact.owner_id
    ));
```

接口只写入 `confirmed` 与 `superseded`。`draft` 和 `revoked` 保留在 schema 中，当前接口不提供对应操作。

## 11. 验收场景

| 编号 | 场景 | 预期 |
| :--- | :--- | :--- |
| F-01 | 首次保存名次 | 返回版本 1，`created` 为 `true`，`value_text` 为 `5/120`，`matter_id` 与路径一致 |
| F-02 | 首次保存百分位 | 返回版本 1，`value_text` 为 `前 4.2%`，`percentile` 为 4.2 |
| F-03 | 保存相同值、范围和生效日 | 不新增版本，`created` 为 `false` |
| F-04 | 保存新值 | 当前事项内版本号递增，旧版本转为 `superseded` |
| F-05 | 读取当前事实 | 只返回当前事项的 `confirmed` 版本 |
| F-06 | 读取版本历史 | 按 `version_no` 倒序返回当前事项的当前与历史版本 |
| F-07 | 保存后查询受影响计划 | 只返回当前事项中记录旧版本或缺少事实条目的 `pending` 计划 |
| F-08 | 事实版本变化后确认计划 | 当前事项计划转为 `expired`，返回 `409 basis_changed` |
| F-09 | 读取计划列表、详情与事项最新计划 | 返回当前事项的 `basis_status` 与 `stale_facts` |
| F-10 | A 事项保存排名后读取 B 事项 | B 无当前事实，输出为空 |
| F-11 | 修改 A 事项事实 | B 的事实的版本、依据状态与确认结果不变 |
| F-12 | 应用重启后读取 A 事项 | 返回重启前保存的事实标识、版本与值 |
| F-13 | 无权限事项保存或读取 | 返回 `404 matter_not_found` |
| F-14 | 未归属历史记录与事项读取 | 历史记录不返回，不参与 Agent 运行；事项内重新保存从版本 1 开始 |
| F-15 | Agent 运行的 `confirmed_facts` 含已注册类型 | 返回 `422 managed_fact_type`，不创建运行 |
| F-16 | Agent 运行使用当前事项事实 | 候选依据记录当前事项的版本，`gpa.rank` 使用 `percentile` |
| F-17 | 运行期间当前事项事实版本变化 | 运行失败为 `VERSION_CONFLICT`，不写入旧依据候选 |
| F-18 | 运行期间其他事项事实变化 | 当前运行不受影响 |
| F-19 | 保存 GPA | 版本 1，`value` 包含 `value` 与 `scale`，`value_text` 为 `3.72/4.0` |
| F-20 | 保存英语四项 | 各自版本 1，展示文本与 `agent_value` 按类型生成 |
| F-21 | GPA 超过 4.0 | 返回 `422 invalid_fact_value`，`details.issues` 定位到 `value.value` |
| F-22 | 英语分数超出范围 | 返回 `422 invalid_fact_value`，`details.issues` 定位到 `value.score` 或 `value.overall` |
| F-23 | 保存证书与竞赛等级 | 版本 1，`value_text` 为 `证书 高级` 或 `竞赛 国家级一等奖` |
| F-24 | 等级为空或超过 32 字符 | 返回 `422 invalid_fact_value`，`details.issues` 定位到 `value.level` |
