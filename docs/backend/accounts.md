# 账户、登录与管理员接口

| 项目 | 内容 |
| :--- | :--- |
| 接口前缀 | `/api/v1` |
| 数据格式 | JSON，UTF-8 |
| 适用范围 | Alpha 多用户后端 |
| 数据库结构 | 迁移 `0016_account_management.sql` |
| 业务接口 | [Alpha 核心业务流程 API](api.md) |

## 1. 账户模型

账户分为普通用户与管理员。每个账户拥有一个个人工作区，事项、个人事实、模型传输同意与任务均在个人工作区内隔离。

| 对象 | 字段 | 说明 |
| :--- | :--- | :--- |
| `core.app_user` | `email` | 唯一；服务端去除首尾空白并转为小写 |
| `core.app_user` | `password_hash` | Argon2id 摘要；不保存明文 |
| `core.app_user` | `account_type` | `applicant` 为普通用户，`admin` 为管理员 |
| `core.app_user` | `status` | `pending`、`active`、`disabled` |
| `core.app_user` | `deleted_at` | 软删除时间；删除后保留账户及业务数据 |
| `core.workspace` | `owner_id` | 与账户 1:1 |
| `core.user_session` | `token_hash` | 会话令牌的 SHA-256 摘要；原始令牌只保存在浏览器 |
| `core.user_session` | `remember` | 是否使用持久 Cookie |
| `core.user_session` | `expires_at` | 服务端会话失效时间 |
| `core.user_session` | `revoked_at` | 退出、停用、删除或重置密码后的撤销时间 |

注册成功后账户立即生效，不需要邮件验证或管理员审批。注册同时创建个人工作区和登录会话，响应携带登录 Cookie。

## 2. 认证方式

业务接口使用服务端会话 Cookie。客户端不需要发送 `Authorization` 头，也不能自造用户或工作区标识。

| Cookie | 属性 |
| :--- | :--- |
| 名称 | `offerpilot_session` |
| `HttpOnly` | 是 |
| `SameSite` | `Lax` |
| `Path` | `/` |
| `Secure` | 由 `OFFERPILOT_COOKIE_SECURE` 控制；HTTPS 部署必须为 `true` |
| `Max-Age` | 仅在 `remember=true` 时设置为持久会话有效期 |

普通登录创建 12 小时有效的服务端会话，`remember=true` 创建 30 天有效的服务端会话。两者都受服务端 `expires_at` 约束，浏览器 Cookie 过期不代表服务端会话仍然有效。有效期可通过环境变量调整：

| 环境变量 | 默认值 |
| :--- | :--- |
| `OFFERPILOT_SESSION_TTL_SECONDS` | `43200` |
| `OFFERPILOT_REMEMBER_SESSION_TTL_SECONDS` | `2592000` |
| `OFFERPILOT_COOKIE_SECURE` | `false` |

每次请求按 Cookie 中的原始令牌查询会话，并校验会话未撤销、未过期、账户为 `active` 且未删除。校验失败统一返回 `401 authentication_required`。服务端只保存令牌摘要，数据库泄露不会直接得到可用会话令牌。

前端开发服务器通过同源 `/api` 代理访问后端。跨源直连时，浏览器请求需要携带凭据，并由部署层配置精确的 CORS 来源；当前服务按同源部署。

## 3. 认证接口

### 3.1 注册

`POST /api/v1/auth/register`

请求字段：

| 字段 | 类型 | 必填 | 约束 |
| :--- | :--- | :--- | :--- |
| `email` | string | 是 | 合法邮箱，最长 160 字符 |
| `display_name` | string | 是 | 去除首尾空白后 1—60 字符 |
| `password` | string | 是 | 8—128 字符 |

响应 `201`：

```json
{
  "user": {
    "id": "00000000-0000-4000-8000-000000000101",
    "email": "user@example.com",
    "display_name": "示例用户",
    "account_type": "applicant",
    "status": "active",
    "workspace_id": "00000000-0000-4000-8000-000000000102",
    "created_at": "2026-11-23T08:00:00+00:00",
    "updated_at": "2026-11-23T08:00:00+00:00",
    "deleted_at": null
  },
  "session": {
    "expires_at": "2026-11-23T20:00:00+00:00",
    "remember": false
  }
}
```

响应同时设置 `offerpilot_session` Cookie。邮箱已存在时返回 `409 email_already_registered`，包括已软删除账户占用的邮箱。

### 3.2 登录

`POST /api/v1/auth/login`

请求字段：

| 字段 | 类型 | 必填 | 默认值 | 约束 |
| :--- | :--- | :--- | :--- | :--- |
| `email` | string | 是 | 无 | 合法邮箱 |
| `password` | string | 是 | 无 | 1—128 字符 |
| `remember` | boolean | 否 | `false` | 是否使用 30 天持久会话 |

