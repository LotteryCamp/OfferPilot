-- 0015_global_model_transfer_consent.sql
-- OfferPilot · 全局模型传输同意
--
-- 同意归属于用户并覆盖全部事项，记录绑定用途、字段类别与授权版本。
-- 同一用户同时只有一条 active 记录；撤回后保留历史版本。

DROP TABLE core.model_transfer_consent;

CREATE TABLE core.model_transfer_consent (
    id               uuid PRIMARY KEY,
    workspace_id     uuid NOT NULL REFERENCES core.workspace (id) ON DELETE CASCADE,
    owner_id         uuid NOT NULL REFERENCES core.app_user (id) ON DELETE CASCADE,
    purposes         text[] NOT NULL,
    field_categories text[] NOT NULL,
    consent_status   text NOT NULL,
    version_no       integer NOT NULL,
    created_at       timestamptz NOT NULL,
    revoked_at       timestamptz,
    CONSTRAINT ck_model_transfer_consent_status
        CHECK (consent_status IN ('active', 'revoked')),
    CONSTRAINT ck_model_transfer_consent_revoked
        CHECK (
            (consent_status = 'active' AND revoked_at IS NULL)
            OR (consent_status = 'revoked' AND revoked_at IS NOT NULL)
        ),
    CONSTRAINT ck_model_transfer_consent_version
        CHECK (version_no > 0),
    CONSTRAINT uq_model_transfer_consent_version
        UNIQUE (owner_id, version_no)
);

CREATE UNIQUE INDEX uq_model_transfer_consent_active
    ON core.model_transfer_consent (owner_id)
    WHERE consent_status = 'active';

CREATE INDEX ix_model_transfer_consent_owner
    ON core.model_transfer_consent (owner_id, created_at DESC);

ALTER TABLE core.model_transfer_consent ENABLE ROW LEVEL SECURITY;

CREATE POLICY model_transfer_consent_by_owner ON core.model_transfer_consent
    USING (
        workspace_id = NULLIF(current_setting('app.current_workspace_id', true), '')::uuid
        AND EXISTS (
            SELECT 1
            FROM core.workspace w
            WHERE w.id = model_transfer_consent.workspace_id
              AND w.owner_id = model_transfer_consent.owner_id
        )
    )
    WITH CHECK (
        workspace_id = NULLIF(current_setting('app.current_workspace_id', true), '')::uuid
        AND EXISTS (
            SELECT 1
            FROM core.workspace w
            WHERE w.id = model_transfer_consent.workspace_id
              AND w.owner_id = model_transfer_consent.owner_id
        )
    );

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'offerpilot_app') THEN
        GRANT SELECT, INSERT, UPDATE ON core.model_transfer_consent TO offerpilot_app;
    END IF;
END $$;

COMMENT ON TABLE core.model_transfer_consent IS
    '用户向外部模型传输公开资料的全局明确同意；同一用户只有一条 active 记录';
COMMENT ON COLUMN core.model_transfer_consent.purposes IS
    '同意覆盖的处理用途，与 Agent 工具的出站用途逐一匹配';
COMMENT ON COLUMN core.model_transfer_consent.field_categories IS
    '同意覆盖的字段类别，出站网关按实际发送类别核对';
