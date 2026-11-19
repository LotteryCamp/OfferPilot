-- 0001_schemas_enums.sql
-- OfferPilot Alpha · 模式与枚举
--
-- 来源：《OfferPilot 数据库设计说明书 v2.0》§2.5、§5.1.2。
-- Alpha 只创建本阶段实际使用的 8 个枚举；其余枚举随对应模块迁移增量添加。
-- 枚举统一建在 core 模式，避免业务类型散落在 public。

CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS ops;

COMMENT ON SCHEMA core IS 'OfferPilot 业务主数据：用户、工作区、事项、要求、计划、任务';
COMMENT ON SCHEMA ops IS 'OfferPilot 运行数据：来源、快照、证据、迁移记录';

CREATE TYPE core.account_status AS ENUM ('pending', 'active', 'disabled');
CREATE TYPE core.matter_status AS ENUM ('draft', 'active', 'paused', 'archived', 'cancelled');
CREATE TYPE core.obligation_nature AS ENUM ('required', 'advised', 'optional', 'to_verify');
CREATE TYPE core.extract_status AS ENUM ('extracted', 'checked', 'to_review', 'rejected');
CREATE TYPE core.plan_status AS ENUM ('draft', 'pending', 'confirmed', 'rejected', 'expired');
CREATE TYPE core.task_status AS ENUM (
    'pending', 'ready', 'in_progress', 'blocked', 'done', 'cancelled'
);
CREATE TYPE ops.source_status AS ENUM ('active', 'withdrawn', 'invalid');
CREATE TYPE ops.check_result AS ENUM ('pending', 'passed', 'failed', 'conflict');