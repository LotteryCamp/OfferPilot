-- 0010_persistence_recovery.sql
-- OfferPilot Alpha · 事项来源关联与 Agent 运行检查点
--
-- 来源读取成功后立即关联当前事项，使尚未生成要求或计划的来源仍可在事项内读取。
-- Agent 运行检查点与运行状态持久化；进程重启后读取已保存结果，并明确标记中断运行。

CREATE TABLE core.matter_source (
    matter_id  uuid NOT NULL,
    snapshot_id uuid NOT NULL,
    linked_at  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT pk_matter_source PRIMARY KEY (matter_id, snapshot_id),
    CONSTRAINT fk_matter_source_matter FOREIGN KEY (matter_id)
        REFERENCES core.matter (id) ON DELETE CASCADE,
    CONSTRAINT fk_matter_source_snapshot FOREIGN KEY (snapshot_id)
        REFERENCES ops.snapshot (id) ON DELETE RESTRICT
);

COMMENT ON TABLE core.matter_source IS
    '事项与已读取来源快照的关联；来源读取成功后即可读取，不要求先生成要求或候选计划';

CREATE INDEX ix_matter_source_snapshot ON core.matter_source (snapshot_id);

ALTER TABLE core.matter_source ENABLE ROW LEVEL SECURITY;

CREATE POLICY matter_source_by_matter ON core.matter_source
    USING (EXISTS (
        SELECT 1 FROM core.matter m
        WHERE m.id = matter_source.matter_id
          AND m.workspace_id = NULLIF(current_setting('app.current_workspace_id', true), '')::uuid
    ))
    WITH CHECK (EXISTS (
        SELECT 1 FROM core.matter m
        WHERE m.id = matter_source.matter_id
          AND m.workspace_id = NULLIF(current_setting('app.current_workspace_id', true), '')::uuid
    ));

CREATE TABLE core.agent_run (
    run_id       varchar(64) PRIMARY KEY,
    matter_id    uuid NOT NULL,
    user_id      uuid NOT NULL,
    status       varchar(24) NOT NULL,
    operation_id varchar(200),
    checkpoint   jsonb,
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_agent_run_matter FOREIGN KEY (matter_id)
        REFERENCES core.matter (id) ON DELETE CASCADE,
    CONSTRAINT fk_agent_run_user FOREIGN KEY (user_id)
        REFERENCES core.app_user (id) ON DELETE RESTRICT,
    CONSTRAINT ck_agent_run_status CHECK (
        status IN (
            'running', 'waiting_user', 'waiting_confirmation',
            'completed', 'failed', 'cancelled', 'interrupted'
        )
    ),
    CONSTRAINT ck_agent_run_checkpoint CHECK (
        checkpoint IS NULL OR jsonb_typeof(checkpoint) = 'object'
    )
);

COMMENT ON TABLE core.agent_run IS
    'Agent 运行状态与检查点；等待决定和终态结果可跨进程读取，重启时未完成运行标记为中断';

CREATE INDEX ix_agent_run_matter ON core.agent_run (matter_id, created_at DESC);
CREATE INDEX ix_agent_run_operation ON core.agent_run (matter_id, operation_id)
    WHERE operation_id IS NOT NULL;

CREATE TRIGGER trg_agent_run_touch
    BEFORE UPDATE ON core.agent_run
    FOR EACH ROW EXECUTE FUNCTION core.touch_updated_at();

ALTER TABLE core.agent_run ENABLE ROW LEVEL SECURITY;

CREATE POLICY agent_run_by_matter ON core.agent_run
    USING (EXISTS (
        SELECT 1 FROM core.matter m
        WHERE m.id = agent_run.matter_id
          AND m.workspace_id = NULLIF(current_setting('app.current_workspace_id', true), '')::uuid
    ))
    WITH CHECK (EXISTS (
        SELECT 1 FROM core.matter m
        WHERE m.id = agent_run.matter_id
          AND m.workspace_id = NULLIF(current_setting('app.current_workspace_id', true), '')::uuid
    ));

-- 应用角色由 dev/roles.sql 创建；已存在时在此授权，使已部署环境无需重跑角色脚本。
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'offerpilot_app') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON core.matter_source TO offerpilot_app;
        GRANT SELECT, INSERT, UPDATE, DELETE ON core.agent_run TO offerpilot_app;
    END IF;
END $$;
