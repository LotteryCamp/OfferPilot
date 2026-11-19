-- seed/0001_reference.sql
-- Alpha 参考数据：事项类型。可重复执行。
-- 来源：说明书 §10.2（内置 pre_recommend 与 competition）。

INSERT INTO core.matter_type (type_code, name, built_in, enabled)
VALUES
    ('pre_recommend', '推免', true, true),
    ('competition', '竞赛', true, true)
ON CONFLICT (type_code) DO UPDATE
    SET name = EXCLUDED.name,
        built_in = true;

INSERT INTO core.template_version (
    id, type_code, version_no, stage_defs, requirement_skeleton, material_types,
    status, published_at
)
VALUES
    (
        '10000000-0000-7000-8000-000000000001',
        'pre_recommend', 'TP-pre-01', '[]', '[]', '[]', 'published', now()
    ),
    (
        '10000000-0000-7000-8000-000000000002',
        'competition', 'TP-comp-01', '[]', '[]', '[]', 'published', now()
    )
ON CONFLICT (id) DO NOTHING;