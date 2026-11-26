# 运行配置

| 项目 | 内容 |
| :--- | :--- |
| 适用范围 | 多用户后端 |
| 配置文件 | 由 `OFFERPILOT_CONFIG_FILE` 指定，YAML，UTF-8 |
| 管理员接口 | `GET/PATCH /api/v1/admin/settings` |
| 相关文档 | [账户、登录与管理员接口](accounts.md)、[后端说明](../../backend/README.md) |

## 1. 配置来源与优先级

配置由三层合并得到，优先级从高到低：

1. 运行配置文件中的字段。
2. 进程环境变量。
3. 代码默认值。

未设置 `OFFERPILOT_CONFIG_FILE` 时，服务只读取环境变量，管理员接口仍可读取当前生效值，写入返回 `409 config_file_not_configured`。

## 2. 文件结构

配置文件只接受可热更新字段。以下字段之外的内容会使整个文件校验失败：

```yaml
model:
  provider: OpenAI 兼容模型服务
  name: gpt-4.1-mini
  api_url: https://api.example.com/v1
  api_key: sk-...
  timeout_seconds: 180
auth:
  session_ttl_seconds: 43200
  remember_session_ttl_seconds: 2592000
  cookie_secure: false
  login_ip_window_seconds: 300
  login_ip_limit: 60
  login_email_window_seconds: 900
  login_email_limit: 5
  login_lock_seconds: 900
timezone: Asia/Shanghai
```

| 字段 | 类型 | 约束 | 对应环境变量 |
| :--- | :--- | :--- | :--- |
| `model.provider` | string | 无 | `OFFERPILOT_MODEL_PROVIDER` |
| `model.name` | string | 无 | `OFFERPILOT_MODEL_NAME` |
| `model.api_url` | string | 无 | `OFFERPILOT_MODEL_API_URL` |
| `model.api_key` | string | 不得只包含空白字符 | `OFFERPILOT_MODEL_API_KEY` |
| `model.timeout_seconds` | number | 大于 0 | `OFFERPILOT_MODEL_TIMEOUT_SECONDS` |
| `auth.session_ttl_seconds` | integer | 大于 0 | `OFFERPILOT_SESSION_TTL_SECONDS` |
| `auth.remember_session_ttl_seconds` | integer | 大于 0 | `OFFERPILOT_REMEMBER_SESSION_TTL_SECONDS` |
| `auth.cookie_secure` | boolean | 无 | `OFFERPILOT_COOKIE_SECURE` |
| `auth.login_ip_window_seconds` | integer | 大于 0 | `OFFERPILOT_LOGIN_IP_WINDOW_SECONDS` |
| `auth.login_ip_limit` | integer | 大于等于 0 | `OFFERPILOT_LOGIN_IP_LIMIT` |
| `auth.login_email_window_seconds` | integer | 大于 0 | `OFFERPILOT_LOGIN_EMAIL_WINDOW_SECONDS` |
| `auth.login_email_limit` | integer | 大于等于 0 | `OFFERPILOT_LOGIN_EMAIL_LIMIT` |
| `auth.login_lock_seconds` | integer | 大于 0 | `OFFERPILOT_LOGIN_LOCK_SECONDS` |
| `timezone` | string | 合法 IANA 时区 | `OFFERPILOT_TIMEZONE` |

数据库连接、监听地址、监听端口与 API 前缀不可热更新，出现在文件中直接校验失败。

## 3. 启动与重载

| 场景 | 行为 |
| :--- | :--- |
| 文件存在且合法 | 启动时读取，覆盖环境变量 |
| 文件存在但非法 | 启动失败，错误信息列出全部校验问题 |
| 文件不存在 | 按环境变量启动并记录警告；首次管理员保存时创建 |
| 运行中文件变化 | 每次 HTTP 请求比较文件修改时间与大小，约 1 秒缓存；变化后重新读取、校验并原子替换进程内快照 |
| 重载校验失败 | 保留上一份有效配置并记录错误；文件再次变化时重试 |
| 文件运行中被删除 | 保留当前内存配置并记录错误 |

文件修改时间与大小都未变化时不重复读取。管理员通过接口保存时立即替换内存快照，无需等待下一次请求。读取期间文件被替换时会重新读取，内存快照与版本信息始终对应实际载入的内容；多次尝试仍无法取得稳定内容时按校验失败处理。管理员保存后记录的是本次写入内容的版本信息。

## 4. 生效语义

