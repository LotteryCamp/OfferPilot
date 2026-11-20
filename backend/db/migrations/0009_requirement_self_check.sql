-- 0009_requirement_self_check.sql
-- OfferPilot Alpha · 要求自查结果
--
-- 要求的 extract_status 表示提取记录的核验进度；四态自查结论、判断原因、缺失信息和缺口
-- 单独保存在本表，与 extract_status 各自表达自己的含义。
-- 来源引用继续由 ops.evidence（target_type = 'requirement'）承载。
--
-- conclusion 取值：
--   matched            按现有信息符合
--   not_matched        按现有信息不符合
--   missing_info       待补充信息
--   needs_user_review  待用户核对
--
-- gaps 是 JSON 数组，每项形如：
--   {"gap_type": "...", "description": "...", "locator": "...|null",
--    "source_id": "uuid|null", "snapshot_id": "uuid|null"}

CREATE TABLE core.requirement_self_check (
    requirement_id       uuid PRIMARY KEY,
    conclusion           varchar(24) NOT NULL,
    reason               text NOT NULL,
    missing_fields       text[] NOT NULL DEFAULT '{}',
    computed_deadline_at timestamptz,
    gaps                 jsonb NOT NULL DEFAULT '[]'::jsonb,
    evaluated_at         timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_self_check_requirement FOREIGN KEY (requirement_id)
        REFERENCES core.requirement (id) ON DELETE CASCADE,
    CONSTRAINT ck_self_check_conclusion CHECK (
        conclusion IN ('matched', 'not_matched', 'missing_info', 'needs_user_review')
    ),
    CONSTRAINT ck_self_check_reason CHECK (length(btrim(reason)) > 0),
    CONSTRAINT ck_self_check_gaps CHECK (jsonb_typeof(gaps) = 'array')
);

COMMENT ON TABLE core.requirement_self_check IS '要求的四态自查结论、原因、缺失信息与缺口；独立于 extract_status';

CREATE INDEX ix_self_check_conclusion ON core.requirement_self_check (conclusion);

ALTER TABLE core.requirement_self_check ENABLE ROW LEVEL SECURITY;

CREATE POLICY self_check_by_matter ON core.requirement_self_check
    USING (EXISTS (
        SELECT 1
        FROM core.requirement r
        JOIN core.matter m ON m.id = r.matter_id
        WHERE r.id = requirement_self_check.requirement_id
          AND m.workspace_id = NULLIF(current_setting('app.current_workspace_id', true), '')::uuid
    ))
    WITH CHECK (EXISTS (
        SELECT 1
        FROM core.requirement r
        JOIN core.matter m ON m.id = r.matter_id
        WHERE r.id = requirement_self_check.requirement_id
          AND m.workspace_id = NULLIF(current_setting('app.current_workspace_id', true), '')::uuid
    ));
