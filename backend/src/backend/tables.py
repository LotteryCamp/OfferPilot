"""SQLAlchemy table definitions for the Alpha schema.

The physical schema is owned by the database migration work. These definitions
mirror the columns the business API reads and writes.
"""

from __future__ import annotations

from sqlalchemy import (
    CHAR,
    Boolean,
    Column,
    Date,
    DateTime,
    Integer,
    MetaData,
    Numeric,
    SmallInteger,
    String,
    Table,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY, ENUM, JSONB, UUID

metadata = MetaData()

UUID_TYPE = UUID(as_uuid=True)
TIMESTAMPTZ = DateTime(timezone=True)

account_status = ENUM(
    "pending",
    "active",
    "disabled",
    name="account_status",
    schema="core",
    create_type=False,
)
matter_status = ENUM(
    "draft",
    "active",
    "paused",
    "archived",
    "cancelled",
    name="matter_status",
    schema="core",
    create_type=False,
)
obligation_nature = ENUM(
    "required",
    "advised",
    "optional",
    "to_verify",
    name="obligation_nature",
    schema="core",
    create_type=False,
)
extract_status = ENUM(
    "extracted",
    "checked",
    "to_review",
    "rejected",
    name="extract_status",
    schema="core",
    create_type=False,
)
plan_status = ENUM(
    "draft",
    "pending",
    "confirmed",
    "rejected",
    "expired",
    name="plan_status",
    schema="core",
    create_type=False,
)
task_status = ENUM(
    "pending",
    "ready",
    "in_progress",
    "blocked",
    "done",
    "cancelled",
    name="task_status",
    schema="core",
    create_type=False,
)
source_status = ENUM(
    "active",
    "withdrawn",
    "invalid",
    name="source_status",
    schema="ops",
    create_type=False,
)
check_result = ENUM(
    "pending",
    "passed",
    "failed",
    "conflict",
    name="check_result",
    schema="ops",
    create_type=False,
)

app_user = Table(
    "app_user",
    metadata,
    Column("id", UUID_TYPE, primary_key=True),
    Column("email", String(160), nullable=False),
    Column("display_name", String(60), nullable=False),
    Column("password_hash", String(255), nullable=False),
    Column("account_type", String(16), nullable=False),
    Column("status", account_status, nullable=False),
    Column("created_at", TIMESTAMPTZ, nullable=False),
    Column("updated_at", TIMESTAMPTZ, nullable=False),
    Column("deleted_at", TIMESTAMPTZ),
    schema="core",
)

workspace = Table(
    "workspace",
    metadata,
    Column("id", UUID_TYPE, primary_key=True),
    Column("owner_id", UUID_TYPE, nullable=False),
    Column("created_at", TIMESTAMPTZ, nullable=False),
    Column("updated_at", TIMESTAMPTZ, nullable=False),
    schema="core",
)

matter_type = Table(
    "matter_type",
    metadata,
    Column("id", UUID_TYPE, primary_key=True),
    Column("type_code", String(32), nullable=False),
    Column("name", String(60), nullable=False),
    Column("built_in", Boolean, nullable=False),
    Column("enabled", Boolean, nullable=False),
    Column("created_at", TIMESTAMPTZ, nullable=False),
    schema="core",
)

template_version = Table(
    "template_version",
    metadata,
    Column("id", UUID_TYPE, primary_key=True),
    Column("type_code", String(32), nullable=False),
    Column("version_no", String(32), nullable=False),
    Column("stage_defs", JSONB, nullable=False),
    Column("requirement_skeleton", JSONB, nullable=False),
    Column("material_types", JSONB, nullable=False),
    Column("status", String(16), nullable=False),
    Column("published_at", TIMESTAMPTZ),
    Column("created_at", TIMESTAMPTZ, nullable=False),
    schema="core",
)

matter = Table(
    "matter",
    metadata,
    Column("id", UUID_TYPE, primary_key=True),
    Column("workspace_id", UUID_TYPE, nullable=False),
    Column("type_code", String(32), nullable=False),
    Column("template_version_id", UUID_TYPE, nullable=False),
    Column("goal", String(200), nullable=False),
    Column("status", matter_status, nullable=False),
    Column("scope_year", SmallInteger),
    Column("scope_attrs", JSONB),
    Column("parent_matter_id", UUID_TYPE),
    Column("archived_at", TIMESTAMPTZ),
    Column("submitted_version_ids", ARRAY(UUID_TYPE)),
    Column("archive_result", String(200)),
    Column("retrospective", Text),
    Column("created_at", TIMESTAMPTZ, nullable=False),
    Column("updated_at", TIMESTAMPTZ, nullable=False),
    schema="core",
)

source = Table(
    "source",
    metadata,
    Column("id", UUID_TYPE, primary_key=True),
    Column("publisher", String(160), nullable=False),
    Column("url", String(500), nullable=False),
    Column("matter_type_id", UUID_TYPE),
    Column("scope", String(200)),
    Column("scope_year", SmallInteger),
    Column("valid_from", Date),
    Column("valid_to", Date),
    Column("status", source_status, nullable=False),
    Column("auto_check_status", check_result, nullable=False),
    Column("roi_status", String(16), nullable=False),
    Column("last_fetched_at", TIMESTAMPTZ),
    Column("created_at", TIMESTAMPTZ, nullable=False),
    schema="ops",
)

snapshot = Table(
    "snapshot",
    metadata,
    Column("id", UUID_TYPE, primary_key=True),
    Column("source_id", UUID_TYPE, nullable=False),
    Column("version_no", Integer, nullable=False),
    Column("object_key", String(512), nullable=False),
    Column("content_hash", CHAR(64), nullable=False),
    Column("html_version", String(32)),
    Column("text_version", String(32)),
    Column("extraction", JSONB),
    Column("fetched_at", TIMESTAMPTZ, nullable=False),
    Column("is_current", Boolean, nullable=False),
    schema="ops",
)

requirement = Table(
    "requirement",
    metadata,
    Column("id", UUID_TYPE, primary_key=True),
    Column("matter_id", UUID_TYPE, nullable=False),
    Column("snapshot_id", UUID_TYPE, nullable=False),
    Column("field_key", String(64), nullable=False),
    Column("label", String(120), nullable=False),
    Column("obligation_nature", obligation_nature, nullable=False),
    Column("extract_status", extract_status, nullable=False),
    Column("scope", String(200)),
    Column("value_text", Text),
    Column("value_type", String(16), nullable=False),
    Column("confidence", Numeric(4, 3)),
    Column("checked_at", TIMESTAMPTZ),
    Column("created_at", TIMESTAMPTZ, nullable=False),
    Column("updated_at", TIMESTAMPTZ, nullable=False),
    schema="core",
)

requirement_self_check = Table(
    "requirement_self_check",
    metadata,
    Column("requirement_id", UUID_TYPE, primary_key=True),
    Column("conclusion", String(24), nullable=False),
    Column("reason", Text, nullable=False),
    Column("missing_fields", ARRAY(Text), nullable=False),
    Column("computed_deadline_at", TIMESTAMPTZ),
    Column("gaps", JSONB, nullable=False),
    Column("evaluated_at", TIMESTAMPTZ, nullable=False),
    schema="core",
)

matter_source = Table(
    "matter_source",
    metadata,
    Column("matter_id", UUID_TYPE, primary_key=True),
    Column("snapshot_id", UUID_TYPE, primary_key=True),
    Column("linked_at", TIMESTAMPTZ, nullable=False),
    schema="core",
)

agent_run = Table(
    "agent_run",
    metadata,
    Column("run_id", String(64), primary_key=True),
    Column("matter_id", UUID_TYPE, nullable=False),
    Column("user_id", UUID_TYPE, nullable=False),
    Column("status", String(24), nullable=False),
    Column("operation_id", String(200)),
    Column("checkpoint", JSONB(none_as_null=True)),
    Column("created_at", TIMESTAMPTZ, nullable=False),
    Column("updated_at", TIMESTAMPTZ, nullable=False),
    schema="core",
)

evidence = Table(
    "evidence",
    metadata,
    Column("id", UUID_TYPE, primary_key=True),
    Column("source_id", UUID_TYPE, nullable=False),
    Column("snapshot_id", UUID_TYPE, nullable=False),
    Column("target_type", String(24), nullable=False),
    Column("target_id", UUID_TYPE, nullable=False),
    Column("locator_kind", String(16), nullable=False),
    Column("locator", String(300), nullable=False),
    Column("quote", Text),
    Column("quote_hash", CHAR(64)),
    Column("fetched_at", TIMESTAMPTZ, nullable=False),
    schema="ops",
)

candidate_plan = Table(
    "candidate_plan",
    metadata,
    Column("id", UUID_TYPE, primary_key=True),
    Column("matter_id", UUID_TYPE, nullable=False),
    Column("version_no", Integer, nullable=False),
    Column("status", plan_status, nullable=False),
    Column("basis_version", CHAR(64), nullable=False),
    Column("basis_input", JSONB, nullable=False),
    Column("generated_at", TIMESTAMPTZ, nullable=False),
    Column("confirmed_at", TIMESTAMPTZ),
    Column("expired_at", TIMESTAMPTZ),
    Column("confirmed_by", UUID_TYPE),
    Column("op_id", UUID_TYPE),
    schema="core",
)

candidate_plan_item = Table(
    "candidate_plan_item",
    metadata,
    Column("id", UUID_TYPE, primary_key=True),
    Column("plan_id", UUID_TYPE, nullable=False),
    Column("seq", SmallInteger, nullable=False),
    Column("title", String(160), nullable=False),
    Column("detail", Text),
    Column("obligation_nature", obligation_nature, nullable=False),
    Column("official_deadline_date", Date),
    Column("official_deadline_at", TIMESTAMPTZ),
    Column("suggested_date", Date),
    Column("depends_on_item_ids", ARRAY(UUID_TYPE), nullable=False),
    Column("evidence_required", Boolean, nullable=False),
    Column("requirement_id", UUID_TYPE),
    Column("created_at", TIMESTAMPTZ, nullable=False),
    schema="core",
)

candidate_plan_item_source = Table(
    "candidate_plan_item_source",
    metadata,
    Column("id", UUID_TYPE, primary_key=True),
    Column("plan_item_id", UUID_TYPE, nullable=False),
    Column("source_id", UUID_TYPE, nullable=False),
    Column("snapshot_id", UUID_TYPE, nullable=False),
    Column("locator_kind", String(16), nullable=False),
    Column("locator", String(300), nullable=False),
    Column("quote", Text),
    schema="core",
)

candidate_plan_decision = Table(
    "candidate_plan_decision",
    metadata,
    Column("id", UUID_TYPE, primary_key=True),
    Column("plan_id", UUID_TYPE, nullable=False),
    Column("decision", String(16), nullable=False),
    Column("decided_by", UUID_TYPE, nullable=False),
    Column("decided_at", TIMESTAMPTZ, nullable=False),
    Column("operation_id", UUID_TYPE, nullable=False),
    schema="core",
)

task = Table(
    "task",
    metadata,
    Column("id", UUID_TYPE, primary_key=True),
    Column("matter_id", UUID_TYPE, nullable=False),
    Column("plan_id", UUID_TYPE),
    Column("plan_item_id", UUID_TYPE),
    Column("executor_id", UUID_TYPE, nullable=False),
    Column("title", String(160), nullable=False),
    Column("due_at", TIMESTAMPTZ),
    Column("official_deadline_date", Date),
    Column("official_deadline_at", TIMESTAMPTZ),
    Column("suggested_date", Date),
    Column("status", task_status, nullable=False),
    Column("completion_evidence", Text),
    Column("depends_on", ARRAY(UUID_TYPE)),
    Column("created_at", TIMESTAMPTZ, nullable=False),
    Column("updated_at", TIMESTAMPTZ, nullable=False),
    schema="core",
)

v_matter_overview = Table(
    "v_matter_overview",
    metadata,
    Column("id", UUID_TYPE),
    Column("workspace_id", UUID_TYPE),
    Column("type_code", String(32)),
    Column("type_name", String(60)),
    Column("goal", String(200)),
    Column("status", matter_status),
    Column("scope_year", SmallInteger),
    Column("scope_attrs", JSONB),
    Column("archived_at", TIMESTAMPTZ),
    Column("created_at", TIMESTAMPTZ),
    Column("updated_at", TIMESTAMPTZ),
    Column("task_total", Integer),
    Column("task_done", Integer),
    Column("task_open", Integer),
    Column("latest_plan_id", UUID_TYPE),
    Column("latest_plan_status", plan_status),
    Column("latest_plan_version", Integer),
    schema="core",
)

v_plan_detail = Table(
    "v_plan_detail",
    metadata,
    Column("id", UUID_TYPE),
    Column("matter_id", UUID_TYPE),
    Column("version_no", Integer),
    Column("status", plan_status),
    Column("basis_version", CHAR(64)),
    Column("generated_at", TIMESTAMPTZ),
    Column("confirmed_at", TIMESTAMPTZ),
    Column("expired_at", TIMESTAMPTZ),
    Column("confirmed_by", UUID_TYPE),
    Column("op_id", UUID_TYPE),
    Column("item_count", Integer),
    Column("requirement_linked_count", Integer),
    Column("source_count", Integer),
    schema="core",
)
