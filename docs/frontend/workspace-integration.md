# 个人事项工作区集成约定

本说明覆盖陈常群负责的入口、路由、事项列表、创建、概览及模块接入。事项适配对应 #41 的 `91a857104f0a57302a1e4dbc829b48556f1c2508`，数据库迁移见已合入 `main` 的 #39。

## 责任与文件边界

| 范围 | 维护边界 |
| --- | --- |
| `frontend/src/app`、`router`、`modules/matters` | 陈负责入口、布局、导航、事项业务适配与页面 |
| `frontend/src/shared/ui/StatePanel.vue` | 可共同复用的加载、空内容、错误和未接通反馈；后续变更需双人审阅 |
| `frontend/src/shared/api` | 张负责唯一请求客户端、超时、身份、通用错误处理；此工作区不创建该目录 |
| 来源、条件、个人事实与补录 | 张负责业务组件；陈通过组件注册接入 |
| 候选与任务 | 此次仅保留路由和组件注册点；候选页面具体归属先核对团队决策及已有代码 |

## 路由与上下文

| 路由 | 作用 |
| --- | --- |
| `/matters` | 个人事项列表 |
| `/matters/new` | 新建推免事项 |
| `/matters/:matterId/overview` | 读取事项并展示概览 |
| `/matters/:matterId/sources` | 来源与条件组件入口 |
| `/matters/:matterId/plan` | 候选计划审阅组件入口 |
| `/matters/:matterId/tasks` | 正式任务组件入口 |

`matterId` 为 UUID，导航统一小写。刷新和直接访问先读取事项；读取失败不挂载业务子组件。前端路由校验不承担后端权限职责。

注册的子组件接收 `matterId: string` 和 `matter: Matter`；不得直接改动传入事项对象。子组件切换事项后需终止读取、清理轮询及待提交输入。`changed` 事件触发父级重新读取；返回概览也会重新读取。取消前端读取不表示停止后端任务。

## 事项 HTTP 契约

共享客户端采用 `/api/v1` 为 baseURL。适配器执行下列已从 #41 文档核实的操作：

| 方法及相对路径 | 输入与返回 |
| --- | --- |
| `GET /matters` | `{ matters: Matter[] }`，当前演示工作区，按更新时间倒序 |
| `POST /matters` | `{ goal, type_code: 'pre_recommend', scope_year, scope_attrs }`；`201 { matter: Matter }` |
| `GET /matters/{UUID}` | `{ matter: Matter }`；不存在或越界返回 404 |

创建目标去首尾空白后 1—200 字符，年度为 2020—2100 整数。`scope_attrs` 是允许的 JSON 属性；当前表单不猜测各范围键含义，提交空对象，并在概览提示补核范围。当前创建请求不接受模板 ID，模板关联由后端与迁移契约共同落实。

事项响应包含服务端 ID、工作区 ID、类型/类型名、目标、状态、年度、范围、归档/创建/更新时间、`tasks {total,done,open}`、可空的 `latest_plan {id,status,version_no}`。已有事项允许年度和范围为 `null`，页面显示未填写，创建仍要求有效年度。事项、候选及正式任务状态保持独立。

`SharedHttpClient` 定义消费端接口 `request<T>({method,url,data?,signal?}): Promise<{data:T}>`。团队客户端仍由张维护。显式启用 `VITE_LOCAL_DEMO_MATTERS=1` 时，开发模式的事项模块可用浏览器请求经同源代理访问真实 Alpha API。该接线限于事项的读写，沿用现有适配器并支持取消和超时。团队联调或生产对接时在 `workspaceIntegrations` 使用实际共享客户端。

业务错误体为 `{error:{code,message,next?,details?}}`，422 的字段问题位于 `details.issues`。页面提供就地字段校验，后端错误保留表单。不得直接展示堆栈、凭据或原始内部错误。

## 身份与暂不可用能力

#41 使用服务端固定演示用户及工作区，无登录能力；若接入，应用须声明单用户本地演示，不能宣称跨账户安全隔离。演示身份不存在时后端返回 `500 demo_identity_missing`。前端不发送自行构造的用户或工作区身份头。

#41 提供 `/openapi.json`，实际接口版本在服务启动后核对。事项契约中没有来源与条件缺口摘要、Agent 运行状态、创建幂等键或创建操作查询。未接通页面明确说明。创建网络超时或提交结果无法核验时先检查列表。

候选确认/拒绝的具体 HTTP 路径与讨论稿不同，实际 #41 为 `/candidate-plans/{id}/confirm` 和 `/reject`，使用 UUID `Idempotency-Key`。此处记录供后续集成核对，本次工作区未实现这些写操作。任务状态更新、归档和事实补录目前没有 #41 对应接口。

## 集成验收

连接真实后端、独立测试库和演示身份后，运行 `npm run test:matters:live` 检查真实创建、列表、概览及刷新使用同一个 UUID，启动步骤见前端 README。联调时另检查真实空列表、HTTP 404、服务中断、快速切换事项、保存期间重复点击以及结果不明确时先查列表。完整候选决定与任务验收在相应模块交付后执行。
