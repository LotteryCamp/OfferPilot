-- OfferPilot 数据库建表脚本（PostgreSQL 16，V2.0 事项为中心）
-- 与《数据库设计说明书》§5.2 逐字段对应
BEGIN;

CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS ops;
CREATE SCHEMA IF NOT EXISTS kb;

-- ============ 枚举类型 ============
CREATE TYPE account_status AS ENUM ('pending', 'active', 'disabled');
CREATE TYPE matter_status AS ENUM (
    'draft', 'active', 'paused', 'archived', 'cancelled'
);
CREATE TYPE stage_status AS ENUM ('pending', 'in_progress', 'done', 'skipped');
CREATE TYPE obligation_nature AS ENUM (
    'required', 'advised', 'optional', 'to_verify'
);
CREATE TYPE extract_status AS ENUM (
    'extracted', 'checked', 'to_review', 'rejected'
);
CREATE TYPE conclusion AS ENUM (
    'compliant', 'non_compliant', 'missing_info', 'to_review'
);
CREATE TYPE plan_status AS ENUM (
    'draft', 'pending', 'confirmed', 'rejected', 'expired'
);
CREATE TYPE task_status AS ENUM (
    'pending', 'ready', 'in_progress', 'blocked', 'done', 'cancelled'
);
CREATE TYPE inbox_status AS ENUM ('open', 'read', 'resolved', 'ignored');
CREATE TYPE fact_status AS ENUM ('draft', 'confirmed', 'revoked');
CREATE TYPE doc_status AS ENUM (
    'draft', 'valid', 'expiring', 'expired', 'frozen', 'revoked'
);
CREATE TYPE grant_status AS ENUM ('active', 'revoked', 'expired');
CREATE TYPE consent_status AS ENUM ('granted', 'revoked');
CREATE TYPE source_status AS ENUM ('active', 'withdrawn', 'invalid');
CREATE TYPE check_result AS ENUM ('pending', 'passed', 'failed', 'conflict');
CREATE TYPE gap_status AS ENUM ('open', 'filled', 'unverifiable');
CREATE TYPE pack_status AS ENUM ('draft', 'published', 'retired');
CREATE TYPE severity AS ENUM ('block', 'warn', 'info');


-- ============ core 模式：业务主数据 ============

CREATE TABLE core.app_user (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    email varchar(160) NOT NULL,
    display_name varchar(60) NOT NULL,
    password_hash varchar(255) NOT NULL,
    account_type varchar(16) DEFAULT 'applicant' NOT NULL,
    status account_status DEFAULT 'pending' NOT NULL,
    created_at timestamptz DEFAULT now() NOT NULL,
    updated_at timestamptz DEFAULT now() NOT NULL,
    deleted_at timestamptz,
    CONSTRAINT uq_app_user_email UNIQUE (email),
    CONSTRAINT ck_app_user_type CHECK (account_type IN ('applicant'))
);
CREATE INDEX ix_app_user_status ON core.app_user (status);

