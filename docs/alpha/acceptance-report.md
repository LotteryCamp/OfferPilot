# Alpha 验收测试记录

- 日期：2026-11-20（随执行结果更新）
- 负责人：何慧渊
- 关联：issue #34、后端 PR #41（stacked base）
- 基线：`feat/business-process`（PR #41），合并后 rebase 到 `main`

## 测试环境

| 项 | 要求 |
| --- | --- |
| Python | 3.13 |
| 包管理 | uv |
| 数据库 | PostgreSQL 16；Alpha schema 迁移 `0001` 至 `0008` |
| 应用角色 | `offerpilot_app`，具备 `core`、`ops` 模式读写权限 |
| 测试库变量 | `OFFERPILOT_TEST_DATABASE_URL`、`OFFERPILOT_TEST_ADMIN_DATABASE_URL` |

```bash
cd backend
uv sync
export OFFERPILOT_TEST_DATABASE_URL='postgresql://offerpilot_app:<password>@127.0.0.1:5432/offerpilot_test'
export OFFERPILOT_TEST_ADMIN_DATABASE_URL='postgresql://postgres@127.0.0.1:5432/offerpilot_test'
uv run pytest tests/test_alpha_acceptance.py -q
```

## 验收矩阵

| issue #34 场景 | 覆盖方式 | 状态 |
| --- | --- | --- |
| 1. 创建个人事项并重新读取 | `test_acceptance_main_flow_creates_tasks`；并复用 #41 的 create/read 测试 | 待执行 |
| 2. 读取公开来源并取得出处信息 | 主流程测试登记 source/snapshot；真实来源读取模块见 PR #37 | 部分（API 已覆盖，来源读取待合入） |
| 3. Agent 生成带出处和缺口的候选计划 | 当前只验证 API 接受带 citation 的候选计划；Agent 生成见 PR #23 | 阻塞 |
| 4. 确认候选计划后任务出现且可读取 | 主流程测试覆盖确认、拒绝后的任务读取和幂等重放 | 待执行 |
| 5. 拒绝候选计划不创建任务 | `test_acceptance_reject_does_not_create_tasks` | 待执行 |
| 6. 来源读取失败时显示失败/缺口 | 当前用非法 URL 的 422 验证 API 失败路径；来源读取/UI 见 PR #37、前端 PR | 部分（API 失败已覆盖，UI 阻塞） |
| 缺字段 | `test_acceptance_missing_required_fields` | 待执行 |
| 跨用户/跨事项隔离 | `test_acceptance_cross_workspace_matter_is_hidden` | 待执行 |

## 当前执行记录

- 新增用例尚未在当前环境执行：当前工作机未安装 `uv` 和 PostgreSQL，无法启动真实测试库。
- PR #41 作者记录的验证：`uv run pytest tests -q` 10 项通过；`ruff`、`ty` 通过。
- 执行后请在下方补真实命令、通过/失败/未测数量和缺陷 Issue 链接，不要只写百分比。

| 日期 | 命令 | 通过 | 失败 | 未测/阻塞 | 备注 |
| --- | --- | ---: | ---: | --- | --- |
| 2026-11-20 | 待执行 | — | — | Agent #23、来源 #37、前端 | 本地 PostgreSQL 就绪后填写 |

## 已知阻塞

- **Agent 候选计划生成**：PR #23 未合入；当前只能验证 API 接受候选计划和 citation。
- **真实来源读取/失败反馈**：PR #37 未合入；当前只验证非法 URL 的 422。
- **UI 冒烟（创建 → 工作区）**：前端 PR 尚未出现；先做 API 级验证，UI 标记未测。
- **测试环境**：当前工作机缺少 uv/PostgreSQL；需在本地或具备 PostgreSQL 的 CI 环境执行。

## 下一步

1. 本地起 PostgreSQL 测试库，执行 `tests/test_alpha_acceptance.py` 和 `tests -q`；
2. 把真实通过/失败/未测结果填入上表；
3. 阻断问题按模块建 Issue：Agent #23、来源 #37、前端、后端 #41；
4. 11/21 阶段记录只使用已实际执行的结果。
