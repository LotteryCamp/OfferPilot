-- 0011_core_fact.sql
-- OfferPilot · 个人事实与版本
--
-- 每个用户、每种事实只有一条确认版本；历史版本保留为 superseded。
-- 事实属于用户，不绑定事项；事项通过当前确认版本参与依据指纹。

CREATE TYPE core.fact_status AS ENUM ('draft', 'confirmed', 'superseded', 'revoked');

CREATE TABLE core.fact (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id        uuid NOT NULL,
    fact_type       varchar(48) NOT NULL,
    value_text      text NOT NULL,
    value_json      jsonb NOT NULL DEFAULT '{}'::jsonb,
    value_hash      char(64) NOT NULL,
    scope           varchar(200),
    valid_from      date,
    trust_level     varchar(16) NOT NULL DEFAULT 'self',
    confirm_status  core.fact_status NOT NULL DEFAULT 'draft',
    version_no      integer NOT NULL,
    confirmed_at    timestamptz,
    superseded_at   timestamptz,
    created_at      timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_fact_type_version UNIQUE (owner_id, fact_type, version_no),
    CONSTRAINT ck_fact_version CHECK (version_no > 0),
    CONSTRAINT ck_fact_value_json CHECK (jsonb_typeof(value_json) = 'object'),
    CONSTRAINT ck_fact_value_hash CHECK (value_hash ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_fact_confirm CHECK (
        (confirm_status IN ('confirmed', 'superseded') AND confirmed_at IS NOT NULL)
        OR (confirm_status IN ('draft', 'revoked') AND confirmed_at IS NULL)
    ),
    CONSTRAINT ck_fact_superseded CHECK (
        (confirm_status = 'superseded') = (superseded_at IS NOT NULL)
    ),
    CONSTRAINT fk_fact_owner FOREIGN KEY (owner_id)
        REFERENCES core.app_user (id) ON DELETE CASCADE
);

COMMENT ON TABLE core.fact IS
    '用户个人事实的当前确认版本与历史版本；同类型只有一条 confirmed 记录';
COMMENT ON COLUMN core.fact.value_json IS
    '按事实类型规范化后的值；对象键与类型定义见个人事实接口文档';
COMMENT ON COLUMN core.fact.value_hash IS
    '事实类型、范围、生效日、值与展示文本的规范化 SHA-256';

CREATE UNIQUE INDEX uq_fact_current ON core.fact (owner_id, fact_type)
    WHERE confirm_status = 'confirmed';
CREATE INDEX ix_fact_owner ON core.fact (owner_id, fact_type);

ALTER TABLE core.fact ENABLE ROW LEVEL SECURITY;

CREATE POLICY fact_owner ON core.fact
    USING (owner_id = (
        SELECT w.owner_id FROM core.workspace w
        WHERE w.id = NULLIF(current_setting('app.current_workspace_id', true), '')::uuid))
    WITH CHECK (owner_id = (
        SELECT w.owner_id FROM core.workspace w
        WHERE w.id = NULLIF(current_setting('app.current_workspace_id', true), '')::uuid));

-- 应用角色由 dev/roles.sql 创建；已存在时在此授权，使已部署环境无需重跑角色脚本。
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'offerpilot_app') THEN
        GRANT SELECT, INSERT, UPDATE ON core.fact TO offerpilot_app;
    END IF;
END $$;
