-- 0004_requirement_evidence.sql
-- OfferPilot Alpha · 要求与证据
--
-- 来源：说明书 §5.2.3（表 5-15）、§5.2.2（表 5-14）、§5.6（证据触发器）。
--
-- 关键约束：
--   * 要求必须绑定一个快照，不能凭空生成；
--   * 证据必须能回答“哪一版的哪一处”：source + snapshot + locator + fetched_at；
--   * 指向要求的证据，其 snapshot 必须等于要求自身的 snapshot（触发器）；
--   * 证据 fetched_at 必须等于快照 fetched_at（触发器）。
--
-- evaluation / mentor_contact_rule / source_gap 不在 Alpha 主流程，未建表。

CREATE TABLE core.requirement (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    matter_id         uuid NOT NULL,
    snapshot_id       uuid NOT NULL,
    field_key         varchar(64) NOT NULL,
    label             varchar(120) NOT NULL,
    obligation_nature core.obligation_nature NOT NULL DEFAULT 'to_verify',
    extract_status    core.extract_status NOT NULL DEFAULT 'extracted',
    scope             varchar(200),
    value_text        text,
    value_type        varchar(16) NOT NULL DEFAULT 'text',
    confidence        numeric(4,3),
    checked_at        timestamptz,
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_requirement_matter FOREIGN KEY (matter_id)
        REFERENCES core.matter (id) ON DELETE CASCADE,
    CONSTRAINT fk_requirement_snapshot FOREIGN KEY (snapshot_id)
        REFERENCES ops.snapshot (id) ON DELETE RESTRICT,
    CONSTRAINT ck_req_field_key CHECK (field_key ~ '^[a-z][a-z0-9_.]{1,63}$'),
    CONSTRAINT ck_req_label CHECK (length(btrim(label)) > 0),
    CONSTRAINT ck_req_value_type CHECK (
        value_type IN ('text', 'date', 'number', 'boolean', 'enum')
    ),
    CONSTRAINT ck_req_confidence CHECK (
        confidence IS NULL OR (confidence >= 0 AND confidence <= 1)
    ),
    CONSTRAINT ck_req_checked CHECK ((extract_status = 'checked') = (checked_at IS NOT NULL))
);

COMMENT ON TABLE core.requirement IS '从事项来源中抽取的结构化要求；只有基于官方快照才能作为依据';
COMMENT ON COLUMN core.requirement.obligation_nature IS
    'required 官方必需 / advised 建议 / optional 可选 / to_verify 待核实，独立于四态结论';

CREATE INDEX ix_req_matter ON core.requirement (matter_id, field_key);
CREATE INDEX ix_req_snapshot ON core.requirement (snapshot_id);
CREATE INDEX ix_req_status ON core.requirement (extract_status)
    WHERE extract_status = 'to_review';

CREATE TRIGGER trg_requirement_touch
    BEFORE UPDATE ON core.requirement
    FOR EACH ROW EXECUTE FUNCTION core.touch_updated_at();

CREATE TABLE ops.evidence (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id    uuid NOT NULL,
    snapshot_id  uuid NOT NULL,
    target_type  varchar(24) NOT NULL,
    target_id    uuid NOT NULL,
    locator_kind varchar(16) NOT NULL,
    locator      varchar(300) NOT NULL,
    quote        text,
    quote_hash   char(64),
    fetched_at   timestamptz NOT NULL,
    CONSTRAINT fk_evidence_source FOREIGN KEY (source_id)
        REFERENCES ops.source (id) ON DELETE RESTRICT,
    CONSTRAINT fk_evidence_snapshot FOREIGN KEY (snapshot_id)
        REFERENCES ops.snapshot (id) ON DELETE RESTRICT,
    CONSTRAINT uq_evidence_quad UNIQUE (snapshot_id, target_type, target_id, locator),
    CONSTRAINT ck_evidence_target CHECK (
        target_type IN ('requirement', 'evaluation', 'material_version')
    ),
    CONSTRAINT ck_evidence_locator CHECK (
        locator_kind IN ('text_span', 'page', 'table_row', 'section')
    ),
    CONSTRAINT ck_evidence_locator_text CHECK (length(btrim(locator)) > 0),
    CONSTRAINT ck_evidence_hash CHECK (
        quote_hash IS NULL OR quote_hash ~ '^[0-9a-f]{64}$'
    )
);

COMMENT ON TABLE ops.evidence IS '证据四元组 {source, snapshot, locator, fetched_at} 的多态落库';

CREATE INDEX ix_evidence_target ON ops.evidence (target_type, target_id);
CREATE INDEX ix_evidence_snapshot ON ops.evidence (snapshot_id);

CREATE FUNCTION ops.check_evidence_snapshot() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    target_snapshot uuid;
BEGIN
    IF NEW.target_type = 'requirement' THEN
        SELECT snapshot_id INTO target_snapshot
          FROM core.requirement
         WHERE id = NEW.target_id;

        IF NOT FOUND THEN
            RAISE EXCEPTION '证据指向的要求 % 不存在', NEW.target_id
                USING ERRCODE = '23503';
        END IF;

        IF target_snapshot IS DISTINCT FROM NEW.snapshot_id THEN
            RAISE EXCEPTION '证据快照 % 与要求快照 % 不一致',
                NEW.snapshot_id, target_snapshot
                USING ERRCODE = '23514';
        END IF;
    END IF;
    RETURN NEW;
END $$;

CREATE FUNCTION ops.check_evidence_fetched() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    snapshot_source  uuid;
    snapshot_fetched timestamptz;
BEGIN
    SELECT source_id, fetched_at INTO snapshot_source, snapshot_fetched
      FROM ops.snapshot
     WHERE id = NEW.snapshot_id;

    IF snapshot_source IS DISTINCT FROM NEW.source_id THEN
        RAISE EXCEPTION '证据来源 % 与快照 % 的来源 % 不一致',
            NEW.source_id, NEW.snapshot_id, snapshot_source
            USING ERRCODE = '23514';
    END IF;

    IF NEW.fetched_at IS DISTINCT FROM snapshot_fetched THEN
        RAISE EXCEPTION '证据获取时间 % 与快照获取时间 % 不一致',
            NEW.fetched_at, snapshot_fetched
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $$;

CREATE TRIGGER trg_evidence_snapshot
    BEFORE INSERT OR UPDATE ON ops.evidence
    FOR EACH ROW EXECUTE FUNCTION ops.check_evidence_snapshot();

CREATE TRIGGER trg_evidence_fetched
    BEFORE INSERT OR UPDATE ON ops.evidence
    FOR EACH ROW EXECUTE FUNCTION ops.check_evidence_fetched();

-- 多态目标没有外键，要求被删除时由触发器清理其证据，避免留下孤儿行。
CREATE FUNCTION core.cleanup_requirement_evidence() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    DELETE FROM ops.evidence
     WHERE target_type = 'requirement'
       AND target_id = OLD.id;
    RETURN OLD;
END $$;

CREATE TRIGGER trg_requirement_evidence_cleanup
    AFTER DELETE ON core.requirement
    FOR EACH ROW EXECUTE FUNCTION core.cleanup_requirement_evidence();