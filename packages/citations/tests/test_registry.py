"""Source registration tests using the captured public notice."""

import gzip
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from offerpilot_citations import (
    PublicSourceRequest,
    SourceRegistrationError,
    SourceRegistry,
    parse_public_html,
)

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "examples" / "fzu_notice.html.gz"
SOURCE_URL = "https://math.fzu.edu.cn/info/1171/10393.htm"


def source_result(extra: bytes = b"", *, scope_year: int = 2027):
    return parse_public_html(
        gzip.decompress(HTML.read_bytes()) + extra,
        content_type="text/html; charset=UTF-8",
        final_url=SOURCE_URL,
        request=PublicSourceRequest(
            url=SOURCE_URL,
            publisher="福州大学数学与统计学院",
            scope_year=scope_year,
            matter_id="3e8d27b5-07d4-44ca-bae5-f2f4e57bf631",
        ),
    )


def test_registry_persists_matter_link_and_agent_citations():
    registry = SourceRegistry(":memory:")
    try:
        registered = registry.register(source_result())
        assert registered["status"] == "success"
        assert registered["matter_id"] == "3e8d27b5-07d4-44ca-bae5-f2f4e57bf631"
        assert registered["version_no"] == 1
        assert registered["citations"]
        assert registered["citations"][0]["snapshot_id"] == registered["snapshot_id"]
        assert registry.connection.execute("SELECT COUNT(*) FROM source").fetchone()[0] == 1
        assert registry.connection.execute("SELECT COUNT(*) FROM source_matter").fetchone()[0] == 1
    finally:
        registry.close()


def test_registry_reuses_metadata_and_versions_changed_snapshots():
    registry = SourceRegistry(":memory:")
    try:
        first = registry.register(source_result())
        same = registry.register(source_result())
        changed = registry.register(source_result("\n<p>新增材料说明。</p>".encode()))
        assert same["snapshot_id"] == first["snapshot_id"]
        assert same["version_no"] == first["version_no"]
        assert same["fetched_at"] == first["fetched_at"]
        assert changed["snapshot_id"] != first["snapshot_id"]
        assert changed["version_no"] == 2
        assert changed["citation_batch"]["snapshots"][0]["version_no"] == 2
        assert (
            registry.connection.execute("SELECT COUNT(*) FROM source_snapshot").fetchone()[0] == 2
        )
    finally:
        registry.close()


def test_scope_year_is_stored_per_snapshot():
    registry = SourceRegistry(":memory:")
    try:
        first = registry.register(source_result())
        second = registry.register(
            source_result("\n<p>下一年度说明。</p>".encode(), scope_year=2028)
        )
        assert second["version_no"] == 2
        assert second["scope_year"] == 2028
        assert second["citation_batch"]["snapshots"][0]["scope_year"] == 2028
        assert first["scope_year"] == 2027
    finally:
        registry.close()


def test_existing_snapshot_keeps_registered_metadata():
    registry = SourceRegistry(":memory:")
    try:
        first = source_result()
        registered = registry.register(first)
        changed_metadata = first.model_copy(
            update={"title": "错误标题", "publisher": "错误发布方", "scope_year": 2026}
        )
        same = registry.register(changed_metadata)
        assert same["title"] == registered["title"]
        assert same["publisher"] == registered["publisher"]
        assert same["scope_year"] == registered["scope_year"]
        assert same["citation_batch"]["snapshots"][0]["title"] == registered["title"]
    finally:
        registry.close()


def test_older_snapshot_cannot_be_registered_as_latest():
    registry = SourceRegistry(":memory:")
    try:
        newer = source_result("\n<p>新内容。</p>".encode()).model_copy(
            update={"fetched_at": datetime(2026, 11, 18, tzinfo=UTC)}
        )
        older = source_result().model_copy(
            update={"fetched_at": datetime(2026, 11, 17, tzinfo=UTC)}
        )
        registry.register(newer)
        with pytest.raises(SourceRegistrationError):
            registry.register(older)
    finally:
        registry.close()


def test_external_connection_transaction_is_not_committed():
    connection = sqlite3.connect(":memory:")
    registry = SourceRegistry(connection)
    connection.commit()
    connection.execute("CREATE TABLE pending(value TEXT)")
    connection.execute("INSERT INTO pending(value) VALUES ('caller-write')")
    registry.register(source_result())
    assert connection.execute("SELECT value FROM pending").fetchone()[0] == "caller-write"
    assert connection.in_transaction
    connection.rollback()
    assert connection.execute("SELECT COUNT(*) FROM pending").fetchone()[0] == 0
    registry.close()


def test_invalid_database_path_returns_structured_error(tmp_path):
    with pytest.raises(SourceRegistrationError):
        SourceRegistry(tmp_path / "missing" / "registry.sqlite")
