# OfferPilot 个人事项前端

Vue 3 + TypeScript + Vite 应用，提供个人事项列表、新建表单、事项工作区、概览及来源/条件、候选计划、正式任务的统一入口。界面采用中文、紫色主题与左侧导航。

## 安装与运行

需要 Node.js 24 LTS 和 npm。进入本目录后执行：

```powershell
npm ci
Copy-Item .env.example .env.local
npm run dev
```

打开终端输出的 `http://127.0.0.1:5173`。`.env.local` 仅保存可公开的前端配置。模型密钥和身份凭据由后端管理。默认配置不连接业务服务，页面明确呈现未接通状态；可以导航、填写及校验表单。服务未接入时不会产生事项数据。

## 检查与构建

```powershell
npm run lint
npm run format:check
npm run type-check
npm run test:unit
npm run build
npm run preview
```

纯逻辑测试检查表单、路由和状态语义。浏览器检查使用实际运行的前端，不拦截请求、不替换业务响应：

```powershell
npx playwright install chromium
npm run test:e2e
```

Windows 已安装 Edge 时也可使用现有浏览器：`$env:PLAYWRIGHT_CHANNEL='msedge'`，然后执行 `npm run test:e2e`。

默认浏览器检查覆盖未接通状态下的导航、深链接、表单校验和反馈。连接 Alpha 测试服务后，通过下方独立命令复测真实创建和重读。

## 本地真实事项联调

从业务 PR #41 的目标提交启动实际 Alpha API。对独立 PostgreSQL 测试库应用该提交的全部迁移、演示种子和应用角色配置。安装及启动方式见 [后端 README](https://github.com/LotteryCamp/OfferPilot/blob/f7c2800038e98e5af356e314ea7de061ce38558e/backend/README.md)。在 `.env.local` 配置如下，并重启开发服务器。

```dotenv
VITE_LOCAL_DEMO_MATTERS=1
API_PROXY_TARGET=http://127.0.0.1:8000
```

开发服务器同源转发 `/api`。事项界面使用 `/api/v1/matters` 的真实请求，按服务端返回的 UUID 跳转；概览和浏览器刷新都会重读同一事项。超时或响应无法核验时保留表单并提示先核对列表。此模式使用后端配置的固定演示身份，只有显式启用的 Vite 开发服务会激活。生产构建沿用团队统一请求层的接入约定。

在可写的隔离测试库上执行浏览器验收。命令每次创建一条 `Alpha 联调` 测试事项，保留在测试库中供复查。

```powershell
$env:API_PROXY_TARGET = 'http://127.0.0.1:8000'
$env:PLAYWRIGHT_CHANNEL = 'chrome'
npm run test:matters:live
```

已有 Playwright Chromium 时可省略 `PLAYWRIGHT_CHANNEL`。此命令另启动 5174 端口的开发服务器，核对 POST `201`、列表 `200` 含同一 UUID、从列表点入详情 `200`，以及刷新再次返回相同 UUID。测试结果与失败追踪保存在 `test-results/matters-live/`。联调记录需注明实际运行的后端提交与测试结果。

## 团队共享客户端接入

1. 张锦昊提供唯一的共享 HTTP 客户端。其 `request<T>` 接口须满足 `src/modules/matters/api.ts` 中 `SharedHttpClient`，返回 `{ data: T }`，支持读取取消；共享层负责超时、身份与通用错误转换。事项适配器只执行业务调用及响应校验。
2. 共享客户端的 `baseURL` 使用后端真实前缀 `/api/v1`；事项适配器请求相对路径 `/matters`，不得重复拼接前缀。
3. 集成 #47 时复用 `src/shared/http.ts` 导出的 `http`。在 `src/app/integrations.ts` 的 `workspaceIntegrations` 中使用 `createMattersApi(http)` 接入事项。
4. 若接入 #41 的固定演示身份，同时提供 `identity: { mode: 'single-user-local', label: '单用户本地演示' }`，明确展示运行限制。客户端不得自行伪造登录状态。实际身份变更后应重新挂载应用并清理业务状态。
5. `.env.local` 中的 `API_PROXY_TARGET` 指向实际启动的后端；只在显式指定时启用开发代理。生产部署须提供 `/api` 的同源反向代理，以及 Vue Router 的 SPA 深链接回退。`npm run preview` 只检查静态构建，不承担业务服务转发。
6. 张锦昊的来源与条件、候选审阅分别通过 `workspaceIntegrations.modules.sources` / `plan` 注册。陈常群负责 `tasks`。各组件接收 `matterId` 和只读用途的 `matter`，写入完成后触发 `changed`，父工作区重读事项。

接口和模块约定见 `../docs/frontend/workspace-integration.md`。

## 交互约束

- 事项 ID 只采用后端返回的 UUID，概览重新读取服务端内容。非法参数与未知路由提供恢复入口。
- 读取时取消旧请求，并使用请求序号阻止旧响应覆盖；切换事项清除前一事项内容。
- 未连接、加载、真实空结果、读取失败分别展示。未读取不表示没有事项。
- 表单仅在页面内保留；离开未保存表单会提示。保存中禁止重复提交和路由离开。
- 创建请求网络异常、服务异常或响应无法核验时，写入结果视为未知。当前创建契约没有幂等键或操作查询，需先到列表核对，禁止自动重试或声称未写入。
- 概览显示事项详情提供的数据。来源、自查与 Agent 运行由各自的业务模块读取。
- 候选审阅、确认/拒绝、任务更新、事实补录和来源读取的业务实现由对应模块后续提供。本工程不会通过本地数组生成正式任务。
