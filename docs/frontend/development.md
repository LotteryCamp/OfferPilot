# OfferPilot 个人事项前端

Vue 3 + TypeScript + Vite 应用，提供注册、登录、个人账户与会话状态，以及个人事项列表、新建表单、事项工作区、概览及来源/条件、候选计划、正式任务的统一入口。界面采用中文、紫色主题与左侧导航。

## 安装与运行

需要 Node.js 24 LTS 和 npm 11。进入仓库的 `frontend/` 目录后执行：

```powershell
npm ci
if (-not (Test-Path .env.local)) { Copy-Item .env.example .env.local }
npm run dev
```

打开终端输出的 `http://127.0.0.1:5173`。`.env.local` 仅保存可公开的前端配置。模型密钥和身份凭据由后端管理。未连接账户服务时，受保护页面提示无法确认登录状态并提供重试及登录入口；注册和登录表单可以填写及校验。业务页面仅在服务端确认会话有效后挂载。

## 检查与构建

```powershell
npm run lint
npm run format:check
npm run type-check
npm run test:unit
npm run test:unit:coverage
npm run build
npm run preview
```

覆盖率统计 `src` 下的 TypeScript 与 Vue 源码，报告写入 `coverage/`，终端输出未覆盖行。Frontend CI 使用 `npm run test:unit:coverage`，并将 `coverage/lcov.info` 上传到 Coveralls。

纯逻辑测试检查表单、路由和状态语义。浏览器检查使用实际运行的前端，不拦截请求、不替换业务响应：

```powershell
npx playwright install chromium
npm run test:e2e
```

Windows 已安装 Edge 时也可使用现有浏览器：`$env:PLAYWRIGHT_CHANNEL='msedge'`，然后执行 `npm run test:e2e`。

默认浏览器检查覆盖未接通状态下的受保护路由、会话检查失败和认证表单。连接测试后端后，通过下方独立命令复测真实认证、账号切换、创建和重读。

## 本地真实事项联调

事项 API 对应业务 PR #41，认证 API 对应 #57/#59。使用当前主分支后端、独立 PostgreSQL 数据库和包含 0018 在内的最新迁移，在 `.env.local` 配置如下，并重启开发服务器。

```dotenv
API_PROXY_TARGET=http://127.0.0.1:8000
```

开发服务器同源转发 `/api`。注册成功自动登录，已注册用户在 `/login` 登录，个人账户位于 `/account`。业务接口由同源 `offerpilot_session` Cookie 维持会话；开发和生产使用同一共享客户端。事项界面使用 `/api/v1/matters` 的真实请求，按服务端返回的 UUID 跳转；概览和浏览器刷新都会重读同一事项。超时或响应无法核验时保留表单并提示先核对列表。

在可写的隔离测试库上执行浏览器验收。用例自行注册独立测试账户，创建测试事项并保留在测试库中供复查。

```powershell
$env:API_PROXY_TARGET = 'http://127.0.0.1:8000'
$env:PLAYWRIGHT_CHANNEL = 'chrome'
npm run test:matters:live
```

已有 Playwright Chromium 时可省略 `PLAYWRIGHT_CHANNEL`。此命令另启动 5174 端口的开发服务器，核对 POST `201`、列表 `200` 含同一 UUID、从列表点入详情 `200`，以及刷新再次返回相同 UUID。测试结果与失败追踪保存在 `test-results/matters-live/`。

## 团队共享客户端接入

1. 事项、来源和候选计划共用 `src/shared/http.ts` 的 Axios 客户端。它满足 `src/modules/matters/api.ts` 中 `SharedHttpClient`，返回 `{ data: T }`，支持读取取消与超时。各业务模块保留自己的响应校验和错误展示。
2. 共享客户端的 `baseURL` 使用后端真实前缀 `/api/v1`；事项适配器请求相对路径 `/matters`，不得重复拼接前缀。
3. `src/app/integrations.ts` 通过 `createMattersApi(http)` 接入事项适配器。受保护路由由认证状态控制；生产服务连接由集成负责人配置。
4. `src/modules/auth` 使用注册、登录、退出及当前账户接口。路由守卫通过 `/auth/me` 恢复会话，`authentication_required` 触发会话失效和登录导航，凭据错误在表单反馈。共享客户端携带 Cookie；跨源部署由部署层配置精确的 CORS 来源。退出或会话变化取消业务请求并重挂工作区，运行和决定标识按账号隔离。个人资料编辑及材料操作继续按实际账户与业务契约接入。
5. `.env.local` 中的 `API_PROXY_TARGET` 指向实际启动的后端；只在显式指定时启用开发代理。生产部署须提供 `/api` 的同源反向代理，以及 Vue Router 的 SPA 深链接回退。`npm run preview` 只检查静态构建，不承担业务服务转发。
6. 来源与条件、候选计划审阅及正式任务分别通过 `workspaceIntegrations.modules.sources`、`plan`、`tasks` 注册。各组件接收 `matterId` 和只读用途的 `matter`，写入完成后触发 `changed`，父工作区重读事项。同事项重读保持业务组件，事项变化时清除旧上下文。正式任务页读取当前事项的任务列表，展示进度及前置任务，并可回到产生任务的候选版本。