响应 `200` 与注册响应结构相同。邮箱不存在、密码错误、账户停用或已删除时统一返回 `401 invalid_credentials`，不区分具体原因。

### 3.3 退出

`POST /api/v1/auth/logout`

撤销当前 Cookie 对应的会话并清除 Cookie。响应 `204`。重复退出或 Cookie 已失效时同样返回 `204`。

### 3.4 当前账户

`GET /api/v1/auth/me`

响应 `200`：

```json
{
  "user": {
    "id": "00000000-0000-4000-8000-000000000101",
    "email": "user@example.com",
    "display_name": "示例用户",
    "account_type": "applicant",
    "status": "active",
    "workspace_id": "00000000-0000-4000-8000-000000000102",
    "created_at": "2026-11-23T08:00:00+00:00",
    "updated_at": "2026-11-23T08:00:00+00:00",
    "deleted_at": null
  },
  "session": {
    "expires_at": "2026-11-23T20:00:00+00:00",
    "remember": false
  }
}
```

### 3.5 修改密码

`POST /api/v1/auth/password`

请求字段：

| 字段 | 类型 | 必填 | 约束 |
| :--- | :--- | :--- | :--- |
| `current_password` | string | 是 | 1—128 字符 |
| `new_password` | string | 是 | 8—128 字符，且不同于当前密码 |

当前密码不正确时返回 `401 invalid_current_password`。修改成功后撤销该账户的全部会话，响应 `204` 并清除当前 Cookie；用户需要重新登录。

## 4. 角色与权限

| 能力 | 普通用户 | 管理员 |
| :--- | :--- | :--- |
| 注册、登录、退出、修改本人密码 | 是 | 是 |
| 管理本人事项、事实、来源、候选与任务 | 是 | 是 |
| 读取本人账户信息 | 是 | 是 |
| 列出账户、调整状态与角色 | 否 | 是 |
| 重置他人密码、软删除账户 | 否 | 是 |
| 读取其他用户的私人业务数据 | 否 | 否 |

管理员身份只扩展账户管理权限。管理员访问业务接口时仍使用自己的个人工作区，行级安全策略按管理员本人的工作区过滤数据。

## 5. 管理员账户接口

以下接口均要求管理员会话，普通用户访问返回 `403 admin_required`。

### 5.1 账户列表

`GET /api/v1/admin/users`

| 查询参数 | 类型 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- |
| `search` | string | 无 | 按邮箱或显示名称模糊搜索，最长 160 字符 |
| `status` | string | 无 | `pending`、`active` 或 `disabled` |
| `account_type` | string | 无 | `applicant` 或 `admin` |
| `include_deleted` | boolean | `false` | 是否包含软删除账户 |
| `limit` | integer | `50` | 1—100 |
| `offset` | integer | `0` | 从 0 开始 |

响应 `200`：

```json
{
  "users": [
    {
      "id": "00000000-0000-4000-8000-000000000101",
      "email": "user@example.com",
      "display_name": "示例用户",
      "account_type": "applicant",
      "status": "active",
      "workspace_id": "00000000-0000-4000-8000-000000000102",
      "created_at": "2026-11-23T08:00:00+00:00",
      "updated_at": "2026-11-23T08:00:00+00:00",
      "deleted_at": null
    }
  ],
  "total": 1,
  "limit": 50,
  "offset": 0
}
```

### 5.2 调整账户状态

`PATCH /api/v1/admin/users/{user_id}/status`

请求字段：

| 字段 | 类型 | 必填 | 取值 |
| :--- | :--- | :--- | :--- |
| `status` | string | 是 | `active` 或 `disabled` |

响应 `200` 为 `{ "user": {...} }`。停用账户时撤销其全部会话。管理员不能通过该接口修改自己的状态。

### 5.3 调整账户角色

`PATCH /api/v1/admin/users/{user_id}/role`

请求字段：

| 字段 | 类型 | 必填 | 取值 |
| :--- | :--- | :--- | :--- |
| `account_type` | string | 是 | `applicant` 或 `admin` |

响应 `200` 为 `{ "user": {...} }`。角色在每次请求认证时重新读取，变更立即影响后续请求。管理员不能通过该接口修改自己的角色。

### 5.4 重置密码

`POST /api/v1/admin/users/{user_id}/password-reset`

请求字段：

| 字段 | 类型 | 必填 | 约束 |
| :--- | :--- | :--- | :--- |
| `new_password` | string | 是 | 8—128 字符 |

响应 `200` 为 `{ "user": {...} }`。重置成功后撤销目标账户的全部会话。管理员不能通过该接口重置自己的密码，应使用 `POST /api/v1/auth/password`。

