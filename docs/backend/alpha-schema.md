# Alpha 数据库 Schema 与迁移

| 项目 | 内容 |
| :--- | :--- |
| 负责人 | 佘博海 |
| 分支 | `feat/matter-task-schema` |
| 契约依据 | `docs/development/alpha-scope-contract.md` |
| 数据库 | PostgreSQL 16 及以上 |

## 1. 范围

本文描述 Alpha 主流程的首版物理 schema：

> 创建个人事项 → 获取公开来源 → 提取要求并保留出处 → 生成候选计划 →
> 用户确认或拒绝 → 确认后创建个人任务 → 读取任务

结构覆盖事项、模板版本、来源与快照、证据、要求、候选计划、计划项、计划项来源、
计划决定、个人事实和个人任务。阶段、四态评估、收件箱、审计和材料模块在后续迁移中补充。

## 2. 表与视图

### 2.1 业务表（19 张）

| 表 | 用途 | 关键约束 |
| :--- | :--- | :--- |
| `core.app_user` | 用户 | 邮箱唯一；首版账号类型为 `applicant` |
| `core.workspace` | 个人工作区 | 与用户 1:1 |
| `core.matter_type` | 事项类型 | `type_code` 唯一，内置 `pre_recommend`、`competition` |
| `core.template_version` | 模板版本 | 类型与版本号唯一；事项引用具体版本 |
| `core.matter` | 个人事项 | 模板版本必填；年度 2020—2100；归档时间与状态一致 |
| `core.matter_source` | 事项来源关联 | 来源读取或登记成功后立即关联；事项与快照唯一 |
| `core.agent_run` | Agent 运行 | 状态与检查点持久化；重启前未完成运行标记为中断 |
| `ops.source` | 公开来源 | URL 唯一；生命周期与自动检查状态分列 |
| `ops.snapshot` | 来源快照 | 同源版本唯一；同源内容哈希唯一；只增不改 |
| `ops.evidence` | 要求证据 | 四元组唯一；来源、快照、要求三者一致 |
| `core.requirement` | 候选要求 | 必须绑定快照；`checked` 与检查时间一致 |
| `core.requirement_self_check` | 要求自查结果 | 每个要求至多一条；四态结论、原因、缺失信息、缺口与 `extract_status` 分开保存 |
| `core.fact` | 个人事实版本 | 同用户同事项同类型只有一条 `confirmed`；版本号在事项内唯一且递增；状态与时间一致 |
| `core.model_transfer_consent` | 模型传输同意 | 同用户同事项至多一条 `active`；版本号在事项内唯一；状态与撤回时间一致 |
| `core.candidate_plan` | 候选计划 | 同事项版本唯一；`op_id` 唯一；依据哈希与完整输入持久化 |
| `core.candidate_plan_item` | 候选计划项 | 同计划顺序唯一；依赖项必须在同一计划内 |
| `core.candidate_plan_item_source` | 计划项来源定位 | 计划项、快照、定位唯一；来源与快照一致 |
| `core.candidate_plan_decision` | 计划终态决定 | 每个计划至多一条；`operation_id` 唯一 |
| `core.task` | 个人任务 | 仅确认后创建；计划项唯一；完成必须有非空证据 |

`ops.schema_version` 记录迁移版本、校验和、应用时间与执行耗时。

### 2.2 视图（3 个）

| 视图 | 内容 |
| :--- | :--- |
| `core.v_matter_overview` | 事项、类型、任务完成数、最新计划 |
| `core.v_plan_detail` | 计划、条目数、要求回溯数、来源定位数 |
| `core.v_task_list` | 任务、事项目标、期限、计划状态 |

视图使用 `security_invoker = true`，行级策略作用于底层表。

### 2.3 关系

```mermaid
erDiagram
    app_user ||--|| workspace : owns
    app_user ||--o{ fact : owns
    workspace ||--o{ matter : contains
    matter_type ||--o{ template_version : versions
    matter_type ||--o{ matter : classifies
    template_version ||--o{ matter : instantiates
    matter ||--o{ requirement : extracts
    matter ||--o{ candidate_plan : generates
    matter ||--o{ task : has
    matter ||--o{ fact : scopes
    source ||--o{ snapshot : versions
    snapshot ||--o{ requirement : anchors
    requirement ||--o{ evidence : cited_by
    candidate_plan ||--o{ candidate_plan_item : contains
    candidate_plan ||--o{ candidate_plan_decision : decides
    candidate_plan_item ||--o{ candidate_plan_item_source : cites
    candidate_plan_item ||--o{ task : materializes
```

