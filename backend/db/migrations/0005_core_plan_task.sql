-- 0005_core_plan_task.sql
-- OfferPilot Alpha · 候选计划、计划项、计划决定、个人任务
--
-- 来源：docs/development/alpha-scope-contract.md §3、§4.1。

CREATE TABLE core.candidate_plan (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    matter_id     uuid NOT NULL,
    version_no    integer NOT NULL,
    status        core.plan_status NOT NULL DEFAULT 'draft',
    basis_version char(64) NOT NULL,
    basis_input   jsonb NOT NULL,
    generated_at  timestamptz NOT NULL DEFAULT now(),
    confirmed_at  timestamptz,
    expired_at    timestamptz,
    confirmed_by  uuid,
    op_id         uuid,
    CONSTRAINT fk_candidate_plan_matter FOREIGN KEY (matter_id)
        REFERENCES core.matter (id) ON DELETE CASCADE,
    CONSTRAINT fk_candidate_plan_confirmed_by FOREIGN KEY (confirmed_by)
        REFERENCES core.app_user (id) ON DELETE SET NULL,
    CONSTRAINT uq_plan_version UNIQUE (matter_id, version_no),
    CONSTRAINT uq_plan_op UNIQUE (op_id),
    CONSTRAINT ck_plan_version CHECK (version_no > 0),
    CONSTRAINT ck_plan_basis_version CHECK (basis_version ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_plan_basis_input CHECK (jsonb_typeof(basis_input) = 'object'),
    CONSTRAINT ck_plan_state_time CHECK (
        (status = 'confirmed' AND confirmed_at IS NOT NULL AND expired_at IS NULL)
        OR (status = 'expired' AND expired_at IS NOT NULL AND confirmed_at IS NULL)
        OR (status IN ('draft', 'pending', 'rejected')
            AND confirmed_at IS NULL AND expired_at IS NULL)
    )
);

COMMENT ON TABLE core.candidate_plan IS
    '由要求与事实生成的候选任务集合；确认前不产生正式任务';
COMMENT ON COLUMN core.candidate_plan.basis_version IS
    '规范化依据输入的 SHA-256；确认时重算比对';
COMMENT ON COLUMN core.candidate_plan.basis_input IS
    '生成时的完整规范化输入，供确认重算与审计';
COMMENT ON COLUMN core.candidate_plan.op_id IS
    '确认操作的幂等键；确认成功时写入，拒绝保持为空';

CREATE INDEX ix_plan_matter ON core.candidate_plan (matter_id, status);
CREATE INDEX ix_plan_pending ON core.candidate_plan (generated_at)
    WHERE status = 'pending';

CREATE TABLE core.candidate_plan_item (
    id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    plan_id               uuid NOT NULL,
    seq                   smallint NOT NULL,
    title                 varchar(160) NOT NULL,
    detail                text,
    obligation_nature     core.obligation_nature NOT NULL DEFAULT 'to_verify',
    official_deadline_date date,
    official_deadline_at   timestamptz,
    suggested_date         date,
    depends_on_item_ids    uuid[] NOT NULL DEFAULT '{}',
    evidence_required      boolean NOT NULL DEFAULT false,
    requirement_id         uuid,
    created_at             timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_plan_item_plan FOREIGN KEY (plan_id)
        REFERENCES core.candidate_plan (id) ON DELETE CASCADE,
    CONSTRAINT fk_plan_item_requirement FOREIGN KEY (requirement_id)
        REFERENCES core.requirement (id) ON DELETE SET NULL,
    CONSTRAINT uq_plan_item_seq UNIQUE (plan_id, seq),
    CONSTRAINT ck_plan_item_seq CHECK (seq > 0),
    CONSTRAINT ck_plan_item_title CHECK (length(btrim(title)) > 0),
    CONSTRAINT ck_plan_item_depends CHECK (cardinality(depends_on_item_ids) <= 50)
);

COMMENT ON TABLE core.candidate_plan_item IS
    '候选计划中的一条候选任务；确认前即可持久化、读取和审阅';
COMMENT ON COLUMN core.candidate_plan_item.official_deadline_date IS
    '来源明确给出的日期；date-only 期限只写此列';
COMMENT ON COLUMN core.candidate_plan_item.official_deadline_at IS
    '来源给出具体时刻时填写；不得为 date-only 期限补造时刻';
COMMENT ON COLUMN core.candidate_plan_item.suggested_date IS
    'Agent 给出的个人建议准备日，与官方期限分列';

CREATE INDEX ix_plan_item_plan ON core.candidate_plan_item (plan_id, seq);
CREATE INDEX ix_plan_item_requirement ON core.candidate_plan_item (requirement_id)
    WHERE requirement_id IS NOT NULL;
CREATE INDEX ix_plan_item_depends ON core.candidate_plan_item USING GIN (depends_on_item_ids);

CREATE FUNCTION core.check_plan_item_depends() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    invalid_id uuid;
BEGIN
    IF NEW.depends_on_item_ids IS NULL OR cardinality(NEW.depends_on_item_ids) = 0 THEN
        RETURN NEW;
    END IF;

    IF NEW.id = ANY(NEW.depends_on_item_ids) THEN
        RAISE EXCEPTION '候选计划项 % 不能依赖自身', NEW.id
            USING ERRCODE = '23514';
    END IF;

    SELECT d.id INTO invalid_id
      FROM unnest(NEW.depends_on_item_ids) AS d(id)
     WHERE NOT EXISTS (
         SELECT 1 FROM core.candidate_plan_item i
          WHERE i.id = d.id AND i.plan_id = NEW.plan_id
     )
     LIMIT 1;

    IF FOUND THEN
        RAISE EXCEPTION '候选计划项依赖 % 不在同一计划内', invalid_id
            USING ERRCODE = '23514';
    END IF;

    RETURN NEW;
END $$;

CREATE TRIGGER trg_plan_item_depends
    BEFORE INSERT OR UPDATE OF depends_on_item_ids, plan_id ON core.candidate_plan_item
    FOR EACH ROW EXECUTE FUNCTION core.check_plan_item_depends();

CREATE TABLE core.candidate_plan_decision (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    plan_id      uuid NOT NULL,
    decision     varchar(16) NOT NULL,
    decided_by   uuid NOT NULL,
    decided_at   timestamptz NOT NULL DEFAULT now(),
    operation_id uuid NOT NULL,
    CONSTRAINT fk_decision_plan FOREIGN KEY (plan_id)
        REFERENCES core.candidate_plan (id) ON DELETE CASCADE,
    CONSTRAINT fk_decision_decided_by FOREIGN KEY (decided_by)
        REFERENCES core.app_user (id) ON DELETE RESTRICT,
    CONSTRAINT uq_decision_plan UNIQUE (plan_id),
    CONSTRAINT uq_decision_operation UNIQUE (operation_id),
    CONSTRAINT ck_decision_value CHECK (decision IN ('confirmed', 'rejected'))
);

COMMENT ON TABLE core.candidate_plan_decision IS
    '候选版本的终态决定；每个候选版本至多一条';

CREATE FUNCTION core.check_plan_decision() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    plan_status core.plan_status;
    plan_op_id uuid;
BEGIN
    SELECT status, op_id INTO plan_status, plan_op_id
      FROM core.candidate_plan
     WHERE id = NEW.plan_id
     FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION '候选计划 % 不存在', NEW.plan_id
            USING ERRCODE = '23503';
    END IF;

    IF NEW.decision = 'confirmed' THEN
        IF plan_status <> 'confirmed' THEN
            RAISE EXCEPTION '候选计划 % 尚未确认，不能写确认决定', NEW.plan_id
                USING ERRCODE = '23514';
        END IF;
        IF plan_op_id IS DISTINCT FROM NEW.operation_id THEN
            RAISE EXCEPTION '确认决定 operation_id 与计划 op_id 不一致'
                USING ERRCODE = '23514';
        END IF;
    ELSE
        IF plan_status <> 'rejected' THEN
            RAISE EXCEPTION '候选计划 % 尚未拒绝，不能写拒绝决定', NEW.plan_id
                USING ERRCODE = '23514';
        END IF;
        IF plan_op_id IS NOT NULL THEN
            RAISE EXCEPTION '拒绝决定不得写入 op_id'
                USING ERRCODE = '23514';
        END IF;
    END IF;

    RETURN NEW;
END $$;

CREATE TRIGGER trg_plan_decision_guard
    BEFORE INSERT ON core.candidate_plan_decision
    FOR EACH ROW EXECUTE FUNCTION core.check_plan_decision();

CREATE TABLE core.candidate_plan_item_source (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    plan_item_id uuid NOT NULL,
    source_id    uuid NOT NULL,
    snapshot_id  uuid NOT NULL,
    locator_kind varchar(16) NOT NULL,
    locator      varchar(300) NOT NULL,
    quote        text,
    CONSTRAINT fk_item_source_item FOREIGN KEY (plan_item_id)
        REFERENCES core.candidate_plan_item (id) ON DELETE CASCADE,
    CONSTRAINT fk_item_source_source FOREIGN KEY (source_id)
        REFERENCES ops.source (id) ON DELETE RESTRICT,
    CONSTRAINT fk_item_source_snapshot FOREIGN KEY (snapshot_id)
        REFERENCES ops.snapshot (id) ON DELETE RESTRICT,
    CONSTRAINT uq_item_source_locator UNIQUE (plan_item_id, snapshot_id, locator),
    CONSTRAINT ck_item_source_locator_kind CHECK (
        locator_kind IN ('text_span', 'page', 'table_row', 'section')
    ),
    CONSTRAINT ck_item_source_locator_text CHECK (length(btrim(locator)) > 0)
);

COMMENT ON TABLE core.candidate_plan_item_source IS
    '候选计划项的来源定位；确认后任务经 plan_item_id 延续该证据链';

CREATE INDEX ix_item_source_item ON core.candidate_plan_item_source (plan_item_id);
CREATE INDEX ix_item_source_snapshot ON core.candidate_plan_item_source (snapshot_id);

CREATE FUNCTION core.check_item_source_snapshot() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    snapshot_source uuid;
BEGIN
    SELECT source_id INTO snapshot_source
      FROM ops.snapshot
     WHERE id = NEW.snapshot_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION '快照 % 不存在', NEW.snapshot_id
            USING ERRCODE = '23503';
    END IF;

    IF snapshot_source IS DISTINCT FROM NEW.source_id THEN
        RAISE EXCEPTION '来源 % 与快照 % 不一致', NEW.source_id, NEW.snapshot_id
            USING ERRCODE = '23514';
    END IF;

    RETURN NEW;
END $$;

CREATE TRIGGER trg_item_source_snapshot
    BEFORE INSERT OR UPDATE ON core.candidate_plan_item_source
    FOR EACH ROW EXECUTE FUNCTION core.check_item_source_snapshot();

CREATE TABLE core.task (
    id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    matter_id             uuid NOT NULL,
    plan_id               uuid,
    plan_item_id          uuid,
    executor_id           uuid NOT NULL,
    title                 varchar(160) NOT NULL,
    due_at                timestamptz,
    official_deadline_date date,
    official_deadline_at   timestamptz,
    suggested_date         date,
    status                core.task_status NOT NULL DEFAULT 'pending',
    completion_evidence   text,
    depends_on            uuid[],
    created_at            timestamptz NOT NULL DEFAULT now(),
    updated_at            timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_task_matter FOREIGN KEY (matter_id)
        REFERENCES core.matter (id) ON DELETE CASCADE,
    CONSTRAINT fk_task_plan FOREIGN KEY (plan_id)
        REFERENCES core.candidate_plan (id) ON DELETE SET NULL,
    CONSTRAINT fk_task_plan_item FOREIGN KEY (plan_item_id)
        REFERENCES core.candidate_plan_item (id) ON DELETE SET NULL,
    CONSTRAINT fk_task_executor FOREIGN KEY (executor_id)
        REFERENCES core.app_user (id) ON DELETE RESTRICT,
    CONSTRAINT uq_task_plan_item UNIQUE (plan_item_id),
    CONSTRAINT ck_task_title CHECK (length(btrim(title)) > 0),
    CONSTRAINT ck_task_done CHECK ((status = 'done') = (completion_evidence IS NOT NULL)),
    CONSTRAINT ck_task_depends CHECK (depends_on IS NULL OR cardinality(depends_on) <= 50)
);

COMMENT ON TABLE core.task IS
    '用户确认后写入的正式任务；候选计划被拒绝时不产生任何行';
COMMENT ON COLUMN core.task.plan_item_id IS
    '来源候选条目，唯一；并发重试不会为同一条目创建第二个任务';
COMMENT ON COLUMN core.task.official_deadline_date IS
    '官方期限日期；date-only 期限只写此列';
COMMENT ON COLUMN core.task.official_deadline_at IS
    '官方期限时刻；来源给出具体时刻时填写';
COMMENT ON COLUMN core.task.suggested_date IS
    '个人建议准备日，与官方期限分列';

CREATE INDEX ix_task_matter ON core.task (matter_id, status);
CREATE INDEX ix_task_due ON core.task (due_at) WHERE status <> 'done';
CREATE INDEX ix_task_plan ON core.task (plan_id);
CREATE INDEX ix_task_depends ON core.task USING GIN (depends_on);

CREATE TRIGGER trg_task_touch
    BEFORE UPDATE ON core.task
    FOR EACH ROW EXECUTE FUNCTION core.touch_updated_at();

CREATE FUNCTION core.check_task_links() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    plan_matter uuid;
    plan_status core.plan_status;
    item_plan   uuid;
BEGIN
    IF NEW.plan_item_id IS NOT NULL AND NEW.plan_id IS NULL THEN
        RAISE EXCEPTION '任务引用了候选计划项 % 却没有 plan_id', NEW.plan_item_id
            USING ERRCODE = '23514';
    END IF;

    IF TG_OP = 'INSERT' THEN
        IF NEW.plan_id IS NOT NULL THEN
            SELECT matter_id, status INTO plan_matter, plan_status
              FROM core.candidate_plan
             WHERE id = NEW.plan_id;

            IF NOT FOUND THEN
                RAISE EXCEPTION '任务引用的候选计划 % 不存在', NEW.plan_id
                    USING ERRCODE = '23503';
            END IF;

            IF plan_matter IS DISTINCT FROM NEW.matter_id THEN
                RAISE EXCEPTION '任务事项 % 与候选计划事项 % 不一致',
                    NEW.matter_id, plan_matter
                    USING ERRCODE = '23514';
            END IF;

            IF plan_status <> 'confirmed' THEN
                RAISE EXCEPTION '候选计划 % 未确认，不能写入正式任务', NEW.plan_id
                    USING ERRCODE = '23514';
            END IF;
        END IF;

        IF NEW.plan_item_id IS NOT NULL THEN
            SELECT plan_id INTO item_plan
              FROM core.candidate_plan_item
             WHERE id = NEW.plan_item_id;

            IF NOT FOUND THEN
                RAISE EXCEPTION '任务引用的候选计划项 % 不存在', NEW.plan_item_id
                    USING ERRCODE = '23503';
            END IF;

            IF item_plan IS DISTINCT FROM NEW.plan_id THEN
                RAISE EXCEPTION '候选计划项 % 不属于计划 %', NEW.plan_item_id, NEW.plan_id
                    USING ERRCODE = '23514';
            END IF;
        END IF;
    ELSE
        IF NEW.plan_id IS DISTINCT FROM OLD.plan_id AND NEW.plan_id IS NOT NULL THEN
            SELECT matter_id, status INTO plan_matter, plan_status
              FROM core.candidate_plan
             WHERE id = NEW.plan_id;

            IF NOT FOUND THEN
                RAISE EXCEPTION '任务引用的候选计划 % 不存在', NEW.plan_id
                    USING ERRCODE = '23503';
            END IF;

            IF plan_matter IS DISTINCT FROM NEW.matter_id THEN
                RAISE EXCEPTION '任务事项 % 与候选计划事项 % 不一致',
                    NEW.matter_id, plan_matter
                    USING ERRCODE = '23514';
            END IF;

            IF plan_status <> 'confirmed' THEN
                RAISE EXCEPTION '候选计划 % 未确认，不能写入正式任务', NEW.plan_id
                    USING ERRCODE = '23514';
            END IF;
        END IF;

        IF NEW.plan_item_id IS DISTINCT FROM OLD.plan_item_id
           AND NEW.plan_item_id IS NOT NULL
           AND NEW.plan_id IS NOT NULL
        THEN
            SELECT plan_id INTO item_plan
              FROM core.candidate_plan_item
             WHERE id = NEW.plan_item_id;

            IF NOT FOUND THEN
                RAISE EXCEPTION '任务引用的候选计划项 % 不存在', NEW.plan_item_id
                    USING ERRCODE = '23503';
            END IF;

            IF item_plan IS DISTINCT FROM NEW.plan_id THEN
                RAISE EXCEPTION '候选计划项 % 不属于计划 %', NEW.plan_item_id, NEW.plan_id
                    USING ERRCODE = '23514';
            END IF;
        END IF;
    END IF;

    RETURN NEW;
END $$;

CREATE TRIGGER trg_task_links
    BEFORE INSERT OR UPDATE OF plan_id, plan_item_id, matter_id ON core.task
    FOR EACH ROW EXECUTE FUNCTION core.check_task_links();