# Alpha 验收测试记录

- 关联：issue #34、后端 PR #41、验收报告 PR #45
- 代码基线：`feat/business-process` @ `36afb05`

## 测试环境

| 项 | 实际值 |
| --- | --- |
| 操作系统 | Windows |
| PostgreSQL | 16.16，端口 5433 |
| Python | 3.13（uv 管理） |
| uv | 0.13.9 |
| 测试数据库 | `offerpilot_test` |
| 迁移 | `0001` 至 `0009` 全部应用 |
| 参考数据 | `db/migrate.py seed` 已执行 |
| 应用角色 | `offerpilot_app`（`db/dev/roles.sql`） |
| 测试类型 | 固定网页/固定模型响应回放；真实模型联调单独记录 |

> 以下命令在 Bash（Git Bash/WSL）执行；PowerShell 需将 `export VAR=...` 改为 `$env:VAR='...'`。

## 复现步骤

```bash
cd backend
uv sync
export OFFERPILOT_TEST_DATABASE_URL='postgresql://offerpilot_app:offerpilot_dev_only@127.0.0.1:5433/offerpilot_test'
export OFFERPILOT_TEST_ADMIN_DATABASE_URL='postgresql://postgres@127.0.0.1:5433/offerpilot_test'
uv run python db/migrate.py --dsn "$OFFERPILOT_TEST_ADMIN_DATABASE_URL" migrate
uv run python db/migrate.py --dsn "$OFFERPILOT_TEST_ADMIN_DATABASE_URL" seed
uv run pytest tests/test_alpha_acceptance.py -q
uv run pytest tests -q
export PGTEST_ADMIN_DSN='postgresql://postgres@127.0.0.1:5433/postgres'
uv run python db/tests/test_alpha_schema.py -q
```

## 实际执行结果

| 命令 | 结果 |
| --- | --- |
| `uv run pytest tests/test_alpha_acceptance.py -q` | **6 passed** |
| `uv run pytest tests -q` | **59 passed, 2 failed** |
| `uv run python db/tests/test_alpha_schema.py -q` | **13 passed** |

## 验收矩阵

| issue #34 场景 | 覆盖方式 | 状态 |
| --- | --- | --- |
| 1. 创建个人事项并重新读取 | `test_acceptance_main_flow_creates_tasks`；并复用 #41 create/read 测试 | 通过 |
| 2. 读取公开来源并取得出处信息 | 主流程测试登记 source/snapshot 并校验 locator；来源读取测试在 full suite 中通过 | 通过 |
| 3. Agent 生成带出处和缺口的候选计划 | Agent #23 已合入；`test_agent_backend_flow.py` 的 2 个用例失败 | 失败 |
| 4. 确认候选计划后任务出现且可读取 | 主流程测试覆盖确认、幂等重放和任务读取 | 通过 |
| 5. 拒绝候选计划不创建任务 | `test_acceptance_reject_does_not_create_tasks` | 通过 |
| 6. 来源读取失败时显示失败/缺口 | API：`test_read_public_source_reports_unreadable_source` 覆盖 `source_read_failed`；Agent 契约覆盖 `network_error` / `SOURCE_UNAVAILABLE`；UI 未测 | 部分：API 失败路径通过；UI 未测 |
| 缺字段 | `test_acceptance_missing_required_fields` | 通过 |
| 非法来源 URL | `test_acceptance_invalid_source_url` | 通过 |
| 未知计划 | `test_acceptance_unknown_plan_returns_404` | 通过 |
| 跨用户/跨工作区隔离 | `test_acceptance_cross_workspace_matter_is_hidden` | 通过 |

## 缺陷/阻塞

- **Agent ↔ 后端联调**：2 个 `test_agent_backend_flow` 用例失败；复现记录和错误详情见 issue #34、PR #41，本文档只保留验收结论。责任人：李义东、王智钦、庄凯堃。
- **PR #41 CI**：Actions 卡在 `Check formatting`，type/unit/验收测试未在 Actions 执行；格式化由李义东修复。
- **#32 来源/条件/候选计划 UI**：Draft PR #47 已提交，依赖 #41 的 `self_check`、排名和来源契约；场景 3/6 的 UI 验收仍无法开始，负责人张锦昊。
- **#31 前端整体**：PR #43 仍是 draft；创建 → 工作区 UI 冒烟未测，负责人陈常群。
- **真实模型联调**：本机没有模型密钥，未执行；不能用固定回放结果替代。负责人庄凯堃。

## 结论

- API 级验收用例 6/6 通过，schema 测试 13/13 通过。
- 全量后端测试 59/61 通过；2 个失败是 Agent 与后端联调用例，不计为通过。
- 场景 3 失败，场景 6 的 UI 和真实模型联调未测；不在本记录中写成全部通过。
