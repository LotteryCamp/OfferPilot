# OfferPilot Backend

多用户业务 API，基于 FastAPI、SQLAlchemy 与 PostgreSQL 16。

覆盖流程：注册、登录、会话与管理员账户管理；创建个人事项、保存与读取个人事实、发起 Agent 运行读取来源并生成待确认候选、读取或登记来源与快照、写入候选要求、持久化并读取候选计划、确认或拒绝候选计划、读取确认后生成的任务。

接口说明见 [`docs/backend/api.md`](../docs/backend/api.md)。
个人事实接口见 [`docs/backend/facts.md`](../docs/backend/facts.md)。
账户与管理员接口见 [`docs/backend/accounts.md`](../docs/backend/accounts.md)。

## 前置条件

| 依赖 | 要求 |
| :--- | :--- |
| Python | 3.13 |
| uv | 最新稳定版 |
| PostgreSQL | 16 及以上 |
| 数据库结构 | schema 迁移 `0001`—`0018` 已应用，参考数据已写入 |
| 数据库角色 | 非所有者登录角色 `offerpilot_app`，具备 `core`、`ops` 模式访问权限与账户表授权 |

数据库结构由本模块的迁移交付。目标库须先具备账户、登录会话、登录限流计数、个人工作区、事项、来源、快照、要求、证据、个人事实、模型传输同意、候选计划、计划项、计划项来源、计划决定、任务及读取视图。API 使用非所有者角色连接，以启用行级安全。

## 安装

```bash
cd backend
uv sync
```

数据库初始化、应用角色与测试库的准备步骤见[本地安装与配置](../docs/getting-started.md)。

## 配置

| 环境变量 | 必填 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- |
| `OFFERPILOT_DATABASE_URL` | 是 | 无 | API 数据库连接串；未设置时回退读取 `DATABASE_URL` |
| `OFFERPILOT_CONFIG_FILE` | 否 | 无 | 运行配置文件路径；设置后模型、会话、限流与时区可由文件覆盖并热更新 |
| `OFFERPILOT_TIMEZONE` | 否 | `Asia/Shanghai` | 官方日期期限的比较时区 |
| `OFFERPILOT_SESSION_TTL_SECONDS` | 否 | `43200` | 普通登录会话有效期，单位秒 |
| `OFFERPILOT_REMEMBER_SESSION_TTL_SECONDS` | 否 | `2592000` | 记住登录会话有效期，单位秒 |
| `OFFERPILOT_COOKIE_SECURE` | 否 | `false` | 是否给会话 Cookie 设置 `Secure`；HTTPS 部署设为 `true` |
| `OFFERPILOT_LOGIN_IP_WINDOW_SECONDS` | 否 | `300` | IP 限流固定窗口，单位秒 |
| `OFFERPILOT_LOGIN_IP_LIMIT` | 否 | `60` | 窗口内允许的登录请求数；`0` 关闭 IP 维度 |
| `OFFERPILOT_LOGIN_EMAIL_WINDOW_SECONDS` | 否 | `900` | 邮箱失败计数固定窗口，单位秒 |
| `OFFERPILOT_LOGIN_EMAIL_LIMIT` | 否 | `5` | 窗口内允许的失败次数；`0` 关闭邮箱维度 |
| `OFFERPILOT_LOGIN_LOCK_SECONDS` | 否 | `900` | 邮箱达到阈值后的临时锁定时长，单位秒 |
| `OFFERPILOT_HOST` | 否 | `127.0.0.1` | 监听地址 |
| `OFFERPILOT_PORT` | 否 | `8000` | 监听端口 |
| `OFFERPILOT_MODEL_API_URL` | 否 | 无 | OpenAI 兼容模型服务地址；未配置时 Agent 运行返回 `MODEL_ERROR` |
| `OFFERPILOT_MODEL_NAME` | 否 | 无 | 模型名称 |
| `OFFERPILOT_MODEL_PROVIDER` | 否 | `OpenAI 兼容模型服务` | 模型传输同意的服务商名称，写入同意记录并参与出站校验 |
| `OFFERPILOT_MODEL_API_KEY` | 否 | 无 | 模型服务密钥 |
| `OFFERPILOT_MODEL_TIMEOUT_SECONDS` | 否 | `180` | 单次模型请求超时，单位秒 |

来源正文较长时，需求抽取请求需要较长的生成时间。`OFFERPILOT_MODEL_TIMEOUT_SECONDS` 推荐取 `180`；来源总量接近单次运行上限时取 `300`。

示例：

```bash
export OFFERPILOT_DATABASE_URL='postgresql://offerpilot_app:<password>@127.0.0.1:5432/offerpilot'
```

### 运行配置文件

设置 `OFFERPILOT_CONFIG_FILE` 后，模型服务商、名称、地址、密钥、超时，会话有效期与 Cookie Secure，登录限流参数，以及时区可由 YAML 文件覆盖环境变量。文件变化由每次请求检测，约 1 秒缓存；管理员可通过 `GET/PATCH /api/v1/admin/settings` 读取与修改。文件格式、校验规则、生效语义与部署注意事项见[运行配置](../docs/backend/configuration.md)。

## 账户初始化

注册接口创建的普通用户立即生效，并自动获得个人工作区。首个管理员由命令行创建，初始密码只从环境变量读取：

```bash
export OFFERPILOT_ADMIN_PASSWORD='<初始密码>'
uv run offerpilot-admin create --email admin@example.com --display-name 系统管理员
```

演示种子账户为 `demo@example.com`，口令为 `demo-password-2026`。执行 `uv run python db/migrate.py seed --demo` 后，可使用该账户登录并读取种子中的演示事项。该账户只用于本地演示数据。

