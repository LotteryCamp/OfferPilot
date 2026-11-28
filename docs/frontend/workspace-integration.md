# 个人事项工作区集成约定

本说明覆盖个人事项工作区、账户会话及其业务模块接入。事项与分析接口见[后端契约](../backend/api.md)，账户接口见[账户契约](../backend/accounts.md)。完整联调使用当前数据库迁移，包括账户会话、登录限流、账户资料编辑、事项级排名事实及模型传输同意。基础工作区由 [#43](https://github.com/LotteryCamp/OfferPilot/pull/43) 交付。

## 责任与文件边界

| 范围                                             | 维护边界                                                                                                      |
| ------------------------------------------------ | ------------------------------------------------------------------------------------------------------------- |
| `frontend/src/app`、`router`、`modules/auth`、`modules/matters` | 陈常群负责账户、会话、工作区入口、导航与模块集成，见 [#75](https://github.com/LotteryCamp/OfferPilot/issues/75) |
| `frontend/src/shared/ui/StatePanel.vue`          | 共用的加载、空内容、错误和未接通反馈                                                                          |
| `frontend/src/shared/http.ts`                    | 复用 [#47](https://github.com/LotteryCamp/OfferPilot/pull/47) 的共享 Axios，陈常群维护会话失效与账号上下文，张锦昊进行组件评审 |
| `workspaceIntegrations.modules.sources` / `plan` / `tasks` | 张锦昊负责推免主流程、业务状态和页面体验，见 [#76](https://github.com/LotteryCamp/OfferPilot/issues/76) |

## 路由与上下文

| 路由                          | 作用                 |
| ----------------------------- | -------------------- |
| `/login`                     | 登录（公开）         |
| `/register`                  | 注册（公开）         |
| `/account`                   | 当前账户与会话       |
| `/matters`                    | 个人事项列表         |
| `/matters/new`                | 新建推免事项         |
| `/matters/:matterId/overview` | 读取事项并展示概览   |
| `/matters/:matterId/sources`  | 来源与条件组件入口   |
| `/matters/:matterId/plan`     | 候选计划审阅组件入口 |
| `/matters/:matterId/tasks`    | 当前事项的正式任务和前置依赖 |

`matterId` 为 UUID，导航统一小写。刷新和直接访问先读取事项；读取失败不挂载业务子组件。前端路由校验不承担后端权限职责。

注册的子组件接收 `matterId: string` 和只读用途的 `matter: Matter`。写入成功后，`changed` 事件触发父级重新读取。业务模块接入后，同一事项重读期间保留已挂载组件和所选候选，事项 ID 切换或读取失败时清除旧上下文。切换事项时停止旧读取和轮询，离开的页面不得更新新事项。取消前端读取不影响已发起的后端操作。

## 事项 HTTP 契约

共享客户端采用 `/api/v1` 为 baseURL。适配器执行下列已从 #41 文档核实的操作：

| 方法及相对路径        | 输入与返回                                                                                |
| --------------------- | ----------------------------------------------------------------------------------------- |
| `GET /matters`        | `{ matters: Matter[] }`，当前账户工作区，按更新时间倒序                                   |
| `POST /matters`       | `{ goal, type_code: 'pre_recommend', scope_year, scope_attrs }`；`201 { matter: Matter }` |
| `GET /matters/{UUID}` | `{ matter: Matter }`；不存在或越界返回 404                                                |

创建目标去首尾空白后 1—200 字符，年度为 2020—2100 整数。`scope_attrs` 是允许的 JSON 属性；当前表单不猜测各范围键含义，提交空对象，并在概览提示补核范围。当前创建请求不接受模板 ID，模板关联由后端与迁移契约共同落实。

事项响应包含服务端 ID、工作区 ID、类型/类型名、目标、状态、年度、范围、归档/创建/更新时间、`tasks {total,done,open}`、可空的 `latest_plan {id,status,version_no}`。已有事项允许年度和范围为 `null`，页面显示未填写，创建仍要求有效年度。事项、候选及正式任务状态保持独立。

`SharedHttpClient` 定义消费端接口 `request<T>({method,url,data?,signal?}): Promise<{data:T}>`。事项适配器已接入 `src/shared/http.ts` 的 Axios 客户端，与账户、来源、计划及正式任务共用配置。`workspaceIntegrations.modules.sources`、`plan`、`tasks` 均已注册。认证状态确认后挂载业务模块，开发和生产连接采用同一 API 契约。各组件遵守 `WorkspaceModule` 约束，接收事项 ID 与只读事项，并声明 `changed` 事件。

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

账户接口相对 `/api/v1` 提供注册、登录、退出、读取当前账户、编辑资料与修改密码。注册或登录成功后后端设置 `offerpilot_session` Cookie。前端已接入 `POST /auth/register`、`POST /auth/login`、`GET /auth/me`、`POST /auth/logout`，通过服务端确认当前账户与会话。业务请求收到 `401 authentication_required` 时清除工作区状态并进入登录页；`invalid_credentials` 和 `invalid_current_password` 留在相应表单反馈。会话恢复使用 `/auth/me`，没有额外续期端点。

开发服务器通过同源 `/api` 代理携带 Cookie。跨源直连时，共享客户端启用凭据，并由部署层配置精确的 CORS 来源；HTTPS 部署必须启用安全 Cookie。退出、会话失效或重新确认账户时取消旧业务请求、清空来源 Store、重挂载工作区，业务运行和决定的待确认标识按账户及事项隔离。退出未获服务端确认时隐藏业务界面并提供重试。管理员接口使用同一 Cookie，仅管理员账户可调用。服务启动后可通过 `/openapi.json` 核对实际部署的接口。

同源标签页通过站点存储中的会话版本与变更标识协调注册、登录和退出。标识不保存 Cookie、密码或账号资料。账户操作发出前发布变更，其他标签页暂停旧工作区请求并通过 `/auth/me` 确认稳定后的真实账户；共享客户端在业务请求实际发送和响应交付时核对已确认会话版本。在支持 Web Locks 的浏览器中，认证操作与业务请求通过同源锁协调，并发会话变化期间取消旧请求。待确认的会话及存储异常隐藏私有界面并反馈重试。服务端权限、归属和会话仍是业务判定依据。开发、部署和验收使用统一前端源，生产使用 HTTPS。

会话计时以服务端返回的 `expires_at` 为依据。到期时重新核对当前账户，超过浏览器单次定时器上限的长会话分段计算剩余时间，保留有效工作区。页面恢复可继续核对当前会话版本，已确认的正常会话不因普通焦点切换重建页面。

事项详情提供事项与任务摘要及最新计划引用。来源、自查和运行详情由对应业务端点读取。基础 PR 提供事项列表、创建、概览和模块挂载点。整体任务页、候选决定、来源与条件和 Agent 运行验收分别跟进 [#31](https://github.com/LotteryCamp/OfferPilot/issues/31) 和 [#32](https://github.com/LotteryCamp/OfferPilot/issues/32)。

## 集成验收

安装、启动、代理配置及检查命令见[前端开发与联调指南](development.md)。来源、分析、排名补录及候选决定的契约和 QA 定位入口分别见[来源与条件](source-conditions.md)、[候选审阅](plan-review.md)。

工作区基础验收覆盖真实创建、列表、概览及刷新读取同一 UUID，以及真实空列表、HTTP 404、服务中断、快速切换事项、保存期间重复点击和结果不明确时先核对列表。完整候选决定与任务验收在相应模块交付后执行。
