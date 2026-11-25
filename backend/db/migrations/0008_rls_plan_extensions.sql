-- 0008_rls_plan_extensions.sql
-- OfferPilot · 候选决定与候选项来源的工作区隔离
--
-- 策略与 0007 相同：以会话变量 app.current_workspace_id 为条件，未设置时默认拒绝。

ALTER TABLE core.candidate_plan_decision ENABLE ROW LEVEL SECURITY;
ALTER TABLE core.candidate_plan_item_source ENABLE ROW LEVEL SECURITY;

CREATE POLICY plan_decision_by_matter ON core.candidate_plan_decision
    USING (EXISTS (
        SELECT 1
        FROM core.candidate_plan p
        JOIN core.matter m ON m.id = p.matter_id
        WHERE p.id = candidate_plan_decision.plan_id
          AND m.workspace_id = NULLIF(current_setting('app.current_workspace_id', true), '')::uuid
    ))
    WITH CHECK (EXISTS (
        SELECT 1
        FROM core.candidate_plan p
        JOIN core.matter m ON m.id = p.matter_id
        WHERE p.id = candidate_plan_decision.plan_id
          AND m.workspace_id = NULLIF(current_setting('app.current_workspace_id', true), '')::uuid
    ));

CREATE POLICY plan_item_source_by_matter ON core.candidate_plan_item_source
    USING (EXISTS (
        SELECT 1
        FROM core.candidate_plan_item i
        JOIN core.candidate_plan p ON p.id = i.plan_id
        JOIN core.matter m ON m.id = p.matter_id
        WHERE i.id = candidate_plan_item_source.plan_item_id
          AND m.workspace_id = NULLIF(current_setting('app.current_workspace_id', true), '')::uuid
    ))
    WITH CHECK (EXISTS (
        SELECT 1
        FROM core.candidate_plan_item i
        JOIN core.candidate_plan p ON p.id = i.plan_id
        JOIN core.matter m ON m.id = p.matter_id
        WHERE i.id = candidate_plan_item_source.plan_item_id
          AND m.workspace_id = NULLIF(current_setting('app.current_workspace_id', true), '')::uuid
    ));