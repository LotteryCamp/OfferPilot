-- 0014_model_transfer_consent_grants.sql
-- OfferPilot Alpha · 模型传输同意应用角色授权
--
-- 同意记录由应用角色读写；增量迁移负责新表授权，已部署环境无需重跑角色脚本。

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'offerpilot_app') THEN
        GRANT SELECT, INSERT, UPDATE ON core.model_transfer_consent TO offerpilot_app;
    END IF;
END $$;
