-- dev/roles.sql
-- 本地/验收环境的应用角色（开发默认口令，禁止用于生产）。由管理员执行一次。
--
-- 应用必须用这个非所有者角色连接；表所有者（通常是 postgres）会绕过 RLS。
-- 生产环境请改为强口令，并通过密钥管理注入，不要把口令写进仓库。

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'offerpilot_app') THEN
        CREATE ROLE offerpilot_app LOGIN PASSWORD 'offerpilot_dev_only';
    END IF;
END $$;

GRANT USAGE ON SCHEMA core, ops TO offerpilot_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA core, ops TO offerpilot_app;

ALTER DEFAULT PRIVILEGES IN SCHEMA core, ops
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO offerpilot_app;

COMMENT ON ROLE offerpilot_app IS 'OfferPilot Alpha 应用角色；受 RLS 约束，非表所有者';