| 配置 | 生效时点 | 不受影响 |
| :--- | :--- | :--- |
| 模型服务商、名称、地址、密钥、超时 | 下一次模型调用；下一次读取模型传输同意披露 | 已生成的运行结果、已签署的同意记录 |
| 登录限流参数 | 下一次登录请求的检查 | 已存在的计数窗口记录，按新参数继续计算 |
| 会话有效期 | 下一次注册或登录 | 已签发会话的 `expires_at` |
| Cookie Secure | 之后签发的 Cookie | 浏览器已有 Cookie |
| 时区 | 之后的期限与“今天”计算 | 已存期限字符串与历史结果 |

一次 Agent 运行在启动或恢复时固定一份配置快照，用于决策与持久化；模型调用每次使用当时的配置。管理员自身的当前会话同样受上述规则约束。

时区用于把带时刻的官方期限换算为官方期限日期、校验建议准备日、判断仅日期期限是否已过，以及计算业务“今天”。候选计划创建、确认与 Agent 运行校验使用同一套时区规则。

## 5. 管理员接口

以下接口要求管理员会话，普通用户访问返回 `403 admin_required`。

### 5.1 读取当前配置

`GET /api/v1/admin/settings`

```json
{
  "config_file": "/etc/offerpilot/config.yaml",
  "writable": true,
  "settings": {
    "timezone": "Asia/Shanghai",
    "model": {
      "provider": "OpenAI 兼容模型服务",
      "name": "gpt-4.1-mini",
      "api_url": "https://api.example.com/v1",
      "api_key_configured": true,
      "timeout_seconds": 180
    },
    "auth": {
      "session_ttl_seconds": 43200,
      "remember_session_ttl_seconds": 2592000,
      "cookie_secure": false,
      "login_ip_window_seconds": 300,
      "login_ip_limit": 60,
      "login_email_window_seconds": 900,
      "login_email_limit": 5,
      "login_lock_seconds": 900
    }
  }
}
```

`config_file` 未配置时为 `null`，`writable` 为 `false`。模型密钥不返回，只报告 `api_key_configured`；环境变量中的密钥去除首尾空白后为空时报告为未配置。

### 5.2 修改配置

`PATCH /api/v1/admin/settings`

请求体只包含需要修改的字段；未提交的字段保持当前生效值。

```json
{
  "model": {
    "name": "gpt-4.1",
    "api_key": "sk-...",
    "timeout_seconds": 240
  },
  "auth": {
    "login_email_limit": 10
  },
  "timezone": "Asia/Shanghai"
}
```

| 规则 | 行为 |
| :--- | :--- |
| 部分字段 | 只写入提交的字段，其他文件内容保持不变 |
| 并发保存 | 通过配置文件同目录的锁文件串行执行，后到的保存会重新读取文件再合并 |
| `model.api_key` 提交非空字符串 | 写入文件 |
| `model.api_key` 提交空字符串 | 删除文件中的密钥覆盖，回退环境变量 |
| `model.api_key` 提交仅含空白字符 | `422 validation_error`，文件不写入 |
| `model.api_key` 未提交 | 保持原值 |
| 保存成功 | `200`，返回与读取接口相同的结构 |
| 未设置 `OFFERPILOT_CONFIG_FILE` | `409 config_file_not_configured` |
| 字段非法或文件现有内容非法 | `422 validation_error`，`details.issues` 列出全部问题，文件不写入 |
| 写盘失败 | `500 config_write_failed`，内存配置保持原值 |

写入使用同目录临时文件与 `os.replace` 原子替换，权限设为 `0600`。文件中的值只覆盖对应字段，不会把环境变量值固化到文件中。

## 6. 部署注意

- 多进程部署时每个进程独立检测文件变化；管理员保存由处理该请求的进程立即生效，其他进程在下一次请求时读取。所有进程须挂载同一份文件。
- 管理员保存时在配置文件同目录创建 `.<文件名>.lock` 锁文件，多个进程的保存请求串行执行；每次保存在持有锁期间重新读取文件、合并本次修改后写入，因此并发保存不会互相覆盖。锁文件由程序自动创建，内容为空，所在目录须可写并与所有进程共享。手工编辑配置文件不经过该锁，应避免与管理接口同时写入。
- 配置文件包含模型密钥，权限应为 `0600`，并排除在版本控制之外。
- 管理员修改配置目前不记录审计日志，与其他管理员操作一致。
- 校验失败不会中断服务，错误写入服务日志；启动阶段的非法文件会使进程退出。
