-- 0012_core_fact_matter.sql
-- OfferPilot · 个人事实按事项归属
--
-- 事实归属由用户与事项共同确定；版本、当前确认记录与唯一约束按事项隔离。
-- 0012 之前保存的用户级记录保留为未归属历史：matter_id 为空，读取接口与
-- Agent 运行均不返回这些记录，避免同一份用户级事实被多个事项自动复用。

ALTER TABLE core.fact ADD COLUMN matter_id uuid;

ALTER TABLE core.fact
    ADD CONSTRAINT fk_fact_matter FOREIGN KEY (matter_id)
    REFERENCES core.matter (id) ON DELETE CASCADE;

DROP INDEX core.uq_fact_current;
DROP INDEX core.ix_fact_owner;

ALTER TABLE core.fact DROP CONSTRAINT uq_fact_type_version;
ALTER TABLE core.fact
    ADD CONSTRAINT uq_fact_type_version
    UNIQUE (owner_id, matter_id, fact_type, version_no);

CREATE UNIQUE INDEX uq_fact_current
    ON core.fact (owner_id, matter_id, fact_type)
    WHERE confirm_status = 'confirmed' AND matter_id IS NOT NULL;

CREATE INDEX ix_fact_owner
    ON core.fact (owner_id, matter_id, fact_type);

COMMENT ON TABLE core.fact IS
    '按事项隔离的个人事实当前确认版本与历史版本；同一用户、同一事项、同一类型只有一条 confirmed 记录';
COMMENT ON COLUMN core.fact.matter_id IS
    '事实所属事项；为空的历史用户级记录不参与事项读取、候选依据与 Agent 运行';

DROP POLICY fact_owner ON core.fact;

CREATE POLICY fact_by_matter ON core.fact
    USING (EXISTS (
        SELECT 1
        FROM core.matter m
        JOIN core.workspace w ON w.id = m.workspace_id
        WHERE m.id = fact.matter_id
          AND m.workspace_id = NULLIF(current_setting('app.current_workspace_id', true), '')::uuid
          AND w.owner_id = fact.owner_id
    ))
    WITH CHECK (EXISTS (
        SELECT 1
        FROM core.matter m
        JOIN core.workspace w ON w.id = m.workspace_id
        WHERE m.id = fact.matter_id
          AND m.workspace_id = NULLIF(current_setting('app.current_workspace_id', true), '')::uuid
          AND w.owner_id = fact.owner_id
    ));
