# 本地安装与配置

本文说明在本地准备 OfferPilot 开发环境的步骤：依赖、数据库初始化、环境变量与启动命令。后端接口与业务流程见[后端说明](../backend/README.md)，前端模块与业务联调见[前端开发与联调指南](frontend/development.md)。

## 前置条件

| 组件 | 版本 | 用途 |
| :--- | :--- | :--- |
| Python | 3.13 | 后端运行时 |
| uv | 最新稳定版 | 后端依赖管理与命令执行 |
| PostgreSQL | 16 及以上 | 业务数据库 |
| Node.js | 24 | 前端开发服务器与构建 |
| npm | 11 | 前端依赖管理 |
| Docker | 最新稳定版 | 启动本地 PostgreSQL，可用已有 PostgreSQL 实例替代 |

## 获取代码

```bash
git clone https://github.com/LotteryCamp/OfferPilot.git
cd OfferPilot
```

后端的命令在 `backend/` 目录执行，前端的命令在 `frontend/` 目录执行。

## 后端

### 安装依赖

```bash
cd backend
uv sync
```

`uv` 依据 `backend/.python-version` 使用 Python 3.13。

### 启动数据库

```bash
cd db
docker compose up -d
cd ..
```

Compose 定义位于 `backend/db/docker-compose.yml`，启动 PostgreSQL 16，创建 `offerpilot` 数据库，超级用户为 `postgres`，默认口令为 `postgres`，仅监听 `127.0.0.1:5432`，数据保存在命名卷 `offerpilot_pgdata`。需要覆盖默认口令时，在执行 `docker compose up -d` 前设置 `POSTGRES_PASSWORD`。

使用已有 PostgreSQL 16 实例时跳过此步，自行创建 `offerpilot` 数据库。

### 应用迁移与参考数据

```bash
export DATABASE_URL='postgresql://postgres:postgres@127.0.0.1:5432/offerpilot'
uv run python db/migrate.py migrate
uv run python db/migrate.py seed
```

`migrate` 按文件名顺序执行 `db/migrations` 中尚未应用的迁移，成功版本与校验和记录在 `ops.schema_version`。`seed` 写入事项类型与已发布模板版本。`uv run python db/migrate.py status` 查看迁移状态，`migrate --dry-run` 只列出待执行迁移。

### 创建应用角色

```bash
psql "$DATABASE_URL" -f db/dev/roles.sql
```

以数据库所有者执行一次。脚本创建非所有者登录角色 `offerpilot_app`，授予 `core`、`ops` 模式的访问权限与账户表所需的列级授权。API 以该角色连接，行级安全才会生效。开发默认口令写在 `db/dev/roles.sql`，生产环境须改为强口令并通过密钥管理注入。

未安装 `psql` 时，可在 `backend/db/` 目录通过容器执行：

```bash
docker compose exec -T postgres psql -U postgres -d offerpilot < dev/roles.sql
```

### 配置环境变量

```bash
export OFFERPILOT_DATABASE_URL='postgresql://offerpilot_app:<roles.sql 中的口令>@127.0.0.1:5432/offerpilot'
```

