-- seed/demo.sql
-- Alpha 演示数据（仅用于本地演示/联调，不得用于生产）。可重复执行。
-- 全部为虚构事实与示例链接，符合说明书 §10.2 的 AC19 要求。
--
-- 固定 UUID 便于前端联调；每段都带 ON CONFLICT DO NOTHING，重复执行不新增行。

INSERT INTO core.app_user (id, email, display_name, password_hash, account_type, status)
VALUES (
    '00000000-0000-7000-8000-000000000001',
    'demo@offerpilot.local',
    '演示用户',
    '!alpha-demo-no-login',
    'applicant',
    'active'
)
ON CONFLICT (id) DO NOTHING;

INSERT INTO core.workspace (id, owner_id)
VALUES (
    '00000000-0000-7000-8000-000000000002',
    '00000000-0000-7000-8000-000000000001'
)
ON CONFLICT (id) DO NOTHING;

INSERT INTO core.matter (
    id, workspace_id, type_code, template_version_id, goal, status, scope_year, scope_attrs
)
VALUES (
    '00000000-0000-7000-8000-000000000003',
    '00000000-0000-7000-8000-000000000002',
    'pre_recommend',
    '10000000-0000-7000-8000-000000000001',
    '申请 2027 年示例大学计算机学院推免',
    'active',
    2027,
    '{"school": "示例大学", "college": "计算机学院", "program": "计算机科学与技术", "degree": "academic"}'::jsonb
)
ON CONFLICT (id) DO NOTHING;

INSERT INTO ops.source (
    id, publisher, url, matter_type_id, scope, scope_year,
    status, auto_check_status, roi_status, last_fetched_at
)
SELECT
    '00000000-0000-7000-8000-000000000004',
    '示例大学研究生院',
    'https://example.edu.cn/graduate/2027-recommend',
    mt.id,
    '示例大学计算机学院 2027 年推免',
    2027,
    'active',
    'passed',
    'original',
    '2026-11-18T02:00:00Z'
FROM core.matter_type mt
WHERE mt.type_code = 'pre_recommend'
ON CONFLICT (id) DO NOTHING;

INSERT INTO ops.snapshot (
    id, source_id, version_no, object_key, content_hash, html_version, text_version,
    extraction, fetched_at, is_current
)
VALUES (
    '00000000-0000-7000-8000-000000000005',
    '00000000-0000-7000-8000-000000000004',
    1,
    'inline:demo',
    '9f2c1f6b8a4d3e5c7a1b2c3d4e5f60718293a4b5c6d7e8f90123456789abcdef',
    'reader-0.1',
    'textnorm-0.1',
    '{"text": "示例大学 2027 年推免申请要求：学业成绩排名前 30%，需提交成绩单与导师同意证明。"}'::jsonb,
    '2026-11-18T02:00:00Z',
    true
)
ON CONFLICT (id) DO NOTHING;

INSERT INTO core.requirement (
    id, matter_id, snapshot_id, field_key, label, obligation_nature,
    extract_status, scope, value_text, value_type, confidence, checked_at
)
VALUES (
    '00000000-0000-7000-8000-000000000006',
    '00000000-0000-7000-8000-000000000003',
    '00000000-0000-7000-8000-000000000005',
    'gpa.rank',
    '学业成绩排名要求',
    'required',
    'checked',
    '示例大学计算机学院 2027 年推免',
    '学业成绩排名前 30%',
    'text',
    0.860,
    '2026-11-18T02:05:00Z'
)
ON CONFLICT (id) DO NOTHING;

INSERT INTO ops.evidence (
    id, source_id, snapshot_id, target_type, target_id,
    locator_kind, locator, quote, fetched_at
)
VALUES (
    '00000000-0000-7000-8000-000000000007',
    '00000000-0000-7000-8000-000000000004',
    '00000000-0000-7000-8000-000000000005',
    'requirement',
    '00000000-0000-7000-8000-000000000006',
    'section',
    '第 2 节 第 3 段',
    '学业成绩排名前 30%',
    '2026-11-18T02:00:00Z'
)
ON CONFLICT (id) DO NOTHING;

INSERT INTO core.candidate_plan (
    id, matter_id, version_no, status, basis_version, basis_input, generated_at
)
VALUES (
    '00000000-0000-7000-8000-000000000008',
    '00000000-0000-7000-8000-000000000003',
    1,
    'draft',
    repeat('a', 64),
    '{"matter_id": "00000000-0000-7000-8000-000000000003", "requirement_ids": ["00000000-0000-7000-8000-000000000006"], "rule_pack_version": "RP-2026-01", "template_version_id": null}'::jsonb,
    '2026-11-18T02:10:00Z'
)
ON CONFLICT (id) DO NOTHING;

INSERT INTO core.candidate_plan_item (
    id, plan_id, seq, title, detail, obligation_nature,
    suggested_date, evidence_required, requirement_id
)
VALUES
    (
        '00000000-0000-7000-8000-000000000009',
        '00000000-0000-7000-8000-000000000008',
        1,
        '准备并核对成绩单',
        '确认排名证明与教务盖章版本',
        'required',
        '2026-11-20',
        true,
        '00000000-0000-7000-8000-000000000006'
    ),
    (
        '00000000-0000-7000-8000-000000000010',
        '00000000-0000-7000-8000-000000000008',
        2,
        '联系意向导师并确认同意证明',
        '先发邮件确认，再按学院模板准备证明',
        'to_verify',
        '2026-11-22',
        true,
        NULL
    )
ON CONFLICT (id) DO NOTHING;

INSERT INTO core.candidate_plan_item_source (
    id, plan_item_id, source_id, snapshot_id, locator_kind, locator, quote
)
VALUES (
    '00000000-0000-7000-8000-000000000011',
    '00000000-0000-7000-8000-000000000009',
    '00000000-0000-7000-8000-000000000004',
    '00000000-0000-7000-8000-000000000005',
    'section',
    '第 2 节 第 3 段',
    '学业成绩排名前 30%'
)
ON CONFLICT (id) DO NOTHING;

UPDATE core.candidate_plan
   SET status = 'pending'
 WHERE id = '00000000-0000-7000-8000-000000000008'
   AND status = 'draft';