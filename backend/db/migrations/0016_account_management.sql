-- 0016_account_management.sql
-- OfferPilot · 账户类型、登录会话与多用户认证
--
-- 账户分普通用户（applicant）与管理员（admin）。注册后账户立即生效。
-- 会话令牌只保存 SHA-256 摘要；停用、删除或重置密码时撤销全部会话。
-- 已有账户缺少个人工作区时，在本迁移中补建。

ALTER TABLE core.app_user
    DROP CONSTRAINT ck_app_user_type;

ALTER TABLE core.app_user
    ADD CONSTRAINT ck_app_user_type
    CHECK (account_type IN ('applicant', 'admin'));

COMMENT ON TABLE core.app_user IS
    '登录主体；普通用户为 applicant，管理员为 admin';

CREATE TABLE core.user_session (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     uuid NOT NULL,
    token_hash  char(64) NOT NULL,
    remember    boolean NOT NULL DEFAULT false,
    created_at  timestamptz NOT NULL DEFAULT now(),
    expires_at  timestamptz NOT NULL,
    revoked_at  timestamptz,
    CONSTRAINT fk_user_session_user FOREIGN KEY (user_id)
        REFERENCES core.app_user (id) ON DELETE CASCADE,
    CONSTRAINT uq_user_session_token UNIQUE (token_hash),
    CONSTRAINT ck_user_session_token CHECK (token_hash ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_user_session_expiry CHECK (expires_at > created_at)
);

COMMENT ON TABLE core.user_session IS
    '服务端登录会话；浏览器持有原始令牌，数据库只保存 SHA-256 摘要';
COMMENT ON COLUMN core.user_session.remember IS
    '是否使用持久 Cookie；服务端有效期由创建时确定';
COMMENT ON COLUMN core.user_session.revoked_at IS
    '显式退出、停用、删除或重置密码后的撤销时间';

INSERT INTO core.workspace (id, owner_id)
SELECT gen_random_uuid(), u.id
FROM core.app_user u
WHERE NOT EXISTS (
    SELECT 1
    FROM core.workspace w
    WHERE w.owner_id = u.id
);

CREATE INDEX ix_user_session_user ON core.user_session (user_id, created_at DESC);
CREATE INDEX ix_user_session_expiry ON core.user_session (expires_at);

-- 进程重启后由应用调用；跨工作区更新所有未完成运行。
CREATE FUNCTION core.mark_interrupted_agent_runs() RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = core, pg_temp
AS $$
DECLARE
    affected integer;
BEGIN
    UPDATE core.agent_run
       SET status = 'interrupted',
           updated_at = now()
     WHERE status = 'running';
    GET DIAGNOSTICS affected = ROW_COUNT;
    RETURN affected;
END;
$$;

COMMENT ON FUNCTION core.mark_interrupted_agent_runs() IS
    '服务启动时将所有运行中的 Agent 运行标记为已中断，绕过工作区行级策略';

REVOKE ALL ON FUNCTION core.mark_interrupted_agent_runs() FROM PUBLIC;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'offerpilot_app') THEN
        GRANT SELECT (
            id, email, display_name, password_hash, account_type, status,
            created_at, updated_at, deleted_at
        ) ON core.app_user TO offerpilot_app;
        GRANT INSERT (
            id, email, display_name, password_hash, account_type, status,
            created_at, updated_at, deleted_at
        ) ON core.app_user TO offerpilot_app;
        GRANT UPDATE (
            password_hash, account_type, status, deleted_at, updated_at
        ) ON core.app_user TO offerpilot_app;
        GRANT INSERT ON core.workspace TO offerpilot_app;
        GRANT SELECT, INSERT, UPDATE, DELETE ON core.user_session TO offerpilot_app;
        GRANT EXECUTE ON FUNCTION core.mark_interrupted_agent_runs()
            TO offerpilot_app;
    END IF;
END $$;
