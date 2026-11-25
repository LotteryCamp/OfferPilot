-- 0002_core_identity_matter.sql
-- OfferPilot · 用户、工作区、事项类型、事项
--
-- 来源：说明书 §5.2.1（表 5-3、5-4、5-5、5-8）。
--
-- 设计取舍：
--   * stage / matter_decision 未建表。

CREATE TABLE core.app_user (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email         varchar(160) NOT NULL,
    display_name  varchar(60)  NOT NULL,
    password_hash varchar(255) NOT NULL,
    account_type  varchar(16)  NOT NULL DEFAULT 'applicant',
    status        core.account_status NOT NULL DEFAULT 'pending',
    created_at    timestamptz  NOT NULL DEFAULT now(),
    updated_at    timestamptz  NOT NULL DEFAULT now(),
    deleted_at    timestamptz,
    CONSTRAINT uq_app_user_email UNIQUE (email),
    CONSTRAINT ck_app_user_type CHECK (account_type IN ('applicant')),
    CONSTRAINT ck_app_user_email CHECK (email = lower(btrim(email)) AND position('@' IN email) > 1)
);

COMMENT ON TABLE core.app_user IS '登录主体；首版只有 applicant 一种账号（D-26）';

CREATE TABLE core.workspace (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id   uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_workspace_owner UNIQUE (owner_id),
    CONSTRAINT fk_workspace_owner FOREIGN KEY (owner_id)
        REFERENCES core.app_user (id) ON DELETE CASCADE
);

COMMENT ON TABLE core.workspace IS '与用户 1:1 的个人工作区，事项归属的边界';

CREATE TABLE core.matter_type (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    type_code  varchar(32) NOT NULL,
    name       varchar(60) NOT NULL,
    built_in   boolean NOT NULL DEFAULT false,
    enabled    boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_matter_type_code UNIQUE (type_code),
    CONSTRAINT ck_matter_type_code CHECK (type_code ~ '^[a-z][a-z0-9_]{1,31}$')
);

COMMENT ON TABLE core.matter_type IS '事项类型注册表；type_code 是模板、来源、事项的连接键';

CREATE TABLE core.template_version (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    type_code            varchar(32) NOT NULL,
    version_no           varchar(32) NOT NULL,
    stage_defs           jsonb NOT NULL DEFAULT '[]',
    requirement_skeleton jsonb NOT NULL DEFAULT '[]',
    material_types       jsonb NOT NULL DEFAULT '[]',
    status               varchar(16) NOT NULL DEFAULT 'draft',
    published_at         timestamptz,
    created_at           timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_template_version_type FOREIGN KEY (type_code)
        REFERENCES core.matter_type (type_code) ON DELETE RESTRICT,
    CONSTRAINT uq_template_version UNIQUE (type_code, version_no),
    CONSTRAINT ck_template_version_status CHECK (status IN ('draft', 'published', 'retired')),
    CONSTRAINT ck_template_version_stage_defs CHECK (jsonb_typeof(stage_defs) = 'array'),
    CONSTRAINT ck_template_version_skeleton CHECK (jsonb_typeof(requirement_skeleton) = 'array'),
    CONSTRAINT ck_template_version_materials CHECK (jsonb_typeof(material_types) = 'array')
);

COMMENT ON TABLE core.template_version IS '事项模板版本；事项引用具体版本，模板调整不影响已建事项';

CREATE TABLE core.matter (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id         uuid NOT NULL,
    type_code            varchar(32) NOT NULL,
    template_version_id  uuid NOT NULL,
    goal                 varchar(200) NOT NULL,
    status               core.matter_status NOT NULL DEFAULT 'draft',
    scope_year           smallint,
    scope_attrs          jsonb,
    parent_matter_id     uuid,
    archived_at          timestamptz,
    submitted_version_ids uuid[],
    archive_result       varchar(200),
    retrospective        text,
    created_at           timestamptz NOT NULL DEFAULT now(),
    updated_at           timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_matter_workspace FOREIGN KEY (workspace_id)
        REFERENCES core.workspace (id) ON DELETE CASCADE,
    CONSTRAINT fk_matter_type FOREIGN KEY (type_code)
        REFERENCES core.matter_type (type_code) ON DELETE RESTRICT,
    CONSTRAINT fk_matter_template_version FOREIGN KEY (template_version_id)
        REFERENCES core.template_version (id) ON DELETE RESTRICT,
    CONSTRAINT fk_matter_parent FOREIGN KEY (parent_matter_id)
        REFERENCES core.matter (id) ON DELETE SET NULL,
    CONSTRAINT ck_matter_goal CHECK (length(btrim(goal)) > 0),
    CONSTRAINT ck_matter_year CHECK (scope_year IS NULL OR scope_year BETWEEN 2020 AND 2100),
    CONSTRAINT ck_matter_parent CHECK (parent_matter_id IS NULL OR parent_matter_id <> id),
    CONSTRAINT ck_matter_scope_attrs CHECK (
        scope_attrs IS NULL OR jsonb_typeof(scope_attrs) = 'object'
    ),
    CONSTRAINT ck_matter_archive CHECK (
        (status = 'archived' AND archived_at IS NOT NULL)
        OR (status <> 'archived' AND archived_at IS NULL)
    ),
    CONSTRAINT ck_matter_submitted_versions CHECK (
        submitted_version_ids IS NULL OR cardinality(submitted_version_ids) <= 50
    )
);

COMMENT ON TABLE core.matter IS '核心聚合根；一次申请/一场竞赛/一个项目申报';
COMMENT ON COLUMN core.matter.template_version_id IS '实例化事项所用的模板版本';
COMMENT ON COLUMN core.matter.scope_attrs IS '类型特有字段（院校/项目/批次等），禁止存证件号与原文';

CREATE INDEX ix_matter_workspace ON core.matter (workspace_id, status);
CREATE INDEX ix_matter_type_year ON core.matter (type_code, scope_year);
CREATE INDEX ix_matter_parent ON core.matter (parent_matter_id)
    WHERE parent_matter_id IS NOT NULL;

-- 通用 updated_at 触发器：说明书 §5.6
CREATE FUNCTION core.touch_updated_at() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END $$;

CREATE TRIGGER trg_app_user_touch
    BEFORE UPDATE ON core.app_user
    FOR EACH ROW EXECUTE FUNCTION core.touch_updated_at();

CREATE TRIGGER trg_workspace_touch
    BEFORE UPDATE ON core.workspace
    FOR EACH ROW EXECUTE FUNCTION core.touch_updated_at();

CREATE TRIGGER trg_matter_touch
    BEFORE UPDATE ON core.matter
    FOR EACH ROW EXECUTE FUNCTION core.touch_updated_at();