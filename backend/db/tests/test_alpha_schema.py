"""OfferPilot Alpha schema 集成测试。

前置：一个可连接的 PostgreSQL 16 实例，以及有建库权限的账号。
默认管理连接串为 ``postgresql://postgres@127.0.0.1:5432/postgres``，
可用环境变量 ``PGTEST_ADMIN_DSN`` 覆盖。

运行::

    cd backend
    uv sync
    uv run python db/tests/test_alpha_schema.py -v

测试使用 ``offerpilot_schema_test`` 数据库，并在每次运行时重建 ``core``/``ops`` 模式。
"""

from __future__ import annotations

import os
import subprocess
import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, LiteralString
from uuid import UUID

import psycopg
from psycopg import errors, sql

DB_DIR = Path(__file__).resolve().parents[1]
MIGRATE = DB_DIR / "migrate.py"
ADMIN_DSN = os.environ.get(
    "PGTEST_ADMIN_DSN", "postgresql://postgres@127.0.0.1:5432/postgres"
)
TEST_DB = "offerpilot_alpha_test"
TEST_ROLE = "offerpilot_schema_test_app"

USER_A = UUID("11111111-1111-7111-8111-111111111111")
WS_A = UUID("11111111-1111-7111-8111-111111111112")
MATTER_A = UUID("11111111-1111-7111-8111-111111111113")
USER_B = UUID("22222222-2222-7222-8222-222222222221")
WS_B = UUID("22222222-2222-7222-8222-222222222222")
MATTER_B = UUID("22222222-2222-7222-8222-222222222223")

SOURCE_ID = UUID("33333333-3333-7333-8333-333333333331")
SNAPSHOT_ID = UUID("33333333-3333-7333-8333-333333333332")
REQ_ID = UUID("33333333-3333-7333-8333-333333333333")
EVIDENCE_ID = UUID("33333333-3333-7333-8333-333333333334")
PLAN_ID = UUID("44444444-4444-7444-8444-444444444441")
TEMPLATE_PRE = UUID("10000000-0000-7000-8000-000000000001")
ITEM_1 = UUID("44444444-4444-7444-8444-444444444442")
ITEM_2 = UUID("44444444-4444-7444-8444-444444444443")
FIXED_FETCHED = datetime(2026, 11, 18, 2, 0, tzinfo=UTC)
HASH = "a" * 64
HASH_2 = "b" * 64


def test_dsn() -> str:
    parts = ADMIN_DSN.rsplit("/", 1)
    return parts[0] + "/" + TEST_DB


def fetch_scalar(
    conn: psycopg.Connection,
    query: LiteralString | sql.SQL | sql.Composed,
    params: tuple[object, ...] | None = None,
) -> Any:
    row = conn.execute(query, params).fetchone()
    assert row is not None
    return row[0]


