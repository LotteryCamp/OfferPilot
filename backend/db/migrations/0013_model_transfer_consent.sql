-- 0013_model_transfer_consent.sql
-- OfferPilot · 模型传输同意
--
-- 同意记录归属于用户与事项，绑定服务商、用途、字段类别与授权版本。
-- 同一事项同时只有一条 active 记录；撤回后保留历史版本。

CREATE TABLE core.model_transfer_consent (
    id               uuid PRIMARY KEY,
    workspace_id     uuid NOT NULL REFERENCES core.workspace (id) ON DELETE CASCADE,
    owner_id         uuid NOT NULL REFERENCES core.app_user (id) ON DELETE CASCADE,
    matter_id        uuid NOT NULL REFERENCES core.matter (id) ON DELETE CASCADE,
    provider         text NOT NULL,
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
        UNIQUE (owner_id, matter_id, version_no)
);

CREATE UNIQUE INDEX uq_model_transfer_consent_active
    ON core.model_transfer_consent (owner_id, matter_id)
    WHERE consent_status = 'active';

CREATE INDEX ix_model_transfer_consent_matter
    ON core.model_transfer_consent (matter_id, created_at DESC);

ALTER TABLE core.model_transfer_consent ENABLE ROW LEVEL SECURITY;

CREATE POLICY model_transfer_consent_by_matter ON core.model_transfer_consent
    USING (
        workspace_id = NULLIF(current_setting('app.current_workspace_id', true), '')::uuid
        AND EXISTS (
            SELECT 1
            FROM core.matter m
            JOIN core.workspace w ON w.id = m.workspace_id
            WHERE m.id = model_transfer_consent.matter_id
              AND m.workspace_id = model_transfer_consent.workspace_id
              AND w.owner_id = model_transfer_consent.owner_id
        )
    )
    WITH CHECK (
        workspace_id = NULLIF(current_setting('app.current_workspace_id', true), '')::uuid
        AND EXISTS (
            SELECT 1
            FROM core.matter m
            JOIN core.workspace w ON w.id = m.workspace_id
            WHERE m.id = model_transfer_consent.matter_id
              AND m.workspace_id = model_transfer_consent.workspace_id
              AND w.owner_id = model_transfer_consent.owner_id
        )
    );

COMMENT ON TABLE core.model_transfer_consent IS
    '用户对当前事项向外部模型传输公开资料的明确同意；同一事项只有一条 active 记录';
COMMENT ON COLUMN core.model_transfer_consent.purposes IS
    '同意覆盖的处理用途，与 Agent 工具的出站用途逐一匹配';
COMMENT ON COLUMN core.model_transfer_consent.field_categories IS
    '同意覆盖的字段类别，出站网关按实际发送类别核对';