接口和模块约定见[工作区集成约定](workspace-integration.md)。

## Agent 分析超时与反向代理

Agent 启动请求同步返回，浏览器默认等待 420 秒。后端的 `OFFERPILOT_MODEL_TIMEOUT_SECONDS` 是单次模型调用的上限，端到端时限还要覆盖抽取、规划、来源读取和持久化。Vite 开发代理为 Agent 启动路由使用 `VITE_AGENT_RUN_TIMEOUT_SECONDS` 加 30 秒余量，其他 API 沿用共享代理配置。

生产部署需在实际反向代理和入口网关为分析请求提供相同或更长的响应等待时间。使用默认浏览器预算时，Nginx 可将下例放入现有同源 `server` 配置，并保留现有通用 `/api/` 转发、鉴权及 SPA 回退。确认这条规则实际匹配 Agent 启动路由。

```nginx
location ~ ^/api/v1/matters/[^/]+/agent-runs/?$ {
    proxy_pass http://127.0.0.1:8000;
    proxy_read_timeout 450s;
    proxy_send_timeout 450s;
}
```

修改浏览器预算后应重新构建，并同步核对每层网关的空闲和总响应时限。通过实际部署地址复测慢速分析，记录 HTTP 状态、耗时、运行 ID 和候选 ID。遇到 502、504 或前端等待超时，先读取已保存的来源和候选结果，核对后再尝试。如入口平台存在不可调整的短时限，需要由后端提供立即返回运行 ID 并支持状态查询的接口，再将前端切换为按 ID 查询。

## 交互约束

- 事项 ID 只采用后端返回的 UUID，概览重新读取服务端内容。非法参数与未知路由提供恢复入口。
- 读取时取消旧请求，并使用请求序号阻止旧响应覆盖；切换事项清除前一事项内容。
- 未连接、加载、真实空结果、读取失败分别展示。未读取不表示没有事项。
- 表单仅在页面内保留；离开未保存表单会提示。保存中禁止重复提交和路由离开。
- 创建请求网络异常、服务异常或响应无法核验时，写入结果视为未知。当前创建契约没有幂等键或操作查询，需先到列表核对，禁止自动重试或声称未写入。
- 来源模块支持公开 HTML 通知读取、关联来源与历史快照、原文和要求引用展示；候选模块支持计划审阅、确认/拒绝、稳定操作标识重试及确认后的任务重读。
- 来源要求返回 `self_check` 时，逐条展示四态自查结论、判断原因、缺失信息与缺口出处；字段未返回时提示尚无可读取结果。后端提供保存和按事项读取，联调数据库需应用当前迁移并完成登录后验证真实刷新及重启恢复。
- 来源页可对已读取或选择的公开来源发起 Agent 分析、查询运行状态，并刷新已保存的来源与候选结果。等待补充、失败、运行找不到和结果未知分别提示；分析请求不创建正式任务。按账户和事项保存到当前标签页的运行标识仅辅助查询，业务结果始终由来源和候选接口重新读取。
- 当前事项提供排名补录、正整数及范围校验、本人真实性确认、事项级保存与读取，以及保存后重新自查。保存后重读核对版本，再由 Agent 读取后端的当前事项事实；未保存输入不参与自查，失败保留输入。缺少来源或尚无可用授权时可先保存，满足条件后仅重新自查。本地比例展示不判断资格。整体任务页保留注册点，任务状态更新不在本模块中实现。
- 分析区读取并展示当前用户的统一模型传输披露信息，用户主动确认后授予；撤回后重读并停用旧标识。分析前再次读取授权，由后端查询当前用户的统一授权；授权结果不确定时停止新分析并提示核对。
