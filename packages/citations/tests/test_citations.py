"""Exercise real notice metadata and deliberately invalid boundary inputs."""

import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from uuid import UUID

import pytest

from offerpilot_citations import (
    CitationValidationError,
    build_fact_references,
    build_official_citations,
)

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "fzu_notice.json"
OWNER = UUID("57078387-8ad5-4d3a-9172-ed1b677df6b6")
MATTER = UUID("3e8d27b5-07d4-44ca-bae5-f2f4e57bf631")
OTHER = UUID("c8355abf-28ec-40ef-af75-a6cc282c5a54")


@pytest.fixture
def notice():
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


@pytest.fixture
def fact(notice):
    # Test-only identifiers; no real student's facts or document contents.
    return {
        "kind": "personal_fact",
        "owner_id": str(OWNER),
        "matter_id": str(MATTER),
        "fact_id": "f49ed34f-b54a-45be-b9be-76511a42d97f",
        "fact_version": 2,
        "confirmed_at": notice["snapshots"][0]["fetched_at"],
    }


def issue_codes(error):
    return {issue.code for issue in error.value.issues}


def test_real_notice_metadata_and_evidence(notice):
    original = copy.deepcopy(notice)
    result = build_official_citations(notice)
    citation = result["citations"][0]
    provenance = json.loads(
        (ROOT / "examples" / "fzu_notice_provenance.json").read_text(encoding="utf-8")
    )
    assert citation["url"] == provenance["url"]
    assert citation["publisher"] == "福州大学数学与统计学院"
    assert result["scope_year"] == 2027
    assert citation["fetched_at"].startswith("2026-11-15T")
    assert citation["quote"] == provenance["quote"]
    assert citation["quote_hash"] == hashlib.sha256(citation["quote"].encode()).hexdigest()
    assert citation["basis"] == {
        "source_id": notice["citations"][0]["source_id"],
        "snapshot_id": notice["citations"][0]["snapshot_id"],
        "fetched_at": citation["fetched_at"],
        "locator": "第（4）项",
    }
    assert citation["version_no"] == 1
    assert notice == original


@pytest.mark.parametrize(
    ("container", "field"),
    [
        ("snapshots", "source_id"),
        ("snapshots", "snapshot_id"),
        ("snapshots", "version_no"),
        ("snapshots", "publisher"),
        ("snapshots", "url"),
        ("snapshots", "title"),
        ("snapshots", "scope_year"),
        ("snapshots", "fetched_at"),
        ("citations", "source_id"),
        ("citations", "snapshot_id"),
        ("citations", "fetched_at"),
        ("citations", "locator"),
    ],
)
def test_missing_fields_report_exact_path(notice, container, field):
    del notice[container][0][field]
    with pytest.raises(CitationValidationError) as error:
        build_official_citations(notice)
    assert any(
        issue.path == f"{container}.0.{field}" and issue.code == "missing_field"
        for issue in error.value.issues
    )


@pytest.mark.parametrize("field", ["publisher", "title"])
def test_whitespace_metadata_is_a_gap(notice, field):
    notice["snapshots"][0][field] = " \n\t "
    with pytest.raises(CitationValidationError):
        build_official_citations(notice)


def test_normalization_preserves_url_query_and_snapshot(notice):
    notice["snapshots"][0]["publisher"] = "  福州大学数学与统计学院  "
    notice["snapshots"][0]["url"] = "https://math.fzu.edu.cn/download?id=7&version=2#section"
    item = build_official_citations(notice)["citations"][0]
    assert item["publisher"] == "福州大学数学与统计学院"
    assert item["url"].endswith("?id=7&version=2#section")
    assert item["snapshot_id"] == notice["snapshots"][0]["snapshot_id"]


@pytest.mark.parametrize(
    ("locator", "expected"),
    [
        ({"kind": "section", "section": "第（4）项"}, "第（4）项"),
        ({"kind": "page", "page": 3}, "第3页"),
        ({"kind": "page", "page": 3, "end_page": 5}, "第3—5页"),
        (
            {"kind": "text_span", "paragraph": 4, "start": 0, "end": 18},
            "第4段，字符[0:18]",
        ),
        ({"kind": "table_row", "table": "材料清单", "row": 2}, "材料清单，第2行"),
    ],
)
def test_explicit_locator_formats(notice, locator, expected):
    notice["citations"][0]["locator"] = locator
    assert build_official_citations(notice)["citations"][0]["locator_text"] == expected


