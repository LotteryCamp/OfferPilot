"""Source registration tests using the captured public notice."""

from pathlib import Path

from offerpilot_citations import PublicSourceRequest, SourceRegistry, parse_public_html

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "examples" / "fzu_notice.html"
SOURCE_URL = "https://math.fzu.edu.cn/info/1171/10393.htm"


def source_result(extra: bytes = b""):
    return parse_public_html(
        HTML.read_bytes() + extra,
        content_type="text/html; charset=UTF-8",
        final_url=SOURCE_URL,
        request=PublicSourceRequest(
            url=SOURCE_URL,
            publisher="福州大学数学与统计学院",
            scope_year=2027,
            matter_id="3e8d27b5-07d4-44ca-bae5-f2f4e57bf631",
        ),
    )


def test_registry_persists_matter_link_and_agent_citations():
    registry = SourceRegistry(":memory:")
    try:
        registered = registry.register(source_result())
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
        assert (
            registry.connection.execute("SELECT COUNT(*) FROM source_snapshot").fetchone()[0] == 2
        )
    finally:
        registry.close()