归属链从用户开始，经工作区、事项、计划到任务：

- `app_user.id` → `workspace.owner_id`
- `app_user.id` → `fact.owner_id`
- `matter.id` → `fact.matter_id`
- `workspace.id` → `matter.workspace_id`
- `matter.id` → `requirement.matter_id`
- `matter.id` → `candidate_plan.matter_id`
- `candidate_plan.id` → `candidate_plan_item.plan_id`
- `candidate_plan_item.id` → `candidate_plan_item_source.plan_item_id`
- `candidate_plan.id` → `candidate_plan_decision.plan_id`
- `candidate_plan_item.id` → `task.plan_item_id`

## 3. 关键字段

### 3.1 候选计划

| 字段 | 类型 | 说明 |
| :--- | :--- | :--- |
| `basis_version` | char(64) | 规范化依据输入的 SHA-256 |
| `basis_input` | jsonb | 生成时的完整规范化输入，确认时重算比对 |
| `status` | plan_status | `draft`、`pending`、`confirmed`、`rejected`、`expired` |
| `confirmed_at` | timestamptz | 仅 `confirmed` 非空 |
| `expired_at` | timestamptz | 仅 `expired` 非空 |
| `op_id` | uuid | 确认操作的幂等键；拒绝保持为空 |

### 3.2 候选计划项

| 字段 | 类型 | 说明 |
| :--- | :--- | :--- |
| `obligation_nature` | obligation_nature | `required`、`advised`、`optional`、`to_verify` |
| `official_deadline_date` | date | 来源明确给出的日期 |
| `official_deadline_at` | timestamptz | 来源给出具体时刻时填写 |
| `suggested_date` | date | 个人建议准备日 |
| `depends_on_item_ids` | uuid[] | 同一计划内的前置条目 |
| `evidence_required` | boolean | 完成后是否必须提供证据 |

计划项只能在其计划为 `draft` 时写入；计划进入 `pending` 后条目与来源关联冻结。

### 3.3 计划项来源

`plan_item_id`、`source_id`、`snapshot_id`、`locator_kind`、`locator`、`quote`。
唯一键为 `(plan_item_id, snapshot_id, locator)`；触发器校验 `source_id` 与快照的归属一致。

### 3.4 计划决定

`plan_id`、`decision`、`decided_by`、`decided_at`、`operation_id`。
`decision` 取值 `confirmed` 或 `rejected`；`plan_id` 与 `operation_id` 均唯一。
确认决定要求计划状态为 `confirmed` 且 `op_id` 与 `operation_id` 一致；
拒绝决定要求计划状态为 `rejected` 且 `op_id` 为空。决定记录写入后不可修改或删除。

### 3.5 任务

`task` 在计划项字段的基础上增加 `executor_id`、`due_at`、`status`、`completion_evidence`、
`depends_on`。`plan_id` 与 `plan_item_id` 必填，`plan_item_id` 唯一，阻止同一候选条目生成重复任务。
任务依赖在事务提交时校验，必须指向同一事项内已存在的任务。

### 3.6 个人事实

| 字段 | 类型 | 说明 |
| :--- | :--- | :--- |
| `owner_id` | uuid | 事实所属用户 |
| `matter_id` | uuid | 事实所属事项；未归属历史为 `null` |
| `fact_type` | varchar(48) | 事实类型；Alpha 为 `gpa.rank`、`gpa.score`、`cet4`、`cet6`、`toefl`、`ielts`、`cert`、`comp` |
| `value_text` | text | 服务端生成的展示文本 |
| `value_json` | jsonb | 按类型规范化的值对象 |
| `value_hash` | char(64) | 类型、范围、生效日、值与展示文本的规范化 SHA-256 |
| `scope` | varchar(200) | 适用范围；不参与事实身份 |
| `valid_from` | date | 值生效日期；不参与事实身份 |
| `trust_level` | varchar(16) | 固定为 `self` |
| `confirm_status` | fact_status | 接口写入 `confirmed` 与 `superseded` |
| `version_no` | integer | 同用户、同事项、同类型内递增，从 1 开始 |
| `confirmed_at` | timestamptz | `confirmed` 与 `superseded` 非空 |
| `superseded_at` | timestamptz | 仅 `superseded` 非空 |

