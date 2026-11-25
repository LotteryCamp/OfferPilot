-- 0007_rls.sql
-- OfferPilot · 工作区行级隔离
--
-- 来源：说明书 §8.2。策略以会话变量 app.current_workspace_id 为条件；
-- 变量未设置时 current_setting(..., true) 返回 NULL，策略不匹配任何行（默认拒绝）。
--
-- requirement 按事项归属启用工作区隔离；公开原文仍通过 source/snapshot 共享。
-- 应用角色共享连接，RLS 是纵深防御；认证层签发工作区标识并在服务端校验。共享应用角色
-- 仍可设置会话变量，不能独立承担多租户隔离。
-- 不对表执行 FORCE ROW LEVEL SECURITY：迁移与后台任务用所有者/超级用户执行，
-- 应用必须使用独立的非所有者角色（见 db/dev/roles.sql）。

ALTER TABLE core.matter ENABLE ROW LEVEL SECURITY;
ALTER TABLE core.requirement ENABLE ROW LEVEL SECURITY;
ALTER TABLE core.candidate_plan ENABLE ROW LEVEL SECURITY;
ALTER TABLE core.candidate_plan_item ENABLE ROW LEVEL SECURITY;
ALTER TABLE core.task ENABLE ROW LEVEL SECURITY;

CREATE POLICY matter_owner ON core.matter
    USING (workspace_id = NULLIF(current_setting('app.current_workspace_id', true), '')::uuid)
    WITH CHECK (workspace_id = NULLIF(current_setting('app.current_workspace_id', true), '')::uuid);

CREATE POLICY requirement_by_matter ON core.requirement
    USING (EXISTS (
        SELECT 1 FROM core.matter m
        WHERE m.id = requirement.matter_id
          AND m.workspace_id = NULLIF(current_setting('app.current_workspace_id', true), '')::uuid
    ))
    WITH CHECK (EXISTS (
        SELECT 1 FROM core.matter m
        WHERE m.id = requirement.matter_id
          AND m.workspace_id = NULLIF(current_setting('app.current_workspace_id', true), '')::uuid
    ));

CREATE POLICY plan_by_matter ON core.candidate_plan
    USING (EXISTS (
        SELECT 1 FROM core.matter m
        WHERE m.id = candidate_plan.matter_id
          AND m.workspace_id = NULLIF(current_setting('app.current_workspace_id', true), '')::uuid
    ))
    WITH CHECK (EXISTS (
        SELECT 1 FROM core.matter m
        WHERE m.id = candidate_plan.matter_id
          AND m.workspace_id = NULLIF(current_setting('app.current_workspace_id', true), '')::uuid
    ));

CREATE POLICY plan_item_by_plan ON core.candidate_plan_item
    USING (EXISTS (
        SELECT 1
        FROM core.candidate_plan p
        JOIN core.matter m ON m.id = p.matter_id
        WHERE p.id = candidate_plan_item.plan_id
          AND m.workspace_id = NULLIF(current_setting('app.current_workspace_id', true), '')::uuid
    ))
    WITH CHECK (EXISTS (
        SELECT 1
        FROM core.candidate_plan p
        JOIN core.matter m ON m.id = p.matter_id
        WHERE p.id = candidate_plan_item.plan_id
          AND m.workspace_id = NULLIF(current_setting('app.current_workspace_id', true), '')::uuid
    ));

CREATE POLICY task_by_matter ON core.task
    USING (EXISTS (
        SELECT 1 FROM core.matter m
        WHERE m.id = task.matter_id
          AND m.workspace_id = NULLIF(current_setting('app.current_workspace_id', true), '')::uuid
    ))
    WITH CHECK (EXISTS (
        SELECT 1 FROM core.matter m
        WHERE m.id = task.matter_id
          AND m.workspace_id = NULLIF(current_setting('app.current_workspace_id', true), '')::uuid
    ));