后端从进程环境读取配置，不自动加载 `.env` 文件。`backend/.env.example` 列出全部变量，默认值与完整说明见[后端配置](../backend/README.md#配置)。PowerShell 使用 `$env:OFFERPILOT_DATABASE_URL = '...'` 设置变量。

Agent 分析需要 OpenAI 兼容模型服务，配置以下变量：

| 变量 | 说明 |
| :--- | :--- |
| `OFFERPILOT_MODEL_API_URL` | 模型服务地址 |
| `OFFERPILOT_MODEL_NAME` | 模型名称 |
| `OFFERPILOT_MODEL_API_KEY` | 服务密钥 |
| `OFFERPILOT_MODEL_PROVIDER` | 服务商名称，写入模型传输同意记录 |
| `OFFERPILOT_MODEL_TIMEOUT_SECONDS` | 单次模型请求超时，默认 `180` 秒 |

未配置模型服务时，Agent 运行返回 `MODEL_ERROR`，其余接口正常工作。

### 启动

```bash
uv run backend
```

服务默认监听 `127.0.0.1:8000`，监听地址与端口可通过 `OFFERPILOT_HOST`、`OFFERPILOT_PORT` 修改。健康检查：

```bash
curl http://127.0.0.1:8000/healthz
```

响应为 `{"status": "ok"}`。Swagger UI 位于 `/docs`，OpenAPI 描述位于 `/openapi.json`。

### 账户初始化

注册接口创建的普通账户立即生效，并自动获得个人工作区。首个管理员通过命令行创建，初始密码只从环境变量读取：

```bash
export OFFERPILOT_ADMIN_PASSWORD='<初始密码>'
uv run offerpilot-admin create --email admin@example.com --display-name 系统管理员
```

写入演示账户与演示事项：

```bash
uv run python db/migrate.py seed --demo
```

该命令使用数据库所有者连接，即上面导出的 `DATABASE_URL`。演示账户为 `demo@example.com`，口令见[后端账户初始化](../backend/README.md#账户初始化)。演示数据只用于本地演示与联调。

### 测试

后端集成测试直接访问真实 PostgreSQL，不使用替身数据层，并会清空重建业务表，须使用独立测试库。

```bash
docker exec offerpilot-db createdb -U postgres offerpilot_test
export OFFERPILOT_TEST_ADMIN_DATABASE_URL='postgresql://postgres:postgres@127.0.0.1:5432/offerpilot_test'
uv run python db/migrate.py --dsn "$OFFERPILOT_TEST_ADMIN_DATABASE_URL" migrate
uv run python db/migrate.py --dsn "$OFFERPILOT_TEST_ADMIN_DATABASE_URL" seed
psql "$OFFERPILOT_TEST_ADMIN_DATABASE_URL" -f db/dev/roles.sql
export OFFERPILOT_TEST_DATABASE_URL='postgresql://offerpilot_app:<roles.sql 中的口令>@127.0.0.1:5432/offerpilot_test'
uv run pytest tests -q
```

使用已有 PostgreSQL 实例时，以 `createdb` 与 `psql` 完成相同的数据库创建、迁移、参考数据与应用角色授权。未设置两个测试库变量时，数据库相关用例跳过。

统计覆盖率：

```bash
uv run pytest tests -q --cov --cov-report=term-missing
```

覆盖率统计 `src/backend` 的行覆盖率，门槛为 60%。

### 检查

```bash
uv run ruff check .
uv run ruff format --check .
uv run ty check
```

## 前端

### 安装与启动

```bash
cd frontend
npm ci
cp .env.example .env.local
npm run dev
```

PowerShell 使用 `Copy-Item .env.example .env.local`。开发服务器监听 `127.0.0.1:5173`，打开终端输出的地址。`.env.local` 只保存可公开的前端配置，模型密钥与身份凭据由后端管理。默认配置不连接业务服务，页面可以导航、填写与校验表单，不会产生事项数据。

### 连接本地后端

在 `.env.local` 中启用开发联调并指向后端，然后重启开发服务器：

```dotenv
VITE_LOCAL_DEMO_MATTERS=1
API_PROXY_TARGET=http://127.0.0.1:8000
```

开发服务器同源转发 `/api`，登录态通过 `offerpilot_session` Cookie 维持。真实事项联调与浏览器验收见[前端开发与联调指南](frontend/development.md)。

### 检查与构建

```bash
npm run lint
npm run format:check
npm run type-check
npm run test:unit
npm run build
```

浏览器测试首次需要安装 Chromium：

```bash
npx playwright install chromium
npm run test:e2e
```

Windows 已安装 Edge 时，可将 `PLAYWRIGHT_CHANNEL` 设为 `msedge`，使用现有浏览器执行测试。

## 相关文档

- [后端说明](../backend/README.md)：接口、完整环境变量表、测试与演示边界。
- [前端开发与联调指南](frontend/development.md)：真实事项联调、Agent 超时与反向代理配置。
- [工作区集成约定](frontend/workspace-integration.md)：模块接入与事项 HTTP 契约。
