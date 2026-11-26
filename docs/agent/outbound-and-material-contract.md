# OfferPilot Agent 出站字段、来源筛选与材料草拟授权契约

本文档定义 Beta 阶段 Agent 业务层（#60）与模型适配层（#73）之间的接口契约，涵盖 P0 推免分析的出站字段白名单、公开来源片段筛选与去重、响应与引文校验、错误码映射，以及 P0/P1 个人事实与材料草拟授权边界。

---

## 一、P0 出站字段白名单与公开来源片段结构

### 1.1 全局传输边界

P0 阶段的所有外部模型调用仅传输当前运行的事项目标、白名单公开范围字段及经筛选去重后的公开来源信息。个人事实（如成绩排名、英语分数、获奖明细）、个人材料与用户导入件仅留在个人工作区内参与本地规则自查，不进入模型出站请求。

出站前需通过 `ToolGateway` 校验当前用户的 `active` 传输同意记录（参见 [模型传输同意接口契约](../backend/model-transfer-consent.md)），用途与字段类别映射如下：

| 工具名 | 传输用途 (`purpose`) | 必需字段类别 (`field_categories`) |
| --- | --- | --- |
| `extract_requirements` | `requirement_extraction` | `matter_goal`、`public_sources` |
| `generate_candidate_plan` | `candidate_planning` | `matter_goal`、`public_scope`、`public_sources` |
| `persist_candidate_artifacts` | `candidate_planning` | `matter_goal`、`public_scope`、`public_sources` |

### 1.2 要求抽取入参 (`build_extraction_input`)

| 字段 | 类型与约束 | 说明 |
| --- | --- | --- |
| `goal` | `str`，去首尾空白且截断至 `200` 字符（`sanitize_matter_goal`） | 当前事项分析目标 |
| `strategy_version` | `str` | 提示与抽取策略版本 |
| `sources` | `list[dict]`，经 `deduplicate_sources` 去重 | 按 `source_version_id` 与 `(source_id, content_hash)` 去重 |
| `sources[*].source_version_id` | `str` | 来源版本或快照唯一标识 |
| `sources[*].source_id` | `str \| null` | 来源主体标识 |
| `sources[*].snapshot_id` | `str \| null` | 来源快照标识 |
| `sources[*].title` | `str` | 官方通知标题 |
| `sources[*].publisher` | `str` | 官方发布机构 |
| `sources[*].year` | `int \| null` | 适用年度 |
| `sources[*].scope` | `str \| null` | 适用范围描述 |
| `sources[*].content` | `str` | 仅当筛选后 `fragments` 为空时保留正文；否则置为 `""` |
| `sources[*].missing_attachments` | `list[str]` | 缺失附件列表 |
| `sources[*].fragments` | `list[dict]`，经 `filter_and_deduplicate_fragments` 处理 | 每项包含 `locator_kind`、`locator`、`quote` 原文字段 |

### 1.3 候选规划入参 (`build_planning_input`)

| 字段 | 类型与约束 | 说明 |
| --- | --- | --- |
| `goal` | `str`，去首尾空白且截断至 `200` 字符 | 当前事项分析目标 |
| `scope_year` | `int \| null` | 顶层适用年度 |
| `scope_attrs` | `dict`，经 `sanitize_public_scope_attrs` 过滤 | 仅允许 `PUBLIC_SCOPE_ALLOWLIST` 内的 10 个键，字符串截断至 `100` 字符，保留 `int` / `bool` 值 |
| `strategy_version` | `str` | 规划策略版本 |
| `sources` | `list[dict]`，经 `deduplicate_sources` 与片段筛选去重 | 仅包含 `source_version_id`、`title`、`publisher`、`year`、`scope` 及 `fragments[*].{locator_kind, locator}`，省略 `content` 与 `quote` |
| `evaluations` | `list[dict]` | 本地四态自查结果摘要，仅包含 `requirement_id`、`title`、`status`、`basis`、`scope`、`computed_deadline`，省略 `reason` 与 `missing_fields` |

`PUBLIC_SCOPE_ALLOWLIST` 允许键固定为：
`school`、`college`、`department`、`program`、`major`、`track`、`category`、`degree`、`intake_year`、`region`。

### 1.4 公开来源筛选与去重不变量 (`source_filter.py`)

`deduplicate_sources` 与 `filter_and_deduplicate_fragments` 遵循以下确定性不变量：

