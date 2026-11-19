# Alpha 验收测试记录

- 执行日期：2026-11-19 23:35（Asia/Shanghai）
- 负责人：何慧渊
- 关联：issue #34、后端 PR #41、测试 PR #42
- 代码基线：`test/alpha-acceptance`（stacked on PR #41 `feat/business-process`）

## 测试环境

| 项 | 实际值 |
| --- | --- |
| 操作系统 | Windows |
| PostgreSQL | 16.16，端口 5433，数据目录 `E:\PostgreSQL\data` |
| Python | 3.13（uv 管理） |
| uv | 0.13.9 |
| 测试数据库 | `offerpilot_test` |
| 迁移 | `0001` 至 `0008` 全部应用 |
| 参考数据 | `db/migrate.py seed` 已执行 |
| 应用角色 | `offerpilot_app`（`db/dev/roles.sql`） |

```bash
cd backend
uv sync
export OFFERPILOT_TEST_DATABASE_URL='postgresql://offerpilot_app:offerpilot_dev_only@127.0.0.1:5433/offerpilot_test'
export OFFERPILOT_TEST_ADMIN_DATABASE_URL='postgresql://postgres@127.0.0.1:5433/offerpilot_test'
uv run pytest tests/test_alpha_acceptance.py -q
```

## 实际执行结果

| 命令 | 结果 |
| --- | --- |
| `uv run pytest tests/test_alpha_acceptance.py -q` | **6 passed in 1.80s** |
| `uv run pytest tests -q` | **38 passed in 5.37s** |

## 验收矩阵

| issue #34 场景 | 覆盖方式 | 状态 |
| --- | --- | --- |
| 1. 创建个人事项并重新读取 | `test_acceptance_main_flow_creates_tasks`；并复用 #41 create/read 测试 | 通过 |
| 2. 读取公开来源并取得出处信息 | 主流程测试登记 source/snapshot 并校验 locator；来源读取测试在全量 38 项中通过 | 通过 |
| 3. Agent 生成带出处和缺口的候选计划 | Agent #23 已合入并通过 14 项单测；真实数据库端到端依赖 #41 合并后联调 | 部分：合同/单测通过，E2E 未测 |
| 4. 确认候选计划后任务出现且可读取 | 主流程测试覆盖确认、幂等重放和任务读取 | 通过 |
| 5. 拒绝候选计划不创建任务 | `test_acceptance_reject_does_not_create_tasks` | 通过 |
| 6. 来源读取失败时显示失败/缺口 | 非法 URL 的 422 只覆盖请求校验；来源 #37 已合入，fetch/read 失败路径和 UI 仍未覆盖，UI 见 #43 | 部分：仅 URL 校验通过；来源读取失败未测 |
| 缺字段 | `test_acceptance_missing_required_fields` | 通过 |
| 非法来源 URL | `test_acceptance_invalid_source_url` | 通过 |
| 未知计划 | `test_acceptance_unknown_plan_returns_404` | 通过 |
| 跨用户/跨工作区隔离 | `test_acceptance_cross_workspace_matter_is_hidden` | 通过 |

## 缺陷/阻塞

- **Agent ↔ 后端 E2E**：Agent #23 已合入，真实 PostgreSQL 端到端待 PR #41 合并后联调；场景 3 完整链路未测。
- **UI 冒烟（创建 → 工作区）**：前端 #43 仍为 draft，未合并；UI 冒烟未测。
- **来源读取失败**：非法 URL 只覆盖请求校验，fetch/read 失败路径与 UI 提示未测；待 #43 与后端联调后补测。

## 结论

- API 级 Alpha 核心流程、拒绝、缺字段、非法来源、未知计划、跨工作区隔离均已实际执行通过。
- 全量后端测试 38 项通过。
- 场景 3 和 UI 相关场景仍需等 #41 合并与 #43 完成，不在本记录中写成已通过。