`uq_fact_current` 是 `(owner_id, matter_id, fact_type)` 上的部分唯一索引，条件为
`confirm_status = 'confirmed'` 且 `matter_id IS NOT NULL`，保证每个用户、每个事项、每种事实只有一条当前确认记录。
`uq_fact_type_version` 保证同一用户、同一事项、同一类型的版本号唯一。
迁移 `0012` 之前的用户级记录保留 `matter_id = NULL`，属于未归属历史，不参与任何事项读取与 Agent 运行。

## 4. 状态与时间

| 对象 | 允许值 | 数据库保证 |
| :--- | :--- | :--- |
| 事项 | `draft`、`active`、`paused`、`archived`、`cancelled` | 枚举；归档时间与状态一致 |
| 来源 | `active`、`withdrawn`、`invalid` | 枚举；与自动检查状态分列 |
| 要求 | `extracted`、`checked`、`to_review`、`rejected` | `checked` 与 `checked_at` 同步 |
| 候选计划 | `draft`、`pending`、`confirmed`、`rejected`、`expired` | `confirmed_at` 仅确认；`expired_at` 仅过期 |
| 任务 | `pending`、`ready`、`in_progress`、`blocked`、`done`、`cancelled` | `done` 与完成证据同步 |
| 个人事实 | `draft`、`confirmed`、`superseded`、`revoked` | 当前确认记录唯一；`confirmed`/`superseded` 与确认时间同步；`superseded` 与替代时间同步 |
| 模型传输同意 | `active`、`revoked` | 同事项至多一条 `active`；`revoked` 与撤回时间同步 |

期限精度：

- `official_deadline_date` 保存日期型官方期限；
- `official_deadline_at` 保存带时刻的官方期限；
- `suggested_date` 保存个人建议准备日；
- `due_at` 保存任务执行时刻，仅在有确定时刻时填写。

## 5. 行级安全

启用 RLS 的表：`matter`、`requirement`、`candidate_plan`、`candidate_plan_item`、
`candidate_plan_item_source`、`candidate_plan_decision`、`task`、`requirement_self_check`、
`matter_source`、`agent_run`、`fact`、`model_transfer_consent`。

策略条件：

```sql
workspace_id = current_setting('app.current_workspace_id', true)::uuid
```

`fact` 按事项归属过滤，条件为事项位于当前工作区，且事实所有者等于工作区所有者：

```sql
EXISTS (
    SELECT 1
    FROM core.matter m
    JOIN core.workspace w ON w.id = m.workspace_id
    WHERE m.id = fact.matter_id
      AND m.workspace_id = current_setting('app.current_workspace_id', true)::uuid
      AND w.owner_id = fact.owner_id
)
```

`model_transfer_consent` 按事项归属过滤，同时核对记录中的所有者与工作区：

```sql
workspace_id = current_setting('app.current_workspace_id', true)::uuid
AND EXISTS (
    SELECT 1
    FROM core.matter m
    JOIN core.workspace w ON w.id = m.workspace_id
    WHERE m.id = model_transfer_consent.matter_id
      AND m.workspace_id = model_transfer_consent.workspace_id
      AND w.owner_id = model_transfer_consent.owner_id
)
```

会话变量未设置时策略不匹配任何行。应用使用非所有者角色连接；表所有者绕过 RLS。
`source`、`snapshot`、`evidence` 为共享层。应用角色可登记来源、追加快照与证据，
快照与证据写入后不可修改；账户表不授予 `password_hash`。

Alpha 没有登录与账户体系，运行范围为单用户本地演示。RLS 是开发期防误查的纵深防御，
共享应用角色仍可设置会话变量，不能独立承担多租户隔离。多账户上线前必须由认证层
签发工作区标识，并在服务端校验事项归属。