1. **原文定位不改写**：保留片段的 `locator_kind`、`locator` 与 `quote` 保持原始解析文本完全不变，保证模型输出的引用可通过 `_validate_and_enrich_citations` 的严格回溯校验。
2. **门户噪音剔除**：移除空白与零宽字符片段、站点导航栏串联项、面包屑（`当前位置：` 及短路径末项）、`正文` 标识、`上一篇 / 下一篇` 及页脚版权/地址邮编行；保留标题（`section`）、表格行（`table_row`）及正文政策条款与附件条目。
3. **跨文档与文档内去重**：跨来源按 `source_version_id` 与非空 `(source_id, content_hash)` 去重；文档内按 `(locator_kind, 归一化 locator)` 及归一化 `quote` 去重，保持原始片段顺序。
4. **必需定位符保护与兜底**：规划阶段在 `evaluations[*].basis` 中已引用到的 `(locator_kind, locator)` 始终保留；若输入来源本身非空且过滤后为空，自动回退为去重后的非空片段列表，避免空输入送入模型。

---

## 二、结构化响应、引文回溯与领域校验约定

1. **模型响应结构**：
   - 抽取阶段输出 `RequirementExtractionPayload`（`requirements`、`gaps`、`scope_summary`）。
   - 规划阶段输出 `CandidatePlanDraftPayload`（`tasks`、`gaps`、`scope_summary`）。
2. **引文回溯校验 (`_validate_and_enrich_citations`)**：
   - 每条要求与候选任务必须至少携带一条 `basis` 引用；
   - `source_version_id` 必须属于本次输入来源，`source_id` / `snapshot_id` 须与真实来源记录一致；
   - 当来源存在 `fragments` 时，`basis[*].locator`（空白归一化后）与 `locator_kind` 必须精确匹配原片段，提供 `excerpt` 时必须为对应 `quote` 的连续原文字串且非空，未提供 `excerpt` 时自动回填对应 `quote`。
3. **四态自查与缺口表达 (`validators.py`)**：
   - 规则结论固定为四态：`按现有信息符合`、`按现有信息不符合`、`待补充信息`、`待用户核对`。
   - 缺少上位文件、附件、来源冲突或规则参数不足时，保持 `待用户核对` 并在 `gaps` 中显式记录，不生成确定性资格结论。
4. **候选任务依赖与编号冲突校验**：
   - `validate_candidate_plan` 校验工作区版本一致、`task_id` 唯一、经 `build_client_item_id_map` 规范化并截断至 `80` 字符后的 `client_item_id` 非空且无冲突、`depends_on` 仅引用同计划内已存在任务且依赖图无环、`suggested_date` 不晚于官方截止日期。
   - Agent 运行仅保存 `WAITING_CONFIRMATION` 状态的待确认候选计划，必须在用户显式确认后才创建正式任务。

---

## 三、错误码映射约定

模型适配器（`backend/model_adapter.py`）负责 HTTP 调用、超时控制与响应 JSON 校验；Agent 层（`StructuredModelAdapter._invoke_model`）统一映射如下，失败时显式返回错误状态，不写入或伪造成功候选：

| 适配器异常代码 / 类型 | Agent 错误码 (`AgentErrorCode`) | 语义与处理 |
| --- | --- | --- |
| `CONFIG_ERROR` | `MODEL_ERROR` | 模型地址、模型名、API Key 或超时配置非法 |
| `SERVICE_ERROR` | `MODEL_ERROR` | 上游模型服务返回非 2xx 或通信异常 |
| `TIMEOUT` / `TimeoutError` | `TIMEOUT` | 单次请求超过配置超时（默认 180 秒，适配器不自动重试） |
| `INVALID_RESPONSE` / `ValidationError` | `VALIDATION_FAILED` | 返回非完整 JSON、字段结构不匹配或引文回溯校验失败 |

---

## 四、P0 与 P1 个人事实及材料草拟授权边界

| 能力阶段 | 外发内容范围 | 授权与校验要求 |
| --- | --- | --- |
| **P0 推免分析** | 事项目标（<= 200 字）、白名单 `public_scope` + `scope_year`、筛选去重后的公开来源片段与定位 | 沿用用户级全局公开资料传输同意；个人事实与私有附件留在工作区本地自查，严禁出站 |
| **P1 材料草拟（待集成）** | 仅限用户主动选取且明确授权的已确认事实条目、目标要求摘要与草拟指令 | 1. 须在用户知悉发送内容与用途后主动发起生成；<br>2. 服务端将本次明示同意绑定至传输请求，并逐条核对所选事实及其版本均在有效授权内；<br>3. 未发生授权范围、用途或事实版本变化时，相同范围的事实授权可跨对话复用；<br>4. 普通对话与后台运行不得据此自动发送个人事实；<br>5. 授权撤回、范围变更或事实版本更新时立即阻断发送并要求重新授权；<br>6. 未知事实编号、缺项编造或格式无效草稿直接拒绝，用户保留编辑、接受与拒绝决定权 |
