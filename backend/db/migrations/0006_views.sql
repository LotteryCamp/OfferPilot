-- 0006_views.sql
-- OfferPilot Alpha · 查询视图
--
-- 全部使用 security_invoker = true，确保视图不会绕过基表的行级安全策略。

CREATE VIEW core.v_matter_overview
WITH (security_invoker = true) AS
SELECT
    m.id,
    m.workspace_id,
    m.type_code,
    mt.name AS type_name,
    m.goal,
    m.status,
    m.scope_year,
    m.scope_attrs,
    m.archived_at,
    m.created_at,
    m.updated_at,
    COALESCE(t.task_total, 0) AS task_total,
    COALESCE(t.task_done, 0) AS task_done,
    COALESCE(t.task_total, 0) - COALESCE(t.task_done, 0) AS task_open,
    lp.id AS latest_plan_id,
    lp.status AS latest_plan_status,
    lp.version_no AS latest_plan_version
FROM core.matter m
JOIN core.matter_type mt ON mt.type_code = m.type_code
LEFT JOIN LATERAL (
    SELECT
        count(*)::integer AS task_total,
        count(*) FILTER (WHERE status = 'done')::integer AS task_done
    FROM core.task
    WHERE matter_id = m.id
) t ON true
LEFT JOIN LATERAL (
    SELECT id, status, version_no
    FROM core.candidate_plan
    WHERE matter_id = m.id
    ORDER BY version_no DESC
    LIMIT 1
) lp ON true;

COMMENT ON VIEW core.v_matter_overview IS '事项列表：类型、任务完成数、最新候选计划';

CREATE VIEW core.v_plan_detail
WITH (security_invoker = true) AS
SELECT
    p.id,
    p.matter_id,
    p.version_no,
    p.status,
    p.basis_version,
    p.generated_at,
    p.confirmed_at,
    p.expired_at,
    p.confirmed_by,
    p.op_id,
    count(i.id)::integer AS item_count,
    count(i.requirement_id)::integer AS requirement_linked_count,
    (
        SELECT count(*)::integer
        FROM core.candidate_plan_item_source s
        JOIN core.candidate_plan_item si ON si.id = s.plan_item_id
        WHERE si.plan_id = p.id
    ) AS source_count
FROM core.candidate_plan p
LEFT JOIN core.candidate_plan_item i ON i.plan_id = p.id
GROUP BY p.id;

COMMENT ON VIEW core.v_plan_detail IS '候选计划详情：条目数、要求回溯数、来源定位数';

CREATE VIEW core.v_task_list
WITH (security_invoker = true) AS
SELECT
    t.id,
    t.matter_id,
    m.goal AS matter_goal,
    m.type_code,
    t.plan_id,
    t.plan_item_id,
    p.status AS plan_status,
    t.executor_id,
    t.title,
    t.due_at,
    t.official_deadline_date,
    t.official_deadline_at,
    t.suggested_date,
    t.status,
    t.completion_evidence,
    t.depends_on,
    t.created_at,
    t.updated_at
FROM core.task t
JOIN core.matter m ON m.id = t.matter_id
LEFT JOIN core.candidate_plan p ON p.id = t.plan_id;

COMMENT ON VIEW core.v_task_list IS '任务列表：带事项上下文、期限精度与来源计划状态';