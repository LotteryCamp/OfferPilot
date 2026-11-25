-- 0018_profile_editing.sql
-- OfferPilot · 用户自助编辑账户资料
--
-- 应用角色获得更新显示名称与邮箱的列权限；邮箱唯一性由唯一约束保证。

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'offerpilot_app') THEN
        GRANT UPDATE (display_name, email) ON core.app_user TO offerpilot_app;
    END IF;
END $$;