CREATE TABLE core.workspace (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    owner_id uuid NOT NULL,
    created_at timestamptz DEFAULT now() NOT NULL,
    updated_at timestamptz DEFAULT now() NOT NULL,
    CONSTRAINT uq_workspace_owner UNIQUE (owner_id),
    CONSTRAINT fk_workspace_owner_id FOREIGN KEY (owner_id),
        REFERENCES core.app_user (id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX ix_workspace_owner ON core.workspace (owner_id);

CREATE TABLE core.matter_type (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    type_code varchar(32) NOT NULL,
    name varchar(60) NOT NULL,
    built_in boolean DEFAULT false NOT NULL,
    enabled boolean DEFAULT true NOT NULL,
    created_at timestamptz DEFAULT now() NOT NULL,
    CONSTRAINT uq_matter_type_code UNIQUE (type_code)
);
CREATE INDEX ix_matter_type_enabled ON core.matter_type (enabled) WHERE enabled;

-- ============ kb 模式：领域知识（规则包） ============

CREATE TABLE kb.rule_pack (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    code varchar(48) NOT NULL,
    name varchar(120) NOT NULL,
    matter_type_id uuid,
    status pack_status DEFAULT 'draft' NOT NULL,
    regression_result jsonb,
    published_at timestamptz,
    created_at timestamptz DEFAULT now() NOT NULL,
    CONSTRAINT uq_rule_pack_code UNIQUE (code),
CONSTRAINT ck_pack_publish CHECK (status <> 'published' OR published_at IS NOT
        NULL),
    CONSTRAINT fk_rule_pack_matter_type_id FOREIGN KEY (matter_type_id),
        REFERENCES core.matter_type (id) ON DELETE SET NULL
);
CREATE INDEX ix_pack_type_status ON kb.rule_pack (matter_type_id, status);

CREATE TABLE kb.rule (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    rule_pack_id uuid NOT NULL,
    rule_code varchar(48) NOT NULL,
    rule_type varchar(24) NOT NULL,
    condition_expr text,
    formula text,
    scope varchar(200),
    severity severity DEFAULT 'warn' NOT NULL,
    message varchar(300),
    CONSTRAINT uq_rule_code UNIQUE (rule_pack_id, rule_code),
CONSTRAINT ck_rule_type CHECK (rule_type IN
        ('schema','expression','mapping','consistency')),
    CONSTRAINT fk_rule_rule_pack_id FOREIGN KEY (rule_pack_id),
        REFERENCES kb.rule_pack (id) ON DELETE CASCADE
);
CREATE INDEX ix_rule_pack ON kb.rule (rule_pack_id, severity);

-- ============ core 模式：业务主数据 ============

CREATE TABLE core.template (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    type_code varchar(32) NOT NULL,
    name varchar(80) NOT NULL,
    current_version_id uuid,
    status varchar(16) DEFAULT 'draft' NOT NULL,
    created_at timestamptz DEFAULT now() NOT NULL,
    CONSTRAINT uq_template_type_name UNIQUE (type_code, name),
    CONSTRAINT ck_template_status CHECK (status IN ('draft','published','retired')),
    CONSTRAINT fk_template_type_code FOREIGN KEY (type_code),
        REFERENCES core.matter_type (type_code) ON DELETE RESTRICT
);
CREATE INDEX ix_template_type ON core.template (type_code);

CREATE TABLE core.template_version (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    template_id uuid NOT NULL,
    version_no varchar(32) NOT NULL,
    stage_defs jsonb NOT NULL,
    requirement_skeleton jsonb NOT NULL,
    material_types jsonb NOT NULL,
    rule_pack_id uuid,
    status pack_status DEFAULT 'draft' NOT NULL,
    regression_result jsonb,
    published_at timestamptz,
    created_at timestamptz DEFAULT now() NOT NULL,
    CONSTRAINT uq_template_version_no UNIQUE (template_id, version_no),
CONSTRAINT ck_tv_publish CHECK (status <> 'published' OR published_at IS NOT NULL),
    CONSTRAINT fk_template_version_template_id FOREIGN KEY (template_id),
        REFERENCES core.template (id) ON DELETE CASCADE,
    CONSTRAINT fk_template_version_rule_pack_id FOREIGN KEY (rule_pack_id),
        REFERENCES kb.rule_pack (id) ON DELETE SET NULL
);
CREATE INDEX ix_tv_template ON core.template_version (template_id, status);

CREATE TABLE core.matter (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    workspace_id uuid NOT NULL,
    type_code varchar(32) NOT NULL,
    template_version_id uuid NOT NULL,
    goal varchar(200) NOT NULL,
    status matter_status DEFAULT 'draft' NOT NULL,
    scope_year smallint,
    scope_attrs jsonb,
    parent_matter_id uuid,
    archived_at timestamptz,
    submitted_version_ids uuid[],
    archive_result varchar(200),
    retrospective text,
    created_at timestamptz DEFAULT now() NOT NULL,
    updated_at timestamptz DEFAULT now() NOT NULL,
CONSTRAINT ck_matter_archive CHECK ((archived_at IS NULL) = (submitted_version_ids
        IS NULL)),
CONSTRAINT ck_matter_year CHECK (scope_year IS NULL OR scope_year BETWEEN 2020 AND
        2100),
    CONSTRAINT fk_matter_workspace_id FOREIGN KEY (workspace_id),
        REFERENCES core.workspace (id) ON DELETE CASCADE,
    CONSTRAINT fk_matter_type_code FOREIGN KEY (type_code),
        REFERENCES core.matter_type (type_code) ON DELETE RESTRICT,
    CONSTRAINT fk_matter_template_version_id FOREIGN KEY (template_version_id),
        REFERENCES core.template_version (id) ON DELETE RESTRICT,
    CONSTRAINT fk_matter_parent_matter_id FOREIGN KEY (parent_matter_id),
        REFERENCES core.matter (id) ON DELETE SET NULL
);
CREATE INDEX ix_matter_workspace ON core.matter (workspace_id, status);
CREATE INDEX ix_matter_type_year ON core.matter (type_code, scope_year);
CREATE INDEX ix_matter_parent ON core.matter (parent_matter_id);

CREATE TABLE core.stage (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    matter_id uuid NOT NULL,
    name varchar(60) NOT NULL,
    seq smallint NOT NULL,
    status stage_status DEFAULT 'pending' NOT NULL,
    is_required boolean DEFAULT true NOT NULL,
    started_at timestamptz,
    completed_at timestamptz,
    CONSTRAINT uq_stage_seq UNIQUE (matter_id, seq),
    CONSTRAINT ck_stage_seq CHECK (seq >= 0),
    CONSTRAINT fk_stage_matter_id FOREIGN KEY (matter_id),
        REFERENCES core.matter (id) ON DELETE CASCADE
);
CREATE INDEX ix_stage_matter ON core.stage (matter_id, seq);

CREATE TABLE core.matter_decision (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    matter_id uuid NOT NULL,
    decision_type varchar(24) NOT NULL,
    decision_value varchar(24) NOT NULL,
    reason text,
    decided_at timestamptz DEFAULT now() NOT NULL,
CONSTRAINT ck_decision_type CHECK (decision_type IN
        ('invest','optional_task','plan')),
    CONSTRAINT ck_decision_value CHECK (decision_value IN ('adopt','later','skip')),
    CONSTRAINT fk_matter_decision_matter_id FOREIGN KEY (matter_id),
        REFERENCES core.matter (id) ON DELETE CASCADE
);
CREATE INDEX ix_decision_matter ON core.matter_decision (matter_id, decided_at);

-- ============ ops 模式：来源、证据与审计 ============

CREATE TABLE ops.source (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    publisher varchar(160) NOT NULL,
    url varchar(500) NOT NULL,
    matter_type_id uuid,
    scope varchar(200),
    scope_year smallint,
    valid_from date,
    valid_to date,
    status source_status DEFAULT 'active' NOT NULL,
    auto_check_status check_result DEFAULT 'pending' NOT NULL,
    roi_status varchar(16) DEFAULT 'original' NOT NULL,
    last_fetched_at timestamptz,
    created_at timestamptz DEFAULT now() NOT NULL,
    CONSTRAINT uq_source_url UNIQUE (url),
CONSTRAINT ck_source_roi CHECK (roi_status IN
        ('original','reposted','expired','ambiguous')),
CONSTRAINT ck_source_range CHECK (valid_to IS NULL OR valid_from IS NULL OR
        valid_to >= valid_from),
    CONSTRAINT fk_source_matter_type_id FOREIGN KEY (matter_type_id),
        REFERENCES core.matter_type (id) ON DELETE SET NULL
);
CREATE INDEX ix_source_type_year ON ops.source (matter_type_id, scope_year);
CREATE INDEX ix_source_status ON ops.source (status, auto_check_status);

CREATE TABLE ops.snapshot (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    source_id uuid NOT NULL,
    version_no integer NOT NULL,
    object_key varchar(512) NOT NULL,
    content_hash char(64) NOT NULL,
    html_version varchar(32),
    text_version varchar(32),
    extraction jsonb,
    fetched_at timestamptz NOT NULL,
    is_current boolean DEFAULT false NOT NULL,
    CONSTRAINT uq_snapshot_version UNIQUE (source_id, version_no),
    CONSTRAINT uq_snapshot_hash UNIQUE (source_id, content_hash),
    CONSTRAINT ck_snapshot_version CHECK (version_no > 0),
    CONSTRAINT fk_snapshot_source_id FOREIGN KEY (source_id),
        REFERENCES ops.source (id) ON DELETE CASCADE
);
CREATE INDEX ix_snapshot_current ON ops.snapshot (source_id) WHERE is_current;
CREATE INDEX ix_snapshot_fetched ON ops.snapshot (fetched_at);

-- ============ core 模式：业务主数据 ============

CREATE TABLE core.requirement (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    matter_id uuid NOT NULL,
    snapshot_id uuid NOT NULL,
    field_key varchar(64) NOT NULL,
    label varchar(120) NOT NULL,
    obligation_nature obligation_nature DEFAULT 'required' NOT NULL,
    extract_status extract_status DEFAULT 'extracted' NOT NULL,
    scope varchar(200),
    value_text text,
    value_type varchar(16) DEFAULT 'text' NOT NULL,
    confidence numeric(4,3),
    checked_at timestamptz,
    created_at timestamptz DEFAULT now() NOT NULL,
    updated_at timestamptz DEFAULT now() NOT NULL,
CONSTRAINT ck_req_confidence CHECK (confidence IS NULL OR (confidence >= 0 AND
        confidence <= 1)),
CONSTRAINT ck_req_checked CHECK (extract_status <> 'checked' OR checked_at IS NOT
        NULL),
    CONSTRAINT fk_requirement_matter_id FOREIGN KEY (matter_id),
        REFERENCES core.matter (id) ON DELETE CASCADE,
    CONSTRAINT fk_requirement_snapshot_id FOREIGN KEY (snapshot_id),
        REFERENCES ops.snapshot (id) ON DELETE RESTRICT
);
CREATE INDEX ix_req_matter ON core.requirement (matter_id, field_key);
CREATE INDEX ix_req_snapshot ON core.requirement (snapshot_id);
CREATE INDEX ix_req_status ON core.requirement (extract_status) WHERE
    extract_status = 'to_review';

-- ============ ops 模式：来源、证据与审计 ============

CREATE TABLE ops.source_gap (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    matter_id uuid NOT NULL,
    gap_type varchar(32) NOT NULL,
    affected_requirement_id uuid,
    status gap_status DEFAULT 'open' NOT NULL,
    note text,
    created_at timestamptz DEFAULT now() NOT NULL,
CONSTRAINT ck_gap_type CHECK (gap_type IN
        ('official_entry_unknown','repost_only','login_required',
        'page_removed','attachment_missing','non_public')),
    CONSTRAINT fk_source_gap_matter_id FOREIGN KEY (matter_id),
        REFERENCES core.matter (id) ON DELETE CASCADE,
CONSTRAINT fk_source_gap_affected_requirement_id FOREIGN KEY
        (affected_requirement_id),
        REFERENCES core.requirement (id) ON DELETE SET NULL
);
CREATE INDEX ix_gap_matter ON ops.source_gap (matter_id, status);

CREATE TABLE ops.evidence (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    source_id uuid NOT NULL,
    snapshot_id uuid NOT NULL,
    target_type varchar(24) NOT NULL,
    target_id uuid NOT NULL,
    locator_kind varchar(16) NOT NULL,
    locator varchar(300) NOT NULL,
    quote text,
    quote_hash char(64),
    fetched_at timestamptz NOT NULL,
CONSTRAINT uq_evidence_quad UNIQUE (snapshot_id, target_type, target_id, locator),
CONSTRAINT ck_evidence_target CHECK (target_type IN
        ('requirement','evaluation','material_version')),
CONSTRAINT ck_evidence_locator CHECK (locator_kind IN
        ('text_span','page','table_row','section')),
    CONSTRAINT fk_evidence_source_id FOREIGN KEY (source_id),
        REFERENCES ops.source (id) ON DELETE RESTRICT,
    CONSTRAINT fk_evidence_snapshot_id FOREIGN KEY (snapshot_id),
        REFERENCES ops.snapshot (id) ON DELETE CASCADE
);
CREATE INDEX ix_evidence_target ON ops.evidence (target_type, target_id);
CREATE INDEX ix_evidence_snapshot ON ops.evidence (snapshot_id);

-- ============ core 模式：业务主数据 ============

CREATE TABLE core.evaluation (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    requirement_id uuid NOT NULL,
    conclusion conclusion NOT NULL,
    basis text,
    rule_version varchar(32) NOT NULL,
    fact_version varchar(32),
    created_at timestamptz DEFAULT now() NOT NULL,
    CONSTRAINT fk_evaluation_requirement_id FOREIGN KEY (requirement_id),
        REFERENCES core.requirement (id) ON DELETE CASCADE
);
CREATE INDEX ix_eval_requirement ON core.evaluation (requirement_id, created_at);
CREATE INDEX ix_eval_conclusion ON core.evaluation (conclusion) WHERE conclusion <>
    'compliant';

CREATE TABLE core.mentor_contact_rule (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    matter_id uuid NOT NULL,
    project_scope varchar(120) NOT NULL,
    contact_status varchar(24) NOT NULL,
    proof_required boolean DEFAULT false NOT NULL,
    source_id uuid,
    snapshot_id uuid,
CONSTRAINT ck_mentor_status CHECK (contact_status IN
        ('required','advised','not_mentioned','inconsistent')),
    CONSTRAINT fk_mentor_contact_rule_matter_id FOREIGN KEY (matter_id),
        REFERENCES core.matter (id) ON DELETE CASCADE,
    CONSTRAINT fk_mentor_contact_rule_source_id FOREIGN KEY (source_id),
        REFERENCES ops.source (id) ON DELETE SET NULL,
    CONSTRAINT fk_mentor_contact_rule_snapshot_id FOREIGN KEY (snapshot_id),
        REFERENCES ops.snapshot (id) ON DELETE SET NULL
);
CREATE INDEX ix_mentor_matter ON core.mentor_contact_rule (matter_id);

CREATE TABLE core.personal_document (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id uuid NOT NULL,
    category varchar(32) NOT NULL,
    title varchar(120) NOT NULL,
    sensitivity_level varchar(16) DEFAULT 'normal' NOT NULL,
    trust_level varchar(16) DEFAULT 'self' NOT NULL,
    current_version_id uuid,
    status doc_status DEFAULT 'draft' NOT NULL,
    created_at timestamptz DEFAULT now() NOT NULL,
CONSTRAINT ck_doc_sensitivity CHECK (sensitivity_level IN
        ('normal','sensitive','high')),
    CONSTRAINT fk_personal_document_user_id FOREIGN KEY (user_id),
        REFERENCES core.app_user (id) ON DELETE CASCADE
);
CREATE INDEX ix_doc_user ON core.personal_document (user_id, category, status);

CREATE TABLE core.document_version (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    doc_id uuid NOT NULL,
    version_no integer NOT NULL,
    object_key varchar(512) NOT NULL,
    file_hash char(64) NOT NULL,
    issued_at date,
    valid_until date,
    doc_form varchar(24) DEFAULT 'electronic' NOT NULL,
    coverage varchar(200),
    trust_level varchar(16) DEFAULT 'self' NOT NULL,
    status doc_status DEFAULT 'valid' NOT NULL,
    created_at timestamptz DEFAULT now() NOT NULL,
    CONSTRAINT uq_doc_version_no UNIQUE (doc_id, version_no),
CONSTRAINT ck_dv_form CHECK (doc_form IN
        ('original','copy','stamped','electronic')),
CONSTRAINT ck_dv_range CHECK (valid_until IS NULL OR issued_at IS NULL OR
        valid_until >= issued_at),
    CONSTRAINT fk_document_version_doc_id FOREIGN KEY (doc_id),
        REFERENCES core.personal_document (id) ON DELETE CASCADE
);
CREATE INDEX ix_dv_doc ON core.document_version (doc_id, version_no);
CREATE INDEX ix_dv_expire ON core.document_version (valid_until) WHERE status IN
    ('valid','expiring');

CREATE TABLE core.document_usage (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    doc_id uuid NOT NULL,
    version_id uuid NOT NULL,
    matter_id uuid NOT NULL,
    requirement_id uuid,
    frozen boolean DEFAULT false NOT NULL,
    used_at timestamptz DEFAULT now() NOT NULL,
    CONSTRAINT uq_doc_usage UNIQUE (version_id, matter_id, requirement_id),
    CONSTRAINT fk_document_usage_doc_id FOREIGN KEY (doc_id),
        REFERENCES core.personal_document (id) ON DELETE CASCADE,
    CONSTRAINT fk_document_usage_version_id FOREIGN KEY (version_id),
        REFERENCES core.document_version (id) ON DELETE RESTRICT,
    CONSTRAINT fk_document_usage_matter_id FOREIGN KEY (matter_id),
        REFERENCES core.matter (id) ON DELETE CASCADE,
    CONSTRAINT fk_document_usage_requirement_id FOREIGN KEY (requirement_id),
        REFERENCES core.requirement (id) ON DELETE SET NULL
);
CREATE INDEX ix_usage_matter ON core.document_usage (matter_id);
CREATE INDEX ix_usage_version ON core.document_usage (version_id);

CREATE TABLE core.fact (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    owner_id uuid NOT NULL,
    fact_type varchar(48) NOT NULL,
    value_text text NOT NULL,
    source_document_id uuid,
    valid_from date,
    trust_level varchar(16) DEFAULT 'self' NOT NULL,
    confirm_status fact_status DEFAULT 'draft' NOT NULL,
    version_no integer DEFAULT 1 NOT NULL,
    confirmed_at timestamptz,
    created_at timestamptz DEFAULT now() NOT NULL,
    CONSTRAINT uq_fact_type_version UNIQUE (owner_id, fact_type, version_no),
CONSTRAINT ck_fact_confirm CHECK ((confirm_status = 'confirmed') = (confirmed_at IS
        NOT NULL)),
    CONSTRAINT fk_fact_owner_id FOREIGN KEY (owner_id),
        REFERENCES core.app_user (id) ON DELETE CASCADE,
    CONSTRAINT fk_fact_source_document_id FOREIGN KEY (source_document_id),
        REFERENCES core.personal_document (id) ON DELETE SET NULL
);
CREATE UNIQUE INDEX uq_fact_current ON core.fact (owner_id, fact_type) WHERE
    confirm_status = 'confirmed';
CREATE INDEX ix_fact_owner ON core.fact (owner_id, fact_type);
CREATE INDEX ix_fact_status ON core.fact (confirm_status) WHERE confirm_status =
    'draft';

CREATE TABLE core.fact_grant (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    fact_id uuid NOT NULL,
    granted_to varchar(32) NOT NULL,
    purpose varchar(64) NOT NULL,
    status grant_status DEFAULT 'active' NOT NULL,
    expires_at timestamptz,
    created_at timestamptz DEFAULT now() NOT NULL,
    CONSTRAINT ck_grant_target CHECK (granted_to IN ('matter','agent','export')),
    CONSTRAINT fk_fact_grant_fact_id FOREIGN KEY (fact_id),
        REFERENCES core.fact (id) ON DELETE CASCADE
);
CREATE INDEX ix_grant_fact ON core.fact_grant (fact_id, status);
CREATE INDEX ix_grant_expire ON core.fact_grant (expires_at) WHERE status =
    'active';

CREATE TABLE core.model_transfer_consent (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id uuid NOT NULL,
    provider varchar(64) NOT NULL,
    field_scope varchar(200) NOT NULL,
    purpose varchar(64) NOT NULL,
    status consent_status DEFAULT 'granted' NOT NULL,
    granted_at timestamptz DEFAULT now() NOT NULL,
    revoked_at timestamptz,
CONSTRAINT ck_consent_revoke CHECK ((status = 'revoked') = (revoked_at IS NOT
        NULL)),
    CONSTRAINT fk_model_transfer_consent_user_id FOREIGN KEY (user_id),
        REFERENCES core.app_user (id) ON DELETE CASCADE
);
CREATE INDEX ix_consent_user ON core.model_transfer_consent (user_id, status,
    provider);

CREATE TABLE core.matter_info_item (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    matter_id uuid NOT NULL,
    user_id uuid NOT NULL,
    item_type varchar(24) NOT NULL,
    title varchar(160) NOT NULL,
    content_ref varchar(512),
    source_url varchar(500),
    trust_level varchar(16) DEFAULT 'unverified' NOT NULL,
    status varchar(16) DEFAULT 'active' NOT NULL,
    created_at timestamptz DEFAULT now() NOT NULL,
CONSTRAINT ck_info_type CHECK (item_type IN
        ('repost','screenshot','note','communication')),
    CONSTRAINT fk_matter_info_item_matter_id FOREIGN KEY (matter_id),
        REFERENCES core.matter (id) ON DELETE CASCADE,
    CONSTRAINT fk_matter_info_item_user_id FOREIGN KEY (user_id),
        REFERENCES core.app_user (id) ON DELETE CASCADE
);
CREATE INDEX ix_info_matter ON core.matter_info_item (matter_id, item_type);

CREATE TABLE core.material (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    matter_id uuid NOT NULL,
    requirement_id uuid,
    material_type varchar(48) NOT NULL,
    current_version_id uuid,
    created_at timestamptz DEFAULT now() NOT NULL,
    CONSTRAINT fk_material_matter_id FOREIGN KEY (matter_id),
        REFERENCES core.matter (id) ON DELETE CASCADE,
    CONSTRAINT fk_material_requirement_id FOREIGN KEY (requirement_id),
        REFERENCES core.requirement (id) ON DELETE SET NULL
);
CREATE INDEX ix_material_matter ON core.material (matter_id, material_type);

CREATE TABLE core.material_version (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    material_id uuid NOT NULL,
    version_no integer NOT NULL,
    docx_object_key varchar(512) NOT NULL,
    diff jsonb,
    accepted_patches jsonb,
    authors text,
    contributors text,
    contribution_confirmed boolean DEFAULT false NOT NULL,
    status varchar(16) DEFAULT 'draft' NOT NULL,
    created_at timestamptz DEFAULT now() NOT NULL,
    CONSTRAINT uq_material_version_no UNIQUE (material_id, version_no),
CONSTRAINT ck_mv_final CHECK (status <> 'final' OR contribution_confirmed = true),
    CONSTRAINT fk_material_version_material_id FOREIGN KEY (material_id),
        REFERENCES core.material (id) ON DELETE CASCADE
);
CREATE INDEX ix_mv_material ON core.material_version (material_id, version_no);

CREATE TABLE core.candidate_plan (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    matter_id uuid NOT NULL,
    version_no integer NOT NULL,
    status plan_status DEFAULT 'draft' NOT NULL,
    basis_version varchar(64) NOT NULL,
    generated_at timestamptz DEFAULT now() NOT NULL,
    confirmed_at timestamptz,
    confirmed_by uuid,
    op_id uuid,
    CONSTRAINT uq_plan_version UNIQUE (matter_id, version_no),
    CONSTRAINT uq_plan_op UNIQUE (op_id),
CONSTRAINT ck_plan_confirm CHECK ((status = 'confirmed') = (confirmed_at IS NOT
        NULL)),
    CONSTRAINT fk_candidate_plan_matter_id FOREIGN KEY (matter_id),
        REFERENCES core.matter (id) ON DELETE CASCADE,
    CONSTRAINT fk_candidate_plan_confirmed_by FOREIGN KEY (confirmed_by),
        REFERENCES core.app_user (id) ON DELETE SET NULL
);
CREATE INDEX ix_plan_matter ON core.candidate_plan (matter_id, status);
CREATE INDEX ix_plan_pending ON core.candidate_plan (generated_at) WHERE status =
    'pending';

CREATE TABLE core.task (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    matter_id uuid NOT NULL,
    plan_id uuid,
    executor_id uuid NOT NULL,
    title varchar(160) NOT NULL,
    due_at timestamptz,
    status task_status DEFAULT 'pending' NOT NULL,
    completion_evidence text,
    depends_on uuid[],
    created_at timestamptz DEFAULT now() NOT NULL,
    updated_at timestamptz DEFAULT now() NOT NULL,
CONSTRAINT ck_task_done CHECK ((status = 'done') = (completion_evidence IS NOT
        NULL)),
    CONSTRAINT fk_task_matter_id FOREIGN KEY (matter_id),
        REFERENCES core.matter (id) ON DELETE CASCADE,
    CONSTRAINT fk_task_plan_id FOREIGN KEY (plan_id),
        REFERENCES core.candidate_plan (id) ON DELETE SET NULL,
    CONSTRAINT fk_task_executor_id FOREIGN KEY (executor_id),
        REFERENCES core.app_user (id) ON DELETE RESTRICT
);
CREATE INDEX ix_task_matter ON core.task (matter_id, status);
CREATE INDEX ix_task_due ON core.task (due_at) WHERE status <> 'done';
CREATE INDEX ix_task_depends ON core.task USING GIN (depends_on);

CREATE TABLE core.inbox_item (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id uuid NOT NULL,
    item_type varchar(24) NOT NULL,
    object_type varchar(32),
    object_id uuid,
    title varchar(200) NOT NULL,
    status inbox_status DEFAULT 'open' NOT NULL,
    created_at timestamptz DEFAULT now() NOT NULL,
    resolved_at timestamptz,
CONSTRAINT ck_inbox_type CHECK (item_type IN
        ('notice','question','blocked','approval','failure')),
CONSTRAINT ck_inbox_resolved CHECK ((status IN ('resolved','ignored')) =
        (resolved_at IS NOT NULL)),
    CONSTRAINT fk_inbox_item_user_id FOREIGN KEY (user_id),
        REFERENCES core.app_user (id) ON DELETE CASCADE
);
CREATE INDEX ix_inbox_user ON core.inbox_item (user_id, status, created_at);
CREATE INDEX ix_inbox_open ON core.inbox_item (created_at) WHERE status = 'open';

CREATE TABLE core.submission_evidence (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    matter_id uuid NOT NULL,
    evidence_kind varchar(24) NOT NULL,
    operator_id uuid,
    occurred_at timestamptz NOT NULL,
    file_ref varchar(512),
    note text,
CONSTRAINT ck_submit_kind CHECK (evidence_kind IN
        ('self_confirm','official_receipt')),
    CONSTRAINT fk_submission_evidence_matter_id FOREIGN KEY (matter_id),
        REFERENCES core.matter (id) ON DELETE CASCADE,
    CONSTRAINT fk_submission_evidence_operator_id FOREIGN KEY (operator_id),
        REFERENCES core.app_user (id) ON DELETE SET NULL
);
CREATE INDEX ix_submit_matter ON core.submission_evidence (matter_id,
    evidence_kind);

CREATE TABLE core.official_result (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    matter_id uuid NOT NULL,
    result_type varchar(24) NOT NULL,
    status varchar(16) DEFAULT 'pending' NOT NULL,
    source_text varchar(200),
    evidence_id uuid,
    occurred_at timestamptz,
    CONSTRAINT uq_result_type UNIQUE (matter_id, result_type),
CONSTRAINT ck_result_type CHECK (result_type IN
        ('selection','registration','award','admission')),
    CONSTRAINT ck_result_status CHECK (status IN ('pending','confirmed')),
    CONSTRAINT fk_official_result_matter_id FOREIGN KEY (matter_id),
        REFERENCES core.matter (id) ON DELETE CASCADE,
    CONSTRAINT fk_official_result_evidence_id FOREIGN KEY (evidence_id),
        REFERENCES core.submission_evidence (id) ON DELETE SET NULL
);
CREATE INDEX ix_result_matter ON core.official_result (matter_id);
CREATE INDEX ix_result_pending ON core.official_result (status) WHERE status =
    'pending';

-- ============ ops 模式：来源、证据与审计 ============

CREATE TABLE ops.audit_log (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    actor_id uuid,
    action varchar(64) NOT NULL,
    object_type varchar(32) NOT NULL,
    object_id uuid,
    object_version varchar(64),
    rule_version varchar(32),
    result varchar(16) DEFAULT 'success' NOT NULL,
    detail jsonb,
    created_at timestamptz DEFAULT now() NOT NULL,
    CONSTRAINT ck_audit_result CHECK (result IN ('success','failure','denied')),
    CONSTRAINT fk_audit_log_actor_id FOREIGN KEY (actor_id),
        REFERENCES core.app_user (id) ON DELETE SET NULL
);
CREATE INDEX ix_audit_object ON ops.audit_log (object_type, object_id, created_at);
CREATE INDEX ix_audit_actor ON ops.audit_log (actor_id, created_at);
CREATE INDEX ix_audit_created_brin ON ops.audit_log USING BRIN (created_at);

-- ============ 环状外键（建表后补充） ============
ALTER TABLE core.template ADD CONSTRAINT fk_template_current_version_id
    FOREIGN KEY (current_version_id) REFERENCES core.template_version (id)
    ON DELETE SET NULL DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE core.personal_document ADD CONSTRAINT
    fk_personal_document_current_version_id
    FOREIGN KEY (current_version_id) REFERENCES core.document_version (id)
    ON DELETE SET NULL DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE core.material ADD CONSTRAINT fk_material_current_version_id
    FOREIGN KEY (current_version_id) REFERENCES core.material_version (id)
    ON DELETE SET NULL DEFERRABLE INITIALLY DEFERRED;

COMMIT;