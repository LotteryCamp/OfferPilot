# 真实模型超时与恢复验证

## 验证范围

`backend/tests/test_agent_model_recovery.py` 通过正式 Agent API、公开 HTML 来源、实际模型服务及 PostgreSQL 验证超时恢复。测试默认关闭，显式启用后会调用配置的模型服务并产生费用。

覆盖两种恢复方式：同一应用内恢复超时配置，以及关闭旧应用并创建新应用后恢复。应用重建清除了进程内服务状态，数据库保持不变；该场景不代表操作系统进程崩溃测试。

每种方式依次检查：

1. 使用 0.001 秒模型请求超时读取公开通知，来源读取成功后模型调用返回 `TIMEOUT`。
2. 失败运行不保存候选计划或正式任务。
3. 恢复正常超时，使用原 `operation_id` 创建新的运行并保存候选。
4. 候选和每个计划项出处可查询，正式任务仍为空。
5. 对等待确认的运行重复提交原操作编号，返回同一运行及候选，候选数量不增加。
6. 原失败运行仍能读回失败状态与错误码。

本测试串行验证重试，不验证并发请求的原子去重；并发同键去重由 `backend/tests/test_agent_backend_flow.py` 的并发用例覆盖。本测试不覆盖已取消运行的同键重试、规划阶段单独超时、HTTP 500、非法 JSON 或截断输出。模型内容、引文或网络失败均按实际结果报告，测试不会将这些错误转换为通过。

## 前置条件

- PostgreSQL 16 或更新版本，独立测试库已执行当前全部迁移、基础种子和 `db/dev/roles.sql`。
- `OFFERPILOT_TEST_DATABASE_URL` 与 `OFFERPILOT_TEST_ADMIN_DATABASE_URL` 指向同一测试库；数据库名必须以 `_test` 结尾。
- 共享测试初始化会清理该测试库的业务数据，禁止指向日常联调或部署数据库。
- 模型地址、名称和密钥在本地配置，允许实际调用该模型服务。
- 网络可公开读取材料学院通知 `https://cl.fzu.edu.cn/info/1072/19700.htm`；学校域名解析为公网地址。

模型配置沿用 `Settings.from_env()` 与 `RuntimeConfig`，支持 `OFFERPILOT_CONFIG_FILE`，优先级为配置文件、环境变量、默认值。测试仅将超时写入临时目录下的 YAML；本地配置文件和密钥不被改写。测试库连接通过专用测试环境变量提供。

## 本地运行

在 `backend` 目录的 PowerShell 中，先配置测试库连接（以下为本地开发默认口令）：

```powershell
$env:OFFERPILOT_TEST_DATABASE_URL = "postgresql://offerpilot_app:offerpilot_dev_only@127.0.0.1:5432/offerpilot_test"
$env:OFFERPILOT_TEST_ADMIN_DATABASE_URL = "postgresql://postgres:postgres@127.0.0.1:5432/offerpilot_test"
```

`.env` 保留本地真实模型配置。启用并运行：

```powershell
$env:OFFERPILOT_MODEL_LIVE_RECOVERY = "1"
uv run --locked --env-file .env python -m pytest tests/test_agent_model_recovery.py -q
```

完成后移除本终端的启用开关：

```powershell
Remove-Item Env:OFFERPILOT_MODEL_LIVE_RECOVERY -ErrorAction SilentlyContinue
```

无需启动单独的后端服务，测试负责创建 API 应用。两组测试均使用真实通知及真实模型输出，恢复调用可能持续数分钟。超时由客户端配置触发，不证明外部服务已取消已发出的请求。

## 结果解释

- 未启用开关时显示跳过，不计为真实联调通过。
- 已启用但缺少必要配置时失败，不静默退回本地回包。
- 来源错误、模型鉴权或服务错误、引文校验失败、恢复请求超时均需定位并重新验证。
- 预期两组通过后，分别记录代码提交号、模型、命令和实际测试结果。运行响应及会话日志保存在仓库外；不提交密钥、Cookie 或个人材料。
- 公告中的期限可能已过；本测试停在候选保存，不确认候选，不生成正式任务。