class AlphaSchemaTest(unittest.TestCase):
    conn: psycopg.Connection

    @classmethod
    def setUpClass(cls) -> None:
        admin = psycopg.connect(ADMIN_DSN, autocommit=True)
        exists = admin.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (TEST_DB,)
        ).fetchone()
        if not exists:
            admin.execute(f'CREATE DATABASE "{TEST_DB}"')
        admin.execute(
            f"""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{TEST_ROLE}') THEN
                    CREATE ROLE {TEST_ROLE} NOLOGIN;
                END IF;
            END $$;
            """
        )
        admin.close()

        # 用 drop schema 代替 drop database：既能在每次运行时得到干净结构，
        # 也避免 Windows 上 DROP DATABASE 的 checkpoint 信号被沙箱拒绝。
        reset = psycopg.connect(test_dsn(), autocommit=True)
        reset.execute("DROP SCHEMA IF EXISTS core CASCADE")
        reset.execute("DROP SCHEMA IF EXISTS ops CASCADE")
        reset.close()

        subprocess.run(
            [sys.executable, str(MIGRATE), "--dsn", test_dsn(), "migrate"],
            check=True,
        )
        subprocess.run(
            [sys.executable, str(MIGRATE), "--dsn", test_dsn(), "seed"],
            check=True,
        )

        grant = psycopg.connect(test_dsn(), autocommit=True)
        grant.execute(f"GRANT USAGE ON SCHEMA core, ops TO {TEST_ROLE}")
        grant.execute(
            "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA core, ops"
            f" TO {TEST_ROLE}"
        )
        grant.close()

        cls.conn = psycopg.connect(test_dsn(), autocommit=False)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.conn.close()
        # Windows 沙箱下 DROP DATABASE 的 checkpoint 可能被拒绝；保留测试库，
        # 下次运行复用并由 setUp 清空数据。需要彻底清理时手工执行：
        #   DROP DATABASE offerpilot_schema_test WITH (FORCE);
        print(f"\n测试库保留：{TEST_DB}（如需清理请手工 DROP DATABASE）")

    def setUp(self) -> None:
        self.conn.rollback()
        self.conn.execute("RESET ROLE")
        self.conn.execute("RESET app.current_workspace_id")
        self.conn.execute(
            """
            TRUNCATE core.agent_run, core.matter_source, core.task,
                     core.candidate_plan_item, core.candidate_plan,
                     core.requirement, core.matter, core.workspace, core.app_user,
                     ops.evidence, ops.snapshot, ops.source
            CASCADE
            """
        )
        self.conn.commit()

    # ---------- helpers ----------

    def make_identity(self, user: UUID, ws: UUID, matter: UUID, goal: str) -> None:
        self.conn.execute(
            "INSERT INTO core.app_user (id, email, display_name, password_hash, status)"
            " VALUES (%s, %s, %s, 'x', 'active')",
            (user, f"{user}@example.test", f"user-{str(user)[:4]}"),
        )
        self.conn.execute(
            "INSERT INTO core.workspace (id, owner_id) VALUES (%s, %s)", (ws, user)
        )
        self.conn.execute(
            "INSERT INTO core.matter"
            " (id, workspace_id, type_code, template_version_id, goal, status, scope_year, scope_attrs)"
            " VALUES (%s, %s, 'pre_recommend', %s, %s, 'active', 2027, %s)",
            (
                matter,
                ws,
                TEMPLATE_PRE,
                goal,
                '{"school": "示例大学", "program": "计算机"}',
            ),
        )

    def make_source_chain(self) -> None:
        self.conn.execute(
            "INSERT INTO ops.source (id, publisher, url, matter_type_id, scope_year,"
            " status, auto_check_status, roi_status)"
            " SELECT %s, '示例大学研究生院', 'https://example.test/notice', id, 2027,"
            " 'active', 'passed', 'original' FROM core.matter_type WHERE type_code='pre_recommend'",
            (SOURCE_ID,),
        )
        self.conn.execute(
            "INSERT INTO ops.snapshot (id, source_id, version_no, object_key, content_hash,"
            " extraction, fetched_at, is_current)"
            " VALUES (%s, %s, 1, 'inline:test', %s, %s, %s, true)",
            (SNAPSHOT_ID, SOURCE_ID, HASH, '{"text": "排名前 30%%"}', FIXED_FETCHED),
        )
        self.conn.execute(
            "INSERT INTO core.requirement (id, matter_id, snapshot_id, field_key, label,"
            " obligation_nature, extract_status, value_text, value_type, confidence, checked_at)"
            " VALUES (%s, %s, %s, 'gpa.rank', '成绩排名', 'required', 'checked',"
            " '前 30%%', 'text', 0.9, %s)",
            (REQ_ID, MATTER_A, SNAPSHOT_ID, FIXED_FETCHED),
        )
        self.conn.execute(
            "INSERT INTO ops.evidence (id, source_id, snapshot_id, target_type, target_id,"
            " locator_kind, locator, quote, fetched_at)"
            " VALUES (%s, %s, %s, 'requirement', %s, 'section', '第 2 节', '前 30%%', %s)",
            (EVIDENCE_ID, SOURCE_ID, SNAPSHOT_ID, REQ_ID, FIXED_FETCHED),
        )

    def make_plan(self, plan_id: UUID = PLAN_ID, version_no: int = 1) -> None:
        self.conn.execute(
            "INSERT INTO core.candidate_plan"
            " (id, matter_id, version_no, status, basis_version, basis_input)"
            " VALUES (%s, %s, %s, 'draft', repeat('a', 64), %s)",
            (plan_id, MATTER_A, version_no, f'{{"matter_id": "{MATTER_A}"}}'),
        )
        self.conn.execute(
            "INSERT INTO core.candidate_plan_item"
            " (id, plan_id, seq, title, obligation_nature, suggested_date,"
            "  evidence_required, requirement_id)"
            " VALUES (%s, %s, 1, '准备成绩单', 'required', '2026-11-20', true, %s),"
            "        (%s, %s, 2, '联系导师', 'to_verify', NULL, false, NULL)",
            (ITEM_1, plan_id, REQ_ID, ITEM_2, plan_id),
        )
        self.conn.execute(
            "INSERT INTO core.candidate_plan_item_source"
            " (id, plan_item_id, source_id, snapshot_id, locator_kind, locator, quote)"
            " VALUES (%s, %s, %s, %s, 'section', '第 2 节', '前 30%%')",
            (
                UUID("33333333-3333-7333-8333-333333333336"),
                ITEM_1,
                SOURCE_ID,
                SNAPSHOT_ID,
            ),
        )
        self.conn.execute(
            "UPDATE core.candidate_plan SET status = 'pending' WHERE id = %s",
            (plan_id,),
        )

    def reject_plan(self, plan_id: UUID, operation_id: UUID) -> None:
        with self.conn.transaction():
            self.conn.execute(
                "UPDATE core.candidate_plan SET status = 'rejected' WHERE id = %s"
                " AND status = 'pending'",
                (plan_id,),
            )
            self.conn.execute(
                "INSERT INTO core.candidate_plan_decision"
                " (plan_id, decision, decided_by, operation_id)"
                " VALUES (%s, 'rejected', %s, %s)",
                (plan_id, USER_A, operation_id),
            )
        self.conn.commit()

    def confirm_plan(self, plan_id: UUID, op_id: UUID) -> str:
        existing = self.conn.execute(
            "SELECT id FROM core.candidate_plan WHERE op_id = %s", (op_id,)
        ).fetchone()
        if existing:
            return "replayed"

        with self.conn.transaction():
            updated = self.conn.execute(
                "UPDATE core.candidate_plan"
                " SET status = 'confirmed', confirmed_at = now(), confirmed_by = %s, op_id = %s"
                " WHERE id = %s AND status = 'pending'"
                " RETURNING id",
                (USER_A, op_id, plan_id),
            ).fetchone()
            if updated is None:
                raise RuntimeError("plan is not pending")
            self.conn.execute(
                "INSERT INTO core.candidate_plan_decision"
                " (plan_id, decision, decided_by, operation_id)"
                " VALUES (%s, 'confirmed', %s, %s)",
                (plan_id, USER_A, op_id),
            )
            self.conn.execute(
                "INSERT INTO core.task"
                " (matter_id, plan_id, plan_item_id, executor_id, title,"
                "  official_deadline_date, official_deadline_at, suggested_date, status)"
                " SELECT p.matter_id, p.id, i.id, %s, i.title,"
                "        i.official_deadline_date, i.official_deadline_at, i.suggested_date, 'pending'"
                " FROM core.candidate_plan p"
                " JOIN core.candidate_plan_item i ON i.plan_id = p.id"
                " WHERE p.id = %s"
                " ORDER BY i.seq",
                (USER_A, plan_id),
            )
        self.conn.commit()
        return "confirmed"

    def count(self, table: str) -> int:
        query = sql.SQL("SELECT count(*) FROM {}").format(
            sql.Identifier(*table.split("."))
        )
        return fetch_scalar(self.conn, query)

    # ---------- tests ----------

    def test_01_schema_objects_and_migration_log(self) -> None:
        tables = {
            row[0]
            for row in self.conn.execute(
                "SELECT table_schema || '.' || table_name FROM information_schema.tables"
                " WHERE table_schema IN ('core', 'ops') AND table_type = 'BASE TABLE'"
            )
        }
        expected_tables = {
            "core.app_user",
            "core.workspace",
            "core.matter_type",
            "core.template_version",
            "core.matter",
            "core.matter_source",
            "core.requirement",
            "core.requirement_self_check",
            "core.agent_run",
            "core.candidate_plan",
            "core.candidate_plan_item",
            "core.candidate_plan_item_source",
            "core.candidate_plan_decision",
            "core.task",
            "ops.source",
            "ops.snapshot",
            "ops.evidence",
            "ops.schema_version",
        }
        self.assertEqual(expected_tables, tables)

        views = {
            row[0]
            for row in self.conn.execute(
                "SELECT table_schema || '.' || table_name FROM information_schema.views"
                " WHERE table_schema = 'core'"
            )
        }
        self.assertEqual(
            {"core.v_matter_overview", "core.v_plan_detail", "core.v_task_list"}, views
        )
        self.assertEqual(
            len(list((DB_DIR / "migrations").glob("*.sql"))),
            self.count("ops.schema_version"),
        )
        self.assertEqual(
            {"pre_recommend", "competition"},
            {
                row[0]
                for row in self.conn.execute("SELECT type_code FROM core.matter_type")
            },
        )

    def test_02_matter_persists_and_can_be_reread(self) -> None:
        self.make_identity(USER_A, WS_A, MATTER_A, "申请 2027 推免")
        self.conn.commit()

        with psycopg.connect(test_dsn()) as fresh:
            row = fresh.execute(
                "SELECT goal, status, scope_year, scope_attrs->>'school'"
                " FROM core.matter WHERE id = %s",
                (MATTER_A,),
            ).fetchone()
        self.assertEqual(("申请 2027 推免", "active", 2027, "示例大学"), row)

        before = fetch_scalar(
            self.conn, "SELECT updated_at FROM core.matter WHERE id = %s", (MATTER_A,)
        )
        self.conn.execute(
            "UPDATE core.matter SET goal = '更新后的目标' WHERE id = %s", (MATTER_A,)
        )
        after = fetch_scalar(
            self.conn, "SELECT updated_at FROM core.matter WHERE id = %s", (MATTER_A,)
        )
        self.assertGreater(after, before)

    def test_03_matter_constraints(self) -> None:
        self.make_identity(USER_A, WS_A, MATTER_A, "目标")
        self.conn.commit()
        with self.assertRaises(errors.CheckViolation):
            self.conn.execute(
                "INSERT INTO core.matter (workspace_id, type_code, template_version_id, goal, scope_year)"
                " VALUES (%s, 'pre_recommend', %s, '目标', 2019)",
                (WS_A, TEMPLATE_PRE),
            )
        self.conn.rollback()

        with self.assertRaises(errors.CheckViolation):
            self.conn.execute(
                "INSERT INTO core.matter (workspace_id, type_code, template_version_id, goal)"
                " VALUES (%s, 'pre_recommend', %s, '   ')",
                (WS_A, TEMPLATE_PRE),
            )
        self.conn.rollback()

        with self.assertRaises(errors.CheckViolation):
            self.conn.execute(
                "UPDATE core.matter SET status = 'archived' WHERE id = %s", (MATTER_A,)
            )
        self.conn.rollback()

    def test_04_source_snapshot_requirement_evidence(self) -> None:
        self.make_identity(USER_A, WS_A, MATTER_A, "目标")
        self.make_source_chain()
        self.conn.commit()

        row = self.conn.execute(
            "SELECT r.label, e.locator, s.publisher, sn.version_no"
            " FROM core.requirement r"
            " JOIN ops.evidence e ON e.target_id = r.id AND e.target_type = 'requirement'"
            " JOIN ops.source s ON s.id = e.source_id"
            " JOIN ops.snapshot sn ON sn.id = e.snapshot_id"
            " WHERE r.id = %s",
            (REQ_ID,),
        ).fetchone()
        self.assertEqual(("成绩排名", "第 2 节", "示例大学研究生院", 1), row)

        with self.assertRaises(errors.CheckViolation):
            self.conn.execute(
                "INSERT INTO ops.evidence (source_id, snapshot_id, target_type, target_id,"
                " locator_kind, locator, fetched_at)"
                " VALUES (%s, %s, 'requirement', %s, 'section', '另一处', %s)",
                (
                    SOURCE_ID,
                    SNAPSHOT_ID,
                    REQ_ID,
                    datetime(2026, 11, 18, 3, 0, tzinfo=UTC),
                ),
            )
        self.conn.rollback()

        # 新快照成为 current，旧快照自动让位；内容相同的快照被唯一约束拒绝。
        snapshot_2 = UUID("33333333-3333-7333-8333-333333333335")
        self.conn.execute(
            "INSERT INTO ops.snapshot (id, source_id, version_no, object_key, content_hash,"
            " extraction, fetched_at, is_current)"
            " VALUES (%s, %s, 2, 'inline:test2', %s, '{}', %s, true)",
            (snapshot_2, SOURCE_ID, HASH_2, FIXED_FETCHED),
        )
        self.assertFalse(
            fetch_scalar(
                self.conn,
                "SELECT is_current FROM ops.snapshot WHERE id = %s",
                (SNAPSHOT_ID,),
            )
        )
        self.conn.commit()

        with self.assertRaises(errors.UniqueViolation):
            self.conn.execute(
                "INSERT INTO ops.snapshot (id, source_id, version_no, object_key, content_hash,"
                " fetched_at) VALUES (gen_random_uuid(), %s, 3, 'inline:dup', %s, %s)",
                (SOURCE_ID, HASH_2, FIXED_FETCHED),
            )
        self.conn.rollback()

    def test_05_reject_plan_writes_no_task(self) -> None:
        self.make_identity(USER_A, WS_A, MATTER_A, "目标")
        self.make_source_chain()
        self.make_plan()
        self.reject_plan(PLAN_ID, UUID("55555555-5555-7555-8555-555555555550"))

        self.assertEqual(0, self.count("core.task"))
        self.assertEqual(
            2,
            fetch_scalar(
                self.conn,
                "SELECT item_count FROM core.v_plan_detail WHERE id = %s",
                (PLAN_ID,),
            ),
        )
        self.assertEqual(
            "rejected",
            fetch_scalar(
                self.conn,
                "SELECT decision FROM core.candidate_plan_decision WHERE plan_id = %s",
                (PLAN_ID,),
            ),
        )
        self.assertIsNone(
            fetch_scalar(
                self.conn,
                "SELECT op_id FROM core.candidate_plan WHERE id = %s",
                (PLAN_ID,),
            )
        )

    def test_06_confirm_writes_tasks_and_is_idempotent(self) -> None:
        self.make_identity(USER_A, WS_A, MATTER_A, "目标")
        self.make_source_chain()
        self.make_plan()
        self.conn.commit()

        op_id = UUID("55555555-5555-7555-8555-555555555551")
        self.assertEqual("confirmed", self.confirm_plan(PLAN_ID, op_id))
        self.assertEqual(2, self.count("core.task"))
        self.assertEqual(
            {"pending"},
            {row[0] for row in self.conn.execute("SELECT status FROM core.task")},
        )

        # 换一个连接重读，确认任务已经持久化。
        with psycopg.connect(test_dsn()) as fresh:
            persisted = fetch_scalar(
                fresh,
                "SELECT count(*) FROM core.task WHERE matter_id = %s",
                (MATTER_A,),
            )
        self.assertEqual(2, persisted)
        self.assertEqual(1, self.count("core.candidate_plan_decision"))

        # 第二次使用同一个 op_id：返回同次结果，不新增任务。
        self.assertEqual("replayed", self.confirm_plan(PLAN_ID, op_id))
        self.assertEqual(2, self.count("core.task"))

        # 已确认的计划不能再被第二次确认（不同 op_id 也无效）。
        other_op = UUID("55555555-5555-7555-8555-555555555552")
        with self.assertRaises(RuntimeError):
            self.confirm_plan(PLAN_ID, other_op)
        self.conn.rollback()

        # 同一计划项只能对应一个任务。
        with self.assertRaises(errors.UniqueViolation):
            self.conn.execute(
                "INSERT INTO core.task (matter_id, plan_id, plan_item_id, executor_id, title)"
                " VALUES (%s, %s, %s, %s, '重复任务')",
                (MATTER_A, PLAN_ID, ITEM_1, USER_A),
            )
        self.conn.rollback()

        # 未确认的计划不能直接写任务。
        plan_2 = UUID("44444444-4444-7444-8444-444444444444")
        self.conn.execute(
            "INSERT INTO core.candidate_plan"
            " (id, matter_id, version_no, status, basis_version, basis_input)"
            " VALUES (%s, %s, 2, 'draft', repeat('b', 64), '{}')",
            (plan_2, MATTER_A),
        )
        self.conn.execute(
            "INSERT INTO core.candidate_plan_item (id, plan_id, seq, title)"
            " VALUES (%s, %s, 1, '候选任务')",
            (UUID("44444444-4444-7444-8444-444444444445"), plan_2),
        )
        self.conn.execute(
            "UPDATE core.candidate_plan SET status = 'pending' WHERE id = %s", (plan_2,)
        )
        with self.assertRaises(errors.CheckViolation) as ctx:
            self.conn.execute(
                "INSERT INTO core.task (matter_id, plan_id, plan_item_id, executor_id, title)"
                " VALUES (%s, %s, %s, %s, '提前写入')",
                (
                    MATTER_A,
                    plan_2,
                    UUID("44444444-4444-7444-8444-444444444445"),
                    USER_A,
                ),
            )
        self.assertIn("未确认", str(ctx.exception))
        self.conn.rollback()

    def test_07_task_done_requires_evidence(self) -> None:
        self.make_identity(USER_A, WS_A, MATTER_A, "目标")
        self.make_source_chain()
        self.make_plan()
        self.conn.commit()
        self.confirm_plan(PLAN_ID, UUID("55555555-5555-7555-8555-555555555553"))

        task_id = fetch_scalar(
            self.conn, "SELECT id FROM core.task ORDER BY title LIMIT 1"
        )
        with self.assertRaises(errors.CheckViolation):
            self.conn.execute(
                "UPDATE core.task SET status = 'done' WHERE id = %s", (task_id,)
            )
        self.conn.rollback()

        self.conn.execute(
            "UPDATE core.task SET status = 'done', completion_evidence = '成绩单已盖章'"
            " WHERE id = %s",
            (task_id,),
        )
        row = self.conn.execute(
            "SELECT status, completion_evidence FROM core.v_task_list WHERE id = %s",
            (task_id,),
        ).fetchone()
        self.assertEqual(("done", "成绩单已盖章"), row)

    def test_08_cross_workspace_rls(self) -> None:
        self.make_identity(USER_A, WS_A, MATTER_A, "A 的事项")
        self.make_identity(USER_B, WS_B, MATTER_B, "B 的事项")
        self.make_source_chain()
        self.make_plan()
        self.conn.commit()
        self.confirm_plan(PLAN_ID, UUID("55555555-5555-7555-8555-555555555554"))
        self.conn.commit()

        self.conn.execute(f"SET ROLE {TEST_ROLE}")
        try:
            self.conn.execute(
                "SELECT set_config('app.current_workspace_id', %s, false)", (str(WS_A),)
            )
            self.assertEqual(1, self.count("core.matter"))
            self.assertEqual(2, self.count("core.task"))
            self.assertEqual(1, self.count("core.candidate_plan"))
            self.assertEqual(2, self.count("core.candidate_plan_item"))
            self.assertEqual(1, self.count("core.candidate_plan_item_source"))
            self.assertEqual(1, self.count("core.candidate_plan_decision"))
            self.assertEqual(1, self.count("core.requirement"))
            self.assertEqual(1, self.count("core.v_matter_overview"))
            self.assertEqual(
                0,
                fetch_scalar(
                    self.conn,
                    "SELECT count(*) FROM core.v_task_list WHERE matter_id = %s",
                    (MATTER_B,),
                ),
            )
            self.assertEqual(
                0,
                fetch_scalar(
                    self.conn,
                    "SELECT count(*) FROM core.matter WHERE id = %s",
                    (MATTER_B,),
                ),
            )

            self.conn.execute(
                "SELECT set_config('app.current_workspace_id', %s, false)", (str(WS_B),)
            )
            self.assertEqual(0, self.count("core.task"))
            self.assertEqual(0, self.count("core.candidate_plan"))

            # 切回 A 的工作区，再尝试写入 B 的事项：WITH CHECK 必须拒绝。
            self.conn.execute(
                "SELECT set_config('app.current_workspace_id', %s, false)", (str(WS_A),)
            )
            with self.assertRaises(errors.InsufficientPrivilege):
                self.conn.execute(
                    "INSERT INTO core.matter (workspace_id, type_code, template_version_id, goal)"
                    " VALUES (%s, 'pre_recommend', %s, '越权写入')",
                    (WS_B, TEMPLATE_PRE),
                )
        finally:
            self.conn.rollback()
            self.conn.execute("RESET ROLE")
            self.conn.execute("RESET app.current_workspace_id")
            self.conn.commit()

    def test_09_cascade_delete_cleans_aggregate_but_keeps_source(self) -> None:
        self.make_identity(USER_A, WS_A, MATTER_A, "目标")
        self.make_source_chain()
        self.make_plan()
        self.conn.commit()
        self.confirm_plan(PLAN_ID, UUID("55555555-5555-7555-8555-555555555555"))
        self.conn.commit()

        self.conn.execute("DELETE FROM core.matter WHERE id = %s", (MATTER_A,))
        self.conn.commit()

        self.assertEqual(0, self.count("core.task"))
        self.assertEqual(0, self.count("core.candidate_plan"))
        self.assertEqual(0, self.count("core.candidate_plan_item"))
        self.assertEqual(0, self.count("core.candidate_plan_item_source"))
        self.assertEqual(0, self.count("core.candidate_plan_decision"))
        self.assertEqual(0, self.count("core.requirement"))
        self.assertEqual(0, self.count("ops.evidence"))
        self.assertEqual(1, self.count("ops.source"))
        self.assertEqual(1, self.count("ops.snapshot"))

    def test_10_plan_state_time_constraints(self) -> None:
        self.make_identity(USER_A, WS_A, MATTER_A, "目标")

        self.conn.execute(
            "INSERT INTO core.candidate_plan"
            " (id, matter_id, version_no, status, basis_version, basis_input, expired_at)"
            " VALUES (%s, %s, 1, 'expired', repeat('c', 64), '{}', now())",
            (PLAN_ID, MATTER_A),
        )
        self.conn.commit()

        invalid_rows: list[tuple[str, LiteralString, tuple[object, ...]]] = [
            (
                "expired without expired_at",
                (
                    "INSERT INTO core.candidate_plan"
                    " (id, matter_id, version_no, status, basis_version, basis_input)"
                    " VALUES (%s, %s, 2, 'expired', repeat('d', 64), '{}')"
                ),
                (UUID("44444444-4444-7444-8444-444444444446"), MATTER_A),
            ),
            (
                "confirmed without confirmed_at",
                (
                    "INSERT INTO core.candidate_plan"
                    " (id, matter_id, version_no, status, basis_version, basis_input)"
                    " VALUES (%s, %s, 3, 'confirmed', repeat('e', 64), '{}')"
                ),
                (UUID("44444444-4444-7444-8444-444444444447"), MATTER_A),
            ),
            (
                "confirmed with expired_at",
                (
                    "INSERT INTO core.candidate_plan"
                    " (id, matter_id, version_no, status, basis_version, basis_input,"
                    "  confirmed_at, confirmed_by, expired_at)"
                    " VALUES (%s, %s, 4, 'confirmed', repeat('f', 64), '{}', now(), %s, now())"
                ),
                (UUID("44444444-4444-7444-8444-444444444448"), MATTER_A, USER_A),
            ),
        ]
        for label, statement, params in invalid_rows:
            with self.subTest(label=label):
                with self.assertRaises(errors.CheckViolation):
                    self.conn.execute(statement, params)
                self.conn.rollback()

        # 未确认的计划不能写确认决定。
        with self.assertRaises(errors.CheckViolation):
            self.conn.execute(
                "INSERT INTO core.candidate_plan_decision"
                " (plan_id, decision, decided_by, operation_id)"
                " VALUES (%s, 'confirmed', %s, %s)",
                (PLAN_ID, USER_A, UUID("55555555-5555-7555-8555-555555555556")),
            )
        self.conn.rollback()

    def test_11_plan_item_freeze_and_dependencies(self) -> None:
        self.make_identity(USER_A, WS_A, MATTER_A, "目标")
        self.make_source_chain()
        self.make_plan()
        self.conn.commit()

        self.assertEqual(1, self.count("core.candidate_plan_item_source"))

        # pending 计划的条目已经冻结。
        with self.assertRaises(errors.CheckViolation):
            self.conn.execute(
                "INSERT INTO core.candidate_plan_item (plan_id, seq, title)"
                " VALUES (%s, 3, '锁定后新增')",
                (PLAN_ID,),
            )
        self.conn.rollback()

        # 草稿计划内仍可编辑，但依赖必须指向同一计划。
        draft_plan = UUID("44444444-4444-7444-8444-444444444460")
        draft_item = UUID("44444444-4444-7444-8444-444444444461")
        self.conn.execute(
            "INSERT INTO core.candidate_plan"
            " (id, matter_id, version_no, status, basis_version, basis_input)"
            " VALUES (%s, %s, 2, 'draft', repeat('c', 64), '{}')",
            (draft_plan, MATTER_A),
        )
        self.conn.commit()
        with self.assertRaises(errors.CheckViolation):
            self.conn.execute(
                "INSERT INTO core.candidate_plan_item"
                " (id, plan_id, seq, title, depends_on_item_ids)"
                " VALUES (%s, %s, 1, '越界依赖', %s)",
                (
                    draft_item,
                    draft_plan,
                    [UUID("99999999-9999-7999-8999-999999999999")],
                ),
            )
        self.conn.rollback()

        # 来源必须与快照一致。
        source_2 = UUID("33333333-3333-7333-8333-333333333340")
        self.conn.execute(
            "INSERT INTO ops.source (id, publisher, url, matter_type_id, scope_year,"
            " status, auto_check_status, roi_status)"
            " SELECT %s, '另一发布主体', 'https://example.test/other', id, 2027,"
            " 'active', 'passed', 'original' FROM core.matter_type"
            " WHERE type_code = 'pre_recommend'",
            (source_2,),
        )
        self.conn.execute(
            "INSERT INTO core.candidate_plan_item (id, plan_id, seq, title)"
            " VALUES (%s, %s, 1, '来源校验')",
            (draft_item, draft_plan),
        )
        with self.assertRaises(errors.CheckViolation):
            self.conn.execute(
                "INSERT INTO core.candidate_plan_item_source"
                " (plan_item_id, source_id, snapshot_id, locator_kind, locator)"
                " VALUES (%s, %s, %s, 'section', '另一处')",
                (draft_item, source_2, SNAPSHOT_ID),
            )
        self.conn.rollback()

    def test_12_snapshot_immutability_and_evidence_source(self) -> None:
        self.make_identity(USER_A, WS_A, MATTER_A, "目标")
        self.make_source_chain()
        snapshot_2 = UUID("33333333-3333-7333-8333-333333333341")
        self.conn.execute(
            "INSERT INTO ops.snapshot (id, source_id, version_no, object_key,"
            " content_hash, fetched_at, is_current)"
            " VALUES (%s, %s, 2, 'inline:test2', %s, %s, false)",
            (snapshot_2, SOURCE_ID, HASH_2, FIXED_FETCHED),
        )
        self.conn.commit()

        with self.assertRaises(errors.CheckViolation):
            self.conn.execute(
                "UPDATE ops.snapshot SET object_key = 'inline:changed' WHERE id = %s",
                (snapshot_2,),
            )
        self.conn.rollback()

        with self.assertRaises(errors.CheckViolation):
            self.conn.execute("DELETE FROM ops.snapshot WHERE id = %s", (snapshot_2,))
        self.conn.rollback()

        source_2 = UUID("33333333-3333-7333-8333-333333333342")
        self.conn.execute(
            "INSERT INTO ops.source (id, publisher, url, matter_type_id, scope_year,"
            " status, auto_check_status, roi_status)"
            " SELECT %s, '另一发布主体', 'https://example.test/other-2', id, 2027,"
            " 'active', 'passed', 'original' FROM core.matter_type"
            " WHERE type_code = 'pre_recommend'",
            (source_2,),
        )
        with self.assertRaises(errors.CheckViolation):
            self.conn.execute(
                "INSERT INTO ops.evidence (source_id, snapshot_id, target_type, target_id,"
                " locator_kind, locator, fetched_at)"
                " VALUES (%s, %s, 'evaluation', %s, 'section', '第 1 节', %s)",
                (
                    source_2,
                    snapshot_2,
                    UUID("99999999-9999-7999-8999-999999999999"),
                    FIXED_FETCHED,
                ),
            )
        self.conn.rollback()

    def test_13_plan_decision_and_actor_owner(self) -> None:
        self.make_identity(USER_A, WS_A, MATTER_A, "目标")
        self.make_source_chain()
        self.make_plan()
        self.conn.commit()

        # 直接改状态而不写决定，提交时必须失败。
        direct_plan = UUID("44444444-4444-7444-8444-444444444470")
        self.conn.execute(
            "INSERT INTO core.candidate_plan"
            " (id, matter_id, version_no, status, basis_version, basis_input)"
            " VALUES (%s, %s, 2, 'pending', repeat('d', 64), '{}')",
            (direct_plan, MATTER_A),
        )
        self.conn.execute(
            "UPDATE core.candidate_plan"
            " SET status = 'confirmed', confirmed_at = now(), confirmed_by = %s"
            " WHERE id = %s",
            (USER_A, direct_plan),
        )
        with self.assertRaises(errors.CheckViolation):
            self.conn.commit()
        self.conn.rollback()

        # 任务执行人必须是工作区所有者。
        self.confirm_plan(PLAN_ID, UUID("55555555-5555-7555-8555-555555555557"))
        with self.assertRaises(errors.CheckViolation):
            self.conn.execute(
                "INSERT INTO core.task"
                " (matter_id, plan_id, plan_item_id, executor_id, title)"
                " VALUES (%s, %s, %s, %s, '他人任务')",
                (MATTER_A, PLAN_ID, ITEM_2, USER_B),
            )
        self.conn.rollback()


if __name__ == "__main__":
    unittest.main(verbosity=2)
