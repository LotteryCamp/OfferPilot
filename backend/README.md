# OfferPilot Alpha Backend

Alpha 核心演示的业务 API，基于 FastAPI、SQLAlchemy 与 PostgreSQL 16。

覆盖流程：创建个人事项、登记来源与快照、写入候选要求、持久化并读取候选计划、确认或拒绝候选计划、读取确认后生成的任务。

接口说明见 [`docs/backend/api.md`](../docs/backend/api.md)。

## 前置条件

| 依赖 | 要求 |
| :--- | :--- |
| Python | 3.13 |
| uv | 最新稳定版 |
| PostgreSQL | 16 及以上 |
| 数据库结构 | Alpha schema 迁移 `0001`—`0008` 已应用，参考数据与演示身份已写入 |
| 数据库角色 | 非所有者登录角色 `offerpilot_app`，具备 `core`、`ops` 模式访问权限 |

数据库结构由数据库迁移交付，本模块不包含 DDL 与迁移执行器。目标库须先具备事项、来源、快照、要求、证据、候选计划、计划项、计划项来源、计划决定、任务及读取视图。API 使用非所有者角色连接，以启用行级安全。

## 安装

```bash
cd backend
uv sync
```

## 配置

| 环境变量 | 必填 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- |
| `OFFERPILOT_DATABASE_URL` | 是 | 无 | API 数据库连接串；未设置时回退读取 `DATABASE_URL` |
| `OFFERPILOT_DEMO_USER_ID` | 否 | `00000000-0000-7000-8000-000000000001` | 演示用户标识 |
| `OFFERPILOT_DEMO_WORKSPACE_ID` | 否 | `00000000-0000-7000-8000-000000000002` | 演示工作区标识 |
| `OFFERPILOT_DEMO_TIMEZONE` | 否 | `Asia/Shanghai` | 官方日期期限的比较时区 |
| `OFFERPILOT_HOST` | 否 | `127.0.0.1` | 监听地址 |
| `OFFERPILOT_PORT` | 否 | `8000` | 监听端口 |

示例：

```bash
export OFFERPILOT_DATABASE_URL='postgresql://offerpilot_app:<password>@127.0.0.1:5432/offerpilot'
```

演示用户与工作区须与数据库中的 `core.app_user`、`core.workspace` 一致。身份不匹配时服务返回 `demo_identity_missing`。

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

| 变量 | 用途 |
| :--- | :--- |
| `OFFERPILOT_TEST_DATABASE_URL` | 受行级安全约束的应用角色连接，供 API 使用 |
| `OFFERPILOT_TEST_ADMIN_DATABASE_URL` | 测试库所有者连接，用于清理数据、写入夹具与模拟来源状态变化 |

未设置上述变量时集成测试跳过。测试库须已应用 Alpha schema，并授予应用角色读写权限；测试夹具会写入演示用户、工作区与 `pre_recommend` 事项类型。

## 检查

```bash
uv run ruff check .
uv run ruff format --check .
uv run ty check src tests
```

## 代码结构

| 路径 | 职责 |
| :--- | :--- |
| `src/backend/main.py` | 应用工厂、路由挂载、健康检查 |
| `src/backend/config.py` | 环境配置与演示身份 |
| `src/backend/db.py` | 引擎、会话与工作区事务 |
| `src/backend/tables.py` | Alpha schema 的 SQLAlchemy 表与视图映射 |
| `src/backend/schemas.py` | 请求字段校验 |
| `src/backend/basis.py` | 依据输入规范化与指纹 |
| `src/backend/services/` | 事项、来源、要求、计划、决定与任务业务 |
| `src/backend/routers/` | HTTP 路由与依赖 |
| `tests/` | 真实数据库集成测试 |

## 演示边界

- 无登录与账户切换，所有请求使用固定演示身份。
- 不执行网络抓取、模型调用、材料生成或外部提交。
- 不提供任务状态更新、事项归档或候选计划内容修改接口。
- 数据隔离依赖工作区校验与行级安全，当前不提供多用户认证。
