-- 0017_login_throttle.sql
-- OfferPilot · 登录限流与临时账户锁定
--
-- 每个计数桶保留一行，固定窗口到期后在原行重置。
-- 桶键只保存规范化 IP 网段或邮箱 SHA-256 摘要，不保存明文邮箱。

CREATE TABLE core.login_throttle (
    bucket_key    text PRIMARY KEY,
    window_start  timestamptz NOT NULL,
    attempts      integer NOT NULL DEFAULT 0,
    blocked_until timestamptz,
    updated_at    timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_login_throttle_key CHECK (
        bucket_key ~ '^(ip|email):[0-9A-Za-z:._/-]+$'
    ),
    CONSTRAINT ck_login_throttle_attempts CHECK (attempts >= 0)
);

COMMENT ON TABLE core.login_throttle IS
    '登录限流与临时锁定计数；按 IP 网段与邮箱摘要分桶';
COMMENT ON COLUMN core.login_throttle.bucket_key IS
    'ip: 前缀为规范化 IP 或 /64 网段；email: 前缀为邮箱 SHA-256';
COMMENT ON COLUMN core.login_throttle.blocked_until IS
    '邮箱桶的临时锁定结束时间；IP 桶使用固定窗口';

CREATE INDEX ix_login_throttle_updated ON core.login_throttle (updated_at);

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'offerpilot_app') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON core.login_throttle
            TO offerpilot_app;
    END IF;
END $$;