@pytest.mark.parametrize(
    "locator",
    [
        {"kind": "section", "section": "  "},
        {"kind": "page"},
        {"kind": "page", "page": 0},
        {"kind": "page", "page": True},
        {"kind": "page", "page": "3"},
        {"kind": "page", "page": 3, "end_page": 2},
        {"kind": "text_span", "paragraph": 0, "start": 0, "end": 3},
        {"kind": "text_span", "paragraph": 1, "start": 3, "end": 3},
        {"kind": "text_span", "paragraph": 1, "start": -1, "end": 3},
        {"kind": "table_row", "table": "", "row": 1},
        {"kind": "guessed", "section": "第1项"},
    ],
)
def test_invalid_locators_are_rejected(notice, locator):
    notice["citations"][0]["locator"] = locator
    with pytest.raises(CitationValidationError):
        build_official_citations(notice)


@pytest.mark.parametrize("collection", ["snapshots", "citations"])
def test_empty_collections_are_rejected(notice, collection):
    notice[collection] = []
    with pytest.raises(CitationValidationError):
        build_official_citations(notice)


@pytest.mark.parametrize("timestamp", ["2026-11-15", "2026-11-15T12:00:00", 1794744000])
def test_timestamps_require_explicit_timezone(notice, timestamp):
    notice["snapshots"][0]["fetched_at"] = timestamp
    with pytest.raises(CitationValidationError):
        build_official_citations(notice)


def test_equivalent_timezones_match(notice):
    notice["snapshots"][0]["fetched_at"] = "2026-11-15T12:00:00Z"
    notice["citations"][0]["fetched_at"] = "2026-11-15T20:00:00+08:00"
    assert build_official_citations(notice)["citations"][0]["fetched_at"] == (
        "2026-11-15T12:00:00Z"
    )


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("source_id", str(OTHER), "source_snapshot_mismatch"),
        ("snapshot_id", str(OTHER), "unknown_snapshot"),
        ("fetched_at", "2026-11-15T00:00:00Z", "snapshot_time_mismatch"),
    ],
)
def test_reference_must_match_registered_snapshot(notice, field, value, code):
    notice["citations"][0][field] = value
    with pytest.raises(CitationValidationError) as error:
        build_official_citations(notice)
    assert code in issue_codes(error)


def test_unrelated_year_is_rejected(notice):
    notice["scope_year"] = 2026
    with pytest.raises(CitationValidationError) as error:
        build_official_citations(notice)
    assert "scope_year_mismatch" in issue_codes(error)


def test_snapshot_registry_is_unambiguous(notice):
    notice["snapshots"].append(copy.deepcopy(notice["snapshots"][0]))
    with pytest.raises(CitationValidationError) as error:
        build_official_citations(notice)
    assert "duplicate_snapshot" in issue_codes(error)


def test_snapshot_versions_are_unique_within_source(notice):
    another = copy.deepcopy(notice["snapshots"][0])
    another["snapshot_id"] = str(OTHER)
    notice["snapshots"].append(another)
    with pytest.raises(CitationValidationError) as error:
        build_official_citations(notice)
    assert "duplicate_snapshot_version" in issue_codes(error)


def test_distinct_historical_versions_remain_distinct(notice):
    snapshot = copy.deepcopy(notice["snapshots"][0])
    snapshot.update(snapshot_id=str(OTHER), version_no=2, fetched_at="2026-11-15T23:00:00Z")
    reference = copy.deepcopy(notice["citations"][0])
    reference.update(snapshot_id=str(OTHER), fetched_at=snapshot["fetched_at"])
    notice["snapshots"].append(snapshot)
    notice["citations"].append(reference)
    refs = build_official_citations(notice)["citations"]
    assert [r["version_no"] for r in refs] == [1, 2]
    assert refs[0]["snapshot_id"] != refs[1]["snapshot_id"]


def test_exact_duplicate_citation_is_collapsed(notice):
    notice["citations"].append(copy.deepcopy(notice["citations"][0]))
    assert len(build_official_citations(notice)["citations"]) == 1


def test_equivalent_single_page_locators_are_collapsed(notice):
    notice["citations"][0]["locator"] = {"kind": "page", "page": 3}
    another = copy.deepcopy(notice["citations"][0])
    another["locator"]["end_page"] = 3
    notice["citations"].append(another)
    assert len(build_official_citations(notice)["citations"]) == 1


