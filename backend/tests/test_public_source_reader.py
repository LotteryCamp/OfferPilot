"""Reader tests driven by the captured public Fuzhou University notice."""

from __future__ import annotations

import gzip
import json
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path
from uuid import UUID

import pytest

from backend.sources import (
    PublicSourceRequest,
    PublicSourceResult,
    SourceReadError,
    parse_public_html,
    read_public_html,
    source_document_from_registration,
    source_registration_payload,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "sources"
HTML = FIXTURES / "fzu_notice.html.gz"
PROVENANCE = json.loads(
    (FIXTURES / "fzu_notice_provenance.json").read_text(encoding="utf-8")
)
FETCHED_AT = datetime.fromisoformat(PROVENANCE["retrieved_at"])
SOURCE_URL = "https://math.fzu.edu.cn/info/1171/10393.htm"
OWNER_MATTER = UUID("3e8d27b5-07d4-44ca-bae5-f2f4e57bf631")


def request(**kwargs: object) -> PublicSourceRequest:
    return PublicSourceRequest.model_validate(
        {
            "url": SOURCE_URL,
            "publisher": "福州大学数学与统计学院",
            "scope_year": 2027,
            "scope": "2027 届、本院、校内推免推荐",
            **kwargs,
        }
    )


def parse_fixture(**kwargs: object) -> PublicSourceResult:
    return parse_public_html(
        gzip.decompress(HTML.read_bytes()),
        content_type="text/html; charset=UTF-8",
        final_url=SOURCE_URL,
        request=request(**kwargs),
        fetched_at=FETCHED_AT,
    )


def test_reader_returns_traceable_result_from_real_notice():
    result = parse_fixture(matter_id=OWNER_MATTER)
    assert result.status == "success"
    assert result.matter_id == OWNER_MATTER
    assert str(result.url) == SOURCE_URL
    assert result.title == (
        "福州大学数学与统计学院2027年推荐优秀应届本科毕业生免试攻读研究生的工作方案"
        "-福州大学数学统计学院"
    )
    assert result.publisher == "福州大学数学与统计学院"
    assert result.scope_year == 2027
    assert result.scope == "2027 届、本院、校内推免推荐"
    assert result.published_date == date(2026, 9, 8)
    assert result.fetched_at == FETCHED_AT
    assert result.content_type == "text/html"
    assert result.content_hash == PROVENANCE["fixture_html_sha256"]
    excerpt = next(
        fragment for fragment in result.fragments if fragment.quote.startswith("（5）")
    )
    assert excerpt.locator.kind == "text_span"
    assert excerpt.locator_text == "第31段，字符[0:124]"
    assert "2026年9月10日下午15:00前" in excerpt.quote
    assert "成绩单" in excerpt.quote
    assert excerpt.quote in result.normalized_text


def test_same_notice_has_stable_snapshot_identity():
    first = parse_fixture()
    second = parse_fixture()
    assert first.source_id == second.source_id
    assert first.snapshot_id == second.snapshot_id
    assert first.content_hash == second.content_hash


def test_url_fragment_does_not_change_source_identity():
    with_fragment = parse_public_html(
        gzip.decompress(HTML.read_bytes()),
        content_type="text/html",
        final_url=f"{SOURCE_URL}#section-1",
        request=request(),
        fetched_at=FETCHED_AT,
    )
    without_fragment = parse_fixture()
    assert str(with_fragment.url) == SOURCE_URL
    assert with_fragment.source_id == without_fragment.source_id
    assert with_fragment.snapshot_id == without_fragment.snapshot_id


def test_changed_notice_gets_new_snapshot_version():
    first = parse_fixture()
    changed = parse_public_html(
        gzip.decompress(HTML.read_bytes()) + "\n<p>新增材料说明。</p>".encode(),
        content_type="text/html; charset=UTF-8",
        final_url=SOURCE_URL,
        request=request(),
        fetched_at=FETCHED_AT,
    )
    assert changed.source_id == first.source_id
    assert changed.snapshot_id != first.snapshot_id


def test_repeated_headings_get_distinct_locators():
    result = parse_public_html(
        gzip.decompress(HTML.read_bytes()),
        content_type="text/html",
        final_url=SOURCE_URL,
        request=request(),
        fetched_at=FETCHED_AT,
    )
    sections = [
        fragment.locator_text
        for fragment in result.fragments
        if fragment.locator.kind == "section"
    ]
    assert len(sections) == len(set(sections))


def test_fragment_limit_returns_structured_failure():
    with pytest.raises(SourceReadError) as error:
        parse_fixture(max_fragments=1)
    assert error.value.code == "too_many_fragments"


@pytest.mark.parametrize("content_type", ["application/pdf", "text/plain"])
def test_non_html_content_is_rejected(content_type):
    with pytest.raises(SourceReadError) as error:
        parse_public_html(
            gzip.decompress(HTML.read_bytes()),
            content_type=content_type,
            final_url=SOURCE_URL,
            request=request(),
            fetched_at=FETCHED_AT,
        )
    assert error.value.code == "unsupported_content_type"


def test_empty_content_is_rejected():
    with pytest.raises(SourceReadError) as error:
        parse_public_html(
            b"",
            content_type="text/html",
            final_url=SOURCE_URL,
            request=request(),
            fetched_at=FETCHED_AT,
        )
    assert error.value.code == "empty_content"


@pytest.mark.parametrize(
    "url",
    [
        "file:///C:/private.html",
        "javascript:alert(1)",
        "https://user:secret@example.com/notice",
        "http://127.0.0.1/notice",
    ],
)
def test_reader_rejects_non_public_urls(url):
    with pytest.raises(SourceReadError) as error:
        read_public_html({"url": url, "publisher": "福州大学", "scope_year": 2027})
    assert error.value.code == "unsafe_url"


def test_reader_rejects_missing_contract_fields():
    with pytest.raises(SourceReadError) as error:
        read_public_html({"url": SOURCE_URL, "scope_year": 2027})
    assert error.value.code == "invalid_request"


def test_reader_rejects_oversized_publisher():
    with pytest.raises(SourceReadError) as error:
        read_public_html(
            {"url": SOURCE_URL, "publisher": "x" * 161, "scope_year": 2027}
        )
    assert error.value.code == "invalid_request"


def test_real_notice_uses_locators_accepted_by_backend():
    result = parse_fixture()
    assert any(fragment.locator.kind == "table_row" for fragment in result.fragments)
    assert {fragment.locator.kind for fragment in result.fragments} == {
        "section",
        "table_row",
        "text_span",
    }


def test_registration_payload_contains_traceable_notice_fragments():
    result = parse_fixture(matter_id=OWNER_MATTER)
    payload = source_registration_payload(result)
    assert payload["url"] == SOURCE_URL
    assert payload["published_date"] == "2026-09-08"
    assert payload["fetched_at"] == FETCHED_AT.isoformat()
    assert payload["content_hash"] == PROVENANCE["fixture_html_sha256"]
    assert "matter_id" not in payload
    assert "version_no" not in payload
    assert "source_id" not in payload
    assert "snapshot_id" not in payload
    fragments = payload["fragments"]
    content = payload["content"]
    assert isinstance(fragments, list)
    assert isinstance(content, str)
    excerpt = next(
        fragment for fragment in fragments if fragment["quote"].startswith("（5）")
    )
    assert excerpt["locator_kind"] == "text_span"
    assert excerpt["locator"] == "第31段，字符[0:124]"
    assert excerpt["quote"] in content


def registered_notice():
    payload = source_registration_payload(parse_fixture())
    source_id = "00000000-0000-7000-8000-000000000004"
    return {
        "source": {
            "id": source_id,
            "publisher": payload["publisher"],
            "url": payload["url"],
            "scope": payload["scope"],
            "scope_year": 2027,
            "status": "active",
            "auto_check_status": "pending",
            "roi_status": "expired",
        },
        "snapshot": {
            "id": "00000000-0000-7000-8000-000000000005",
            "source_id": source_id,
            "version_no": 3,
            "title": payload["title"],
            "published_date": payload["published_date"],
            "text": payload["content"],
            "content_hash": payload["content_hash"],
            "fetched_at": "2026-11-16T02:00:00+00:00",
            "fragments": payload["fragments"],
        },
        "created": {"source": False, "snapshot": False},
    }


def test_agent_document_uses_registered_snapshot_identity_and_fragments():
    response = registered_notice()
    doc = source_document_from_registration(response)
    snapshot = response["snapshot"]
    assert doc["source_id"] == response["source"]["id"]
    assert doc["snapshot_id"] == doc["source_version_id"] == snapshot["id"]
    assert doc["snapshot_id"] != str(parse_fixture().snapshot_id)
    assert doc["version_no"] == 3
    assert doc["fetched_at"] == snapshot["fetched_at"]
    assert doc["fragments"] == snapshot["fragments"]
    assert doc["is_expired"] is True


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [("source_id", "00000000-0000-7000-8000-000000000006"), ("fragments", [])],
)
def test_agent_document_rejects_invalid_saved_evidence(field, bad_value):
    response = registered_notice()
    response["snapshot"][field] = bad_value
    with pytest.raises(SourceReadError) as error:
        source_document_from_registration(response)
    assert error.value.code == "invalid_registration"


@pytest.mark.parametrize(
    ("args", "exit_code", "code"),
    [
        ([], 2, "invalid_request"),
        (
            [
                "http://127.0.0.1/notice",
                "--publisher",
                "福州大学",
                "--scope-year",
                "2027",
            ],
            1,
            "unsafe_url",
        ),
    ],
)
def test_cli_reports_failures_without_a_success_result(args, exit_code, code):
    process = subprocess.run(
        [sys.executable, "-m", "backend.sources", *args],
        capture_output=True,
        encoding="utf-8",
        check=False,
        timeout=10,
    )
    assert process.returncode == exit_code
    assert not process.stdout
    error = json.loads(process.stderr)
    assert error["code"] == code
    assert "status" not in error
