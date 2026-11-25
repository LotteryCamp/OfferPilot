-- 0003_ops_source_snapshot.sql
-- OfferPilot · 公开来源与不可变快照
--
-- 来源：说明书 §5.2.2（表 5-11、5-12）、§7.6（快照幂等）。
--
-- 设计要点：
--   * source 是全体登录用户共享只读的官方信息入口，不属于某个工作区。
--   * snapshot 只增不改；同一来源同一内容只保留一条，靠 UNIQUE(source_id, content_hash) 去重。
--   * 同一来源至多一条 is_current，由部分唯一索引 + 触发器共同保证。

CREATE TABLE ops.source (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    publisher         varchar(160) NOT NULL,
    url               varchar(500) NOT NULL,
    matter_type_id    uuid,
    scope             varchar(200),
    scope_year        smallint,
    valid_from        date,
    valid_to          date,
    status            ops.source_status NOT NULL DEFAULT 'active',
    auto_check_status ops.check_result NOT NULL DEFAULT 'pending',
    roi_status        varchar(16) NOT NULL DEFAULT 'original',
    last_fetched_at   timestamptz,
    created_at        timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_source_url UNIQUE (url),
    CONSTRAINT fk_source_matter_type FOREIGN KEY (matter_type_id)
        REFERENCES core.matter_type (id) ON DELETE SET NULL,
    CONSTRAINT ck_source_roi CHECK (
        roi_status IN ('original', 'reposted', 'expired', 'ambiguous')
    ),
    CONSTRAINT ck_source_range CHECK (
        valid_from IS NULL OR valid_to IS NULL OR valid_from <= valid_to
    ),
    CONSTRAINT ck_source_year CHECK (scope_year IS NULL OR scope_year BETWEEN 2020 AND 2100),
    CONSTRAINT ck_source_publisher CHECK (length(btrim(publisher)) > 0)
);

COMMENT ON TABLE ops.source IS '官方来源登记；共享只读，撤回只置 status，不物理删除';
COMMENT ON COLUMN ops.source.roi_status IS 'original/reposted/expired/ambiguous，避免把转载当依据（AC14）';

CREATE INDEX ix_source_type_year ON ops.source (matter_type_id, scope_year);
CREATE INDEX ix_source_status ON ops.source (status, auto_check_status);

CREATE TABLE ops.snapshot (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id    uuid NOT NULL,
    version_no   integer NOT NULL,
    object_key   varchar(512) NOT NULL,
    content_hash char(64) NOT NULL,
    html_version varchar(32),
    text_version varchar(32),
    extraction   jsonb,
    fetched_at   timestamptz NOT NULL DEFAULT now(),
    is_current   boolean NOT NULL DEFAULT true,
    CONSTRAINT fk_snapshot_source FOREIGN KEY (source_id)
        REFERENCES ops.source (id) ON DELETE RESTRICT,
    CONSTRAINT uq_snapshot_version UNIQUE (source_id, version_no),
    CONSTRAINT uq_snapshot_hash UNIQUE (source_id, content_hash),
    CONSTRAINT ck_snapshot_version CHECK (version_no > 0),
    CONSTRAINT ck_snapshot_hash CHECK (content_hash ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_snapshot_object_key CHECK (length(btrim(object_key)) > 0),
    CONSTRAINT ck_snapshot_extraction CHECK (
        extraction IS NULL OR jsonb_typeof(extraction) = 'object'
    )
);

COMMENT ON TABLE ops.snapshot IS '来源在某一时刻的完整留存，只增不改（D-10）';
COMMENT ON COLUMN ops.snapshot.object_key IS
    '对象存储键；未接入对象存储时约定为 inline:<sha256>，正文可放在 extraction->>''text''';

CREATE UNIQUE INDEX ix_snapshot_current ON ops.snapshot (source_id) WHERE is_current;
CREATE INDEX ix_snapshot_fetched ON ops.snapshot (fetched_at);

-- 切换当前快照：把同来源旧版本标记清零。唯一部分索引是最终防线。
CREATE FUNCTION ops.keep_single_current_snapshot() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.is_current THEN
        UPDATE ops.snapshot
           SET is_current = false
         WHERE source_id = NEW.source_id
           AND id <> NEW.id
           AND is_current;
    END IF;
    RETURN NEW;
END $$;

CREATE TRIGGER trg_snapshot_current
    BEFORE INSERT OR UPDATE OF is_current ON ops.snapshot
    FOR EACH ROW EXECUTE FUNCTION ops.keep_single_current_snapshot();

CREATE FUNCTION ops.reject_snapshot_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION '快照 % 只增不改，禁止删除', OLD.id
            USING ERRCODE = '23514';
    END IF;

    IF ROW(
        NEW.id, NEW.source_id, NEW.version_no, NEW.object_key, NEW.content_hash,
        NEW.html_version, NEW.text_version, NEW.extraction, NEW.fetched_at
    ) IS DISTINCT FROM ROW(
        OLD.id, OLD.source_id, OLD.version_no, OLD.object_key, OLD.content_hash,
        OLD.html_version, OLD.text_version, OLD.extraction, OLD.fetched_at
    ) THEN
        RAISE EXCEPTION '快照 % 只增不改，仅允许切换 is_current', NEW.id
            USING ERRCODE = '23514';
    END IF;

    RETURN NEW;
END $$;

CREATE TRIGGER trg_snapshot_immutable
    BEFORE UPDATE OR DELETE ON ops.snapshot
    FOR EACH ROW EXECUTE FUNCTION ops.reject_snapshot_mutation();