def test_duplicate_location_with_conflicting_quote_is_rejected(notice):
    another = copy.deepcopy(notice["citations"][0])
    another["quote"] = "不同引文"
    notice["citations"].append(another)
    with pytest.raises(CitationValidationError) as error:
        build_official_citations(notice)
    assert "conflicting_quote" in issue_codes(error)


def test_locator_storage_collision_is_rejected(notice):
    notice["citations"][0]["locator"] = {"kind": "section", "section": "第3页"}
    another = copy.deepcopy(notice["citations"][0])
    another["locator"] = {"kind": "page", "page": 3}
    notice["citations"].append(another)
    with pytest.raises(CitationValidationError) as error:
        build_official_citations(notice)
    assert "locator_collision" in issue_codes(error)


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "file:///C:/private.txt",
        "https://account:secret@math.fzu.edu.cn/notice",
        "https://math.fzu.edu.cn/\nnotice",
    ],
)
def test_unsafe_url_forms_are_rejected(notice, url):
    notice["snapshots"][0]["url"] = url
    with pytest.raises(CitationValidationError):
        build_official_citations(notice)


def test_uploaded_content_cannot_be_promoted(notice):
    notice["snapshots"][0]["origin"] = "user_upload"
    with pytest.raises(CitationValidationError):
        build_official_citations(notice)


def test_private_records_cannot_enter_public_list(notice, fact):
    notice["citations"].append(fact)
    with pytest.raises(CitationValidationError):
        build_official_citations(notice)


def test_extra_private_data_is_rejected_without_echo(notice):
    secret = "PRIVATE-STUDENT-DATA-NEVER-ECHO"
    notice["citations"][0]["fact_value"] = secret
    with pytest.raises(CitationValidationError) as error:
        build_official_citations(notice)
    assert "extra_forbidden" in issue_codes(error)
    assert secret not in str(error.value)
    assert secret not in json.dumps(error.value.as_dict())
    assert "fact_value" in str(error.value)


def test_one_bad_reference_blocks_entire_output(notice):
    another = copy.deepcopy(notice["citations"][0])
    del another["snapshot_id"]
    notice["citations"].append(another)
    with pytest.raises(CitationValidationError):
        build_official_citations(notice)


def test_owner_scoped_private_references(fact):
    original = copy.deepcopy(fact)
    refs = build_fact_references([fact], current_user_id=OWNER, matter_id=MATTER)
    assert refs[0]["kind"] == "personal_fact"
    assert refs[0]["fact_version"] == 2
    assert "value_text" not in refs[0]
    assert fact == original


@pytest.mark.parametrize(
    ("user", "matter", "code"),
    [(OTHER, MATTER, "owner_mismatch"), (OWNER, OTHER, "matter_mismatch")],
)
def test_private_references_are_scoped_to_context(fact, user, matter, code):
    with pytest.raises(CitationValidationError) as error:
        build_fact_references([fact], current_user_id=user, matter_id=matter)
    assert code in issue_codes(error)


@pytest.mark.parametrize("field", ["fact_version", "confirmed_at"])
def test_unversioned_or_unconfirmed_fact_is_rejected(fact, field):
    del fact[field]
    with pytest.raises(CitationValidationError):
        build_fact_references([fact], current_user_id=OWNER, matter_id=MATTER)


def test_private_fact_values_are_not_accepted(fact):
    fact["value_text"] = "TEST-ONLY-VALUE"
    with pytest.raises(CitationValidationError):
        build_fact_references([fact], current_user_id=OWNER, matter_id=MATTER)


def test_cli_runs_real_notice_example():
    process = subprocess.run(
        [sys.executable, "-m", "offerpilot_citations", str(EXAMPLE)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert process.returncode == 0, process.stderr
    assert json.loads(process.stdout)["citations"][0]["publisher"] == "福州大学数学与统计学院"


@pytest.mark.parametrize(("content", "exit_code"), [("{", 2), ("{}", 1), ("[]", 1)])
def test_cli_reports_failures(tmp_path, content, exit_code):
    path = tmp_path / "input.json"
    path.write_text(content, encoding="utf-8")
    process = subprocess.run(
        [sys.executable, "-m", "offerpilot_citations", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert process.returncode == exit_code
    assert not process.stdout
    assert "error" in json.loads(process.stderr)
