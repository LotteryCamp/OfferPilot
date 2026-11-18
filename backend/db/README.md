# Alpha 数据库迁移（backend/db）

本目录提供 Alpha 首版数据库结构、版本化迁移、参考数据、迁移执行器和集成测试。
字段语义以 `docs/development/alpha-scope-contract.md` 为准，物理结构说明见
`docs/backend/alpha-schema.md`。

## 目录

```text
backend/db/
├─ migrations/            版本化 DDL，按编号顺序执行
├─ seed/                  参考数据与演示数据
├─ dev/roles.sql          本地应用角色与授权
├─ tests/                 数据库集成测试
├─ migrate.py             迁移执行器
├─ requirements.txt
└─ docker-compose.yml
```

## 环境

- PostgreSQL 16 及以上
- Python 3.13 及以上
- `python -m pip install -r backend/db/requirements.txt`

## 从空库初始化

```bash
cd backend/db
docker compose up -d

export DATABASE_URL='postgresql://postgres:postgres@127.0.0.1:5432/offerpilot'
python migrate.py migrate
python migrate.py seed
python migrate.py status
```

本机 PostgreSQL：

```bash
createdb offerpilot
export DATABASE_URL='postgresql://postgres@127.0.0.1:5432/offerpilot'
python migrate.py migrate
python migrate.py seed
```

演示数据：

```bash
python migrate.py seed --demo
```

## 应用角色

迁移启用行级安全。API 使用非所有者角色连接：

```bash
psql "$DATABASE_URL" -f dev/roles.sql
```

业务请求取得工作区后设置：

```sql
SET app.current_workspace_id = '<workspace-uuid>';
```

变量未设置时策略不匹配任何行。数据库所有者会绕过 RLS，迁移与后台任务使用所有者连接。

## 迁移规则

1. 文件名格式为 `NNNN_snake_case.sql`，编号连续，只追加。
2. 每个迁移在独立事务中执行，成功后写入 `ops.schema_version`。
3. 重复执行跳过已应用版本；校验和不一致或数据库存在缺失版本时退出码 2。
4. 迁移期间持有 advisory lock。
5. 种子脚本使用 `ON CONFLICT`，可重复执行。
6. 回滚使用迁移前快照或新增反向迁移。

常用命令：

```bash
python migrate.py status
python migrate.py migrate --dry-run
python migrate.py migrate
python migrate.py seed --demo
```

## 测试

```bash
export PGTEST_ADMIN_DSN='postgresql://postgres@127.0.0.1:5432/postgres'
python tests/test_alpha_schema.py -v
```

测试覆盖事项持久化、来源与证据链、计划项来源、拒绝与确认、幂等重放、
任务唯一性、完成证据、跨工作区 RLS、级联删除和计划状态约束。

## 约定

- 时间字段使用 `timestamptz`，接口输出 ISO 8601。
- 主键由应用层生成 UUIDv7，数据库 `gen_random_uuid()` 兜底。
- 未接入对象存储时，`ops.snapshot.object_key` 使用 `inline:<sha256>`，
  正文放在 `extraction->>'text'`。
- 事项类型编码由参考数据提供，不在代码中写死。