### 5.5 删除账户

`DELETE /api/v1/admin/users/{user_id}`

账户被置为 `disabled` 并记录 `deleted_at`，业务数据保留，全部会话撤销。响应 `204`。重复删除已删除账户时同样返回 `204`。

管理员不能删除自己。系统始终保留至少一个 `active` 且未删除的管理员；违反时返回 `409 last_admin_required`。

## 6. 首个管理员

首个管理员由命令行创建，不能通过公开注册接口创建。命令读取 `OFFERPILOT_ADMIN_PASSWORD` 作为初始密码，密码不通过命令行参数传递。

```bash
cd backend
export OFFERPILOT_DATABASE_URL='postgresql://offerpilot_app:<password>@127.0.0.1:5432/offerpilot'
export OFFERPILOT_ADMIN_PASSWORD='<初始密码>'
uv run offerpilot-admin create \
  --email admin@example.com \
  --display-name 系统管理员
```

命令成功时输出账户邮箱与标识。邮箱已存在时退出码为 `1`；密码缺失或参数校验失败时退出码为 `2`。管理员创建后立即生效，可通过登录接口使用。

初始化顺序：

1. 执行 `uv run python db/migrate.py migrate` 应用迁移。
2. 首次部署执行 `db/dev/roles.sql` 创建应用角色与基础授权。
3. 按需执行 `uv run python db/migrate.py seed --demo` 写入演示数据。
4. 使用上述命令创建首个管理员。
5. 启动 API，通过登录接口建立会话。

## 7. 数据边界

每个账户拥有独立个人工作区。请求认证得到 `CurrentUser` 后，业务服务在事务中设置 `app.current_workspace_id`，行级安全策略按该工作区过滤事项、要求、候选计划、计划项、任务及其关联数据。个人事实与模型传输同意同时校验记录所有者与工作区所有者。

管理员账户列表只返回账户元数据，不提供跨账户事项、事实、材料或任务读取能力。越界读取按不存在处理，返回 `404` 对应业务错误码。

## 8. 错误码

| HTTP 状态 | `code` | 含义 |
| :--- | :--- | :--- |
| 401 | `authentication_required` | 缺少有效会话，或会话已过期、撤销、账户停用 |
| 401 | `invalid_credentials` | 邮箱或密码错误，账户停用或已删除 |
| 401 | `invalid_current_password` | 修改密码时当前密码不正确 |
| 403 | `admin_required` | 当前账户不具备管理员身份 |
| 404 | `user_not_found` | 管理员接口指定的账户不存在 |
| 409 | `email_already_registered` | 邮箱已注册 |
| 409 | `self_administration_forbidden` | 管理员试图通过管理员接口实际修改自己的账户 |
| 409 | `last_admin_required` | 操作会导致没有有效管理员 |
| 409 | `account_deleted` | 目标账户已软删除 |
| 422 | `validation_error` | 请求字段未通过校验 |

## 9. 部署与兼容影响

- 除 `/healthz` 外，所有业务接口都要求登录；未携带有效 Cookie 的请求返回 `401 authentication_required`。
- 固定演示用户与工作区配置已移除。依赖 `OFFERPILOT_DEMO_USER_ID`、`OFFERPILOT_DEMO_WORKSPACE_ID` 或 `demo_identity_missing` 的客户端与部署脚本需要更新。
- HTTPS 部署必须设置 `OFFERPILOT_COOKIE_SECURE=true`，并让前端与 API 同源，或由部署层提供精确的 CORS 凭据策略。
- 服务启动时会将数据库中所有 `running` 状态的 Agent 运行标记为 `interrupted`。多进程部署需要保证只有一个进程执行该启动步骤，或改用实例级运行心跳后再扩展为多实例。
- 演示种子账户为 `demo@example.com`，口令为 `demo-password-2026`，仅用于本地演示数据。种子脚本会把旧版不可登录的演示账户升级为可登录账户。
- 当前不提供邮件验证、找回密码、MFA、登录限流、账户锁定、管理员操作审计、个人信息编辑与第三方登录。

## 10. 验证

账户接口集成测试覆盖注册即用、重复邮箱、普通与持久会话、Cookie 属性、退出、改密撤销、管理员列表与筛选、状态与角色调整、密码重置、软删除、自操作保护、管理员数据边界与匿名请求拒绝。

```bash
cd backend
export OFFERPILOT_TEST_DATABASE_URL='postgresql://offerpilot_app:<password>@127.0.0.1:5432/offerpilot_test'
export OFFERPILOT_TEST_ADMIN_DATABASE_URL='postgresql://postgres@127.0.0.1:5432/offerpilot_test'
uv run pytest tests/test_auth_api.py -q
```