## 6. 迁移与初始化

### 6.1 迁移文件

| 编号 | 内容 |
| :--- | :--- |
| `0001` | `core`、`ops` 模式与 8 个枚举 |
| `0002` | 用户、工作区、事项类型、模板版本、事项 |
| `0003` | 来源、快照 |
| `0004` | 要求、证据 |
| `0005` | 候选计划、计划项、计划决定、计划项来源、任务 |
| `0006` | 3 个查询视图 |
| `0007` | 事项聚合的 RLS 策略 |
| `0008` | 计划决定与计划项来源的 RLS 策略 |
| `0009` | 要求自查结果表及其 RLS 策略 |
| `0010` | 事项来源关联、Agent 运行检查点及其 RLS 策略 |
| `0011` | 个人事实表、当前版本唯一索引及其 RLS 策略 |
| `0012` | 个人事实事项归属、事项内版本与当前记录唯一索引、RLS 策略调整 |
| `0013` | 模型传输同意表、活动记录唯一索引及其 RLS 策略 |
| `0014` | 模型传输同意表的应用角色授权 |

### 6.2 执行规则

- 迁移文件按编号执行，只追加，不修改已执行文件。
- 每个文件单独事务；成功后写入 `ops.schema_version`，包含 SHA-256 与执行耗时。
- 重复执行时跳过已应用版本；校验和不一致时退出码 2。
- 迁移在创建业务表后向已存在的 `offerpilot_app` 授予所需表权限；`db/dev/roles.sql` 只负责首次创建角色与基础授权。
- 已部署环境执行 `db/migrate.py migrate` 即可获得新表权限，不需要在迁移后重跑角色脚本。
- 数据库存在当前目录没有的版本时退出码 2。
- migrations 目录为空或不存在时退出码 2。
- `status` 发现校验和漂移或缺失文件时退出码 1。
- `migrate --dry-run` 不创建任何数据库对象。
- 迁移期间持有 advisory lock，避免并发执行。
- 种子脚本使用 `ON CONFLICT`，可重复执行。

### 6.3 从空库初始化

```bash
cd backend
uv sync
export DATABASE_URL='postgresql://postgres:postgres@127.0.0.1:5432/offerpilot'
uv run python db/migrate.py migrate
uv run python db/migrate.py seed
uv run python db/migrate.py status
```

Docker：

```bash
cd backend/db
docker compose up -d --wait
```

本机 PostgreSQL：

```bash
createdb offerpilot
export DATABASE_URL='postgresql://postgres@127.0.0.1:5432/offerpilot'
```

演示数据：

```bash
cd backend
uv run python db/migrate.py seed --demo
```

运行环境：Python 3.13。

## 7. 验证

环境：PostgreSQL 16.4、Python 3.13、psycopg 3.3.9。

```text
空库迁移：14 个全部成功
重复迁移：14 个全部跳过
参考数据与演示数据：成功
表数量：20（19 张业务表 + schema_version）
视图数量：3
集成测试：14 个通过
```

覆盖场景：事项持久化与重读、约束拒绝、来源与证据链、计划项来源、
拒绝不创建任务、确认创建任务、`op_id` 重放、同一计划项任务唯一、
未确认计划禁止写任务、完成证据、跨工作区 RLS、级联删除、
计划状态时间约束、计划项冻结与依赖、快照不可变、决定与操作者校验、
事实当前版本唯一、版本号唯一、状态时间约束与事实 RLS。

运行命令：

```bash
cd backend
uv sync
export PGTEST_ADMIN_DSN='postgresql://postgres@127.0.0.1:5432/postgres'
uv run python db/tests/test_alpha_schema.py -v
```

## 8. 已知限制

1. 完整登录与账户体系不在 Alpha 范围；运行范围为单用户本地演示，数据边界通过事项关联和服务端校验落实。
2. RLS 作为纵深防御，不独立承担多租户隔离；共享应用角色仍可设置会话变量。
3. 不提供 down 迁移；回滚使用迁移前快照或新增反向迁移。
4. 阶段、四态评估、来源缺口、收件箱、审计日志、个人材料在后续迁移中补充。
