# 个人事项工作区集成约定

本说明覆盖个人事项工作区及其业务模块接入。事项与分析接口对照 [#41 后端契约（`16a647a`）](https://github.com/LotteryCamp/OfferPilot/blob/16a647a5ff61fee327a262f40f7c0435a81a86bc/docs/backend/api.md)，排名事实与候选依据隔离依赖截至 `0012_core_fact_matter.sql` 的数据库迁移。基础工作区由 [#43](https://github.com/LotteryCamp/OfferPilot/pull/43) 交付。

## 责任与文件边界

| 范围                                             | 维护边界                                                                                                      |
| ------------------------------------------------ | ------------------------------------------------------------------------------------------------------------- |
| `frontend/src/app`、`router`、`modules/matters`  | 陈常群负责入口、导航、事项页面及模块集成，见 [#31](https://github.com/LotteryCamp/OfferPilot/issues/31)       |
| `frontend/src/shared/ui/StatePanel.vue`          | 共用的加载、空内容、错误和未接通反馈                                                                          |
| `frontend/src/shared/http.ts`                    | 张锦昊在 [#47](https://github.com/LotteryCamp/OfferPilot/pull/47) 提供的共享 Axios 客户端                     |
| `workspaceIntegrations.modules.sources` / `plan` | 张锦昊负责来源与条件、分析、自查补录及候选审阅，见 [#32](https://github.com/LotteryCamp/OfferPilot/issues/32) |
| `workspaceIntegrations.modules.tasks`            | 陈常群负责正式任务整体页面及注册，见 [#31](https://github.com/LotteryCamp/OfferPilot/issues/31)               |

## 路由与上下文

| 路由                          | 作用                 |
| ----------------------------- | -------------------- |
| `/matters`                    | 个人事项列表         |
| `/matters/new`                | 新建推免事项         |
| `/matters/:matterId/overview` | 读取事项并展示概览   |
| `/matters/:matterId/sources`  | 来源与条件组件入口   |
| `/matters/:matterId/plan`     | 候选计划审阅组件入口 |
| `/matters/:matterId/tasks`    | 正式任务组件入口     |

`matterId` 为 UUID，导航统一小写。刷新和直接访问先读取事项；读取失败不挂载业务子组件。前端路由校验不承担后端权限职责。

注册的子组件接收 `matterId: string` 和只读用途的 `matter: Matter`。写入成功后，`changed` 事件触发父级重新读取。业务模块接入后，同一事项重读期间保留已挂载组件和所选候选，事项 ID 切换或读取失败时清除旧上下文。切换事项时停止旧读取和轮询，离开的页面不得更新新事项。取消前端读取不影响已发起的后端操作。

## 事项 HTTP 契约

共享客户端采用 `/api/v1` 为 baseURL。适配器执行下列已从 #41 文档核实的操作：

| 方法及相对路径        | 输入与返回                                                                                |
| --------------------- | ----------------------------------------------------------------------------------------- |
| `GET /matters`        | `{ matters: Matter[] }`，当前演示工作区，按更新时间倒序                                   |
| `POST /matters`       | `{ goal, type_code: 'pre_recommend', scope_year, scope_attrs }`；`201 { matter: Matter }` |
| `GET /matters/{UUID}` | `{ matter: Matter }`；不存在或越界返回 404                                                |

创建目标去首尾空白后 1—200 字符，年度为 2020—2100 整数。`scope_attrs` 是允许的 JSON 属性；当前表单不猜测各范围键含义，提交空对象，并在概览提示补核范围。当前创建请求不接受模板 ID，模板关联由后端与迁移契约共同落实。

事项响应包含服务端 ID、工作区 ID、类型/类型名、目标、状态、年度、范围、归档/创建/更新时间、`tasks {total,done,open}`、可空的 `latest_plan {id,status,version_no}`。已有事项允许年度和范围为 `null`，页面显示未填写，创建仍要求有效年度。事项、候选及正式任务状态保持独立。

`SharedHttpClient` 定义消费端接口 `request<T>({method,url,data?,signal?}): Promise<{data:T}>`。事项适配器已接入 `src/shared/http.ts` 的 Axios 客户端，与来源及计划共用配置。`workspaceIntegrations.modules.sources`、`plan` 已注册业务组件，`tasks` 保留注册点。`VITE_LOCAL_DEMO_MATTERS=1` 启用开发模式的真实 Alpha API；生产连接由集成负责人配置。各组件遵守 `WorkspaceModule` 约束，接收事项 ID 与只读事项，并声明 `changed` 事件。

业务错误体为 `{error:{code,message,next?,details?}}`，422 的字段问题位于 `details.issues`。创建遇到 `409 template_version_missing` 时保留表单并提示补齐已发布模板。网络中断、超时（含 HTTP 408）或创建结果无法核验时，保留表单、停用提交并提示先重读列表。未知错误使用前端提供的通用文案。

## 分析、候选决定与恢复

此流程沿用 #47 的分析与候选审阅调用。下表路径均相对于 `/api/v1`。

| 场景           | 请求及处理                                                                                                                                                                                   |
| -------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 发起与查看分析 | `POST /matters/{matterId}/agent-runs` 接收 `source_urls` 等字段，使用同一事项的 `operation_id` 识别重复发起；已知运行 ID 时通过 `GET /agent-runs/{runId}` 读取                               |
| 核对分析结果   | HTTP `200` 返回 `{ run }`；用 `run.status` 和 `run.error` 区分运行中、缺口、失败等状态，进入 `等待确认` 后用 `persisted_plan_id` 定位已入库候选                                              |
| 读取持久化结果 | `GET /matters/{matterId}/sources` 读取来源、快照和随要求返回的 `self_check`；`GET /matters/{matterId}/candidate-plans` 和 `GET /candidate-plans/{planId}` 读取候选版本、内容、出处和已有决定 |
| 确认或拒绝     | `POST /candidate-plans/{planId}/confirm` 或 `POST /candidate-plans/{planId}/reject`，空请求体，携带 UUID 格式的 `Idempotency-Key`；同一决定重试复用原键                                      |
| 读取正式任务   | `GET /matters/{matterId}/tasks`；候选确认由后端事务生成任务，拒绝不会生成                                                                                                                    |

候选审阅在进入页面或恢复时均通过候选 ID 提交决定，一次用户操作只调用一条决定路径。后端还提供 `POST /agent-runs/{runId}/confirm` 和 `POST /agent-runs/{runId}/reject`。候选接口提交的决定以候选详情和任务重读为准，运行检查点可能仍显示 `等待确认`。后端返回依据变化、疑点未解决、来源不可用或官方期限已过时，显示失败与后续处理提示。

刷新或后端重启后，按事项 ID 重新读取来源、自查和候选列表，再读取指定候选及其已有决定。仍有效的待确认候选可以继续审阅。若已知运行 ID，可以读取持久化检查点。服务重启前仍在运行的任务标记为 `已中断`（`RUN_INTERRUPTED`），用户核对已保存结果后可使用新 `operation_id` 重新发起分析。排名事实持久化、补录后重查和最终联调按 [#32](https://github.com/LotteryCamp/OfferPilot/issues/32) 与后端核验。

## 身份与接口边界

Alpha 使用服务端固定演示用户及工作区，应用显示单用户本地演示。演示身份不存在时返回 `500 demo_identity_missing`。前端不发送自造身份头。服务启动后可通过 `/openapi.json` 核对实际部署的接口。

事项详情提供事项与任务摘要及最新计划引用。来源、自查和运行详情由对应业务端点读取。基础 PR 提供事项列表、创建、概览和模块挂载点。整体任务页、候选决定、来源与条件和 Agent 运行验收分别跟进 [#31](https://github.com/LotteryCamp/OfferPilot/issues/31) 和 [#32](https://github.com/LotteryCamp/OfferPilot/issues/32)。

## 集成验收

安装、启动、代理配置及检查命令见[前端开发与联调指南](development.md)。来源、分析、排名补录及候选决定的契约和 QA 定位入口分别见[来源与条件](source-conditions.md)、[候选审阅](plan-review.md)。

工作区基础验收覆盖真实创建、列表、概览及刷新读取同一 UUID，以及真实空列表、HTTP 404、服务中断、快速切换事项、保存期间重复点击和结果不明确时先核对列表。完整候选决定与任务验收在相应模块交付后执行。
