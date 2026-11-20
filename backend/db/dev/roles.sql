-- dev/roles.sql
-- 本地/验收环境的应用角色（开发默认口令，禁止用于生产）。由管理员执行一次。
--
-- 应用必须用这个非所有者角色连接；表所有者会绕过 RLS。
-- 生产环境请改为强口令，并通过密钥管理注入，不要把口令写进仓库。

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'offerpilot_app') THEN
        CREATE ROLE offerpilot_app LOGIN PASSWORD 'offerpilot_dev_only';
    END IF;
END $$;

GRANT USAGE ON SCHEMA core, ops TO offerpilot_app;

-- 账户与工作区只读；password_hash 不授予应用角色。
GRANT SELECT (id, email, display_name, account_type, status, created_at, updated_at, deleted_at)
    ON core.app_user TO offerpilot_app;
GRANT SELECT ON core.workspace, core.matter_type, core.template_version TO offerpilot_app;
GRANT SELECT ON core.v_matter_overview, core.v_plan_detail, core.v_task_list TO offerpilot_app;

-- 共享来源层：应用登记来源、追加快照与证据；快照与证据写入后不可修改。
GRANT SELECT, INSERT, UPDATE ON ops.source TO offerpilot_app;
GRANT SELECT, INSERT, UPDATE ON ops.snapshot TO offerpilot_app;
GRANT SELECT, INSERT ON ops.evidence TO offerpilot_app;

-- 事项聚合：应用只做常规增改；删除由管理任务执行。
GRANT SELECT, INSERT, UPDATE ON core.matter, core.requirement TO offerpilot_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON core.requirement_self_check TO offerpilot_app;
GRANT SELECT, INSERT, UPDATE ON core.fact TO offerpilot_app;
GRANT SELECT, INSERT, UPDATE ON core.model_transfer_consent TO offerpilot_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON core.matter_source TO offerpilot_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON core.agent_run TO offerpilot_app;
GRANT SELECT, INSERT, UPDATE, DELETE
    ON core.candidate_plan, core.candidate_plan_item, core.candidate_plan_item_source
    TO offerpilot_app;
GRANT SELECT, INSERT ON core.candidate_plan_decision TO offerpilot_app;
GRANT SELECT, INSERT, UPDATE ON core.task TO offerpilot_app;

COMMENT ON ROLE offerpilot_app IS
    'OfferPilot Alpha 应用角色；受 RLS 约束，快照与证据只增不改';