登录成功后服务端设置 `offerpilot_session` Cookie。普通会话有效 12 小时，登录请求携带 `"remember": true` 时有效 30 天。所有业务接口要求有效会话；详细接口与错误码见[账户、登录与管理员接口](../docs/backend/accounts.md)。

登录接口按客户端 IP 与邮箱地址两级限流，默认同一 IP 每 5 分钟最多 60 次登录请求，同一邮箱每 15 分钟累计 5 次失败后临时锁定 15 分钟。阈值、窗口与锁定时长可通过 `OFFERPILOT_LOGIN_*` 环境变量调整；次数上限设为 `0` 时关闭对应维度。超限返回 `429 too_many_login_attempts` 与 `Retry-After`。邮箱维度按提交的邮箱计数，账户不存在时行为一致。

客户端 IP 取自 ASGI 服务器处理后的 `request.client.host`，应用不自行解析 `X-Forwarded-For`。uvicorn 默认信任来自 `127.0.0.1` 与 `::1` 的代理头；反向代理位于其他主机或容器时，须将 `FORWARDED_ALLOW_IPS` 设为代理地址或网段，不得设为 `*`。

## 启动

```bash
cd backend
uv run backend
```

健康检查：

```bash
curl http://127.0.0.1:8000/healthz
```

响应：

```json
{"status": "ok"}
```

OpenAPI 文档由 FastAPI 提供：

| 地址 | 内容 |
| :--- | :--- |
| `/docs` | Swagger UI |
| `/openapi.json` | OpenAPI 描述 |

## 测试

集成测试直接访问真实 PostgreSQL 数据库，不使用替身数据层。测试会清空并重建业务表数据，目标库须为独立测试库。

```bash
export OFFERPILOT_TEST_DATABASE_URL='postgresql://offerpilot_app:<password>@127.0.0.1:5432/offerpilot_test'
export OFFERPILOT_TEST_ADMIN_DATABASE_URL='postgresql://postgres@127.0.0.1:5432/offerpilot_test'
uv run pytest tests -q
```

统计测试覆盖率：

```bash
uv run pytest tests -q --cov --cov-report=term-missing
```

覆盖率统计 `src/backend` 的行覆盖率，门槛为 60%，未覆盖行会列在报告中。

| 变量 | 用途 |
| :--- | :--- |
| `OFFERPILOT_TEST_DATABASE_URL` | 受行级安全约束的应用角色连接，供 API 使用 |
| `OFFERPILOT_TEST_ADMIN_DATABASE_URL` | 测试库所有者连接，用于清理数据、写入夹具与模拟来源状态变化 |

未设置上述变量时集成测试跳过。测试库须已应用 schema，并授予应用角色读写权限；测试夹具会写入可登录的演示账户、工作区与 `pre_recommend` 事项类型。账户测试还会通过命令行创建管理员。

## CI

`.github/workflows/backend-ci.yml` 在推送 `main` 和拉取请求时启动 PostgreSQL 16，创建测试库与应用角色，执行数据库迁移和参考数据种子，然后运行 Ruff、格式检查、ty 与测试。数据库集成测试使用上述真实 PostgreSQL 实例；本地未配置测试库时这些用例跳过。

测试步骤使用 `pytest-cov` 统计 `src/backend` 的行覆盖率，门槛为 60%，覆盖率低于门槛时 CI 失败。覆盖率配置位于 `backend/pyproject.toml`。覆盖率报告以 LCOV 格式上传到 Coveralls，上传失败不阻断 CI。

## 检查

```bash
uv run ruff check .
uv run ruff format --check .
uv run ty check
```

## 代码结构

| 路径 | 职责 |
| :--- | :--- |
| `src/backend/main.py` | 应用工厂、路由挂载、健康检查 |
| `src/backend/config.py` | 环境配置、会话有效期与 Cookie 安全设置 |
| `src/backend/db.py` | 引擎、会话与工作区事务 |
| `src/backend/identity.py` | 请求级当前账户与个人工作区 |
| `src/backend/security.py` | Argon2 密码摘要与会话令牌摘要 |
| `src/backend/admin_cli.py` | 首个管理员创建命令 |
| `src/backend/tables.py` | schema 的 SQLAlchemy 表与视图映射 |
| `src/backend/schemas.py` | 请求字段校验 |
| `src/backend/basis.py` | 依据输入规范化与指纹 |
| `src/backend/fact_types.py` | 个人事实类型注册表、校验与渲染 |
| `src/backend/sources/` | 公开 HTML 来源读取、来源文档转换与命令行入口 |
| `src/backend/agent/` | Agent 编排、运行契约与业务端口适配 |
| `src/backend/services/` | 账户、会话、管理员、登录限流与事项等业务 |
| `src/backend/routers/` | HTTP 路由与认证依赖 |
| `tests/` | 真实数据库集成测试 |

## 演示边界

- 注册、登录、退出、记住登录与管理员账户管理已提供后端接口；前端登录界面由独立任务交付。
- 每个账户拥有独立个人工作区；管理员只能管理账户元数据，不能读取其他用户的私人业务数据。
- 登录失败按 IP 与邮箱计数并临时拒绝登录，不修改账户状态，也不撤销已有会话。
- 不提供邮件验证、找回密码、MFA、管理员操作审计、个人信息编辑与第三方登录。
- 来源读取只访问公开 HTML 页面；Agent 运行调用外部模型生成待确认候选，不解析 PDF 与附件、不生成材料、不执行外部提交。
- 不提供任务状态更新、事项归档或候选计划内容修改接口。
- 数据隔离依赖会话认证、工作区校验与行级安全。
