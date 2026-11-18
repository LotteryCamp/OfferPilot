"""Reader tests driven by the captured public Fuzhou University notice."""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from uuid import UUID

import pytest

from offerpilot_citations import (
    PublicSourceRequest,
    SourceReadError,
    build_official_citations,
    parse_public_html,
    read_public_html,
)
from offerpilot_citations.reader_cli import main as reader_main

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "examples" / "fzu_notice.html.gz"
SOURCE_URL = "https://math.fzu.edu.cn/info/1171/10393.htm"
OWNER_MATTER = UUID("3e8d27b5-07d4-44ca-bae5-f2f4e57bf631")


def request(**kwargs: object) -> PublicSourceRequest:
    return PublicSourceRequest(
        url=SOURCE_URL,
        publisher="福州大学数学与统计学院",
        scope_year=2027,
        **kwargs,
    )


def parse_fixture(**kwargs: object):
    return parse_public_html(
        gzip.decompress(HTML.read_bytes()),
        content_type="text/html; charset=UTF-8",
        final_url=SOURCE_URL,
        request=request(**kwargs),
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
    assert result.content_type == "text/html"
    assert len(result.content_hash) == 64
    assert any("思想品德考核不合格者不予推荐和录取。" in f.quote for f in result.fragments)
    assert "secret_should_not_be_returned" not in result.normalized_text


def test_same_notice_has_stable_snapshot_identity():
    first = parse_fixture()
    second = parse_fixture()
    assert first.source_id == second.source_id
    assert first.snapshot_id == second.snapshot_id
    assert first.version_no == second.version_no == 1
    assert first.content_hash == second.content_hash


def test_url_fragment_does_not_change_source_identity():
    with_fragment = parse_public_html(
        gzip.decompress(HTML.read_bytes()),
        content_type="text/html",
        final_url=f"{SOURCE_URL}#section-1",
        request=request(),
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
    )
    assert changed.source_id == first.source_id
    assert changed.snapshot_id != first.snapshot_id
    assert changed.version_no == first.version_no == 1


def test_result_can_be_sent_to_citation_validator():
    result = parse_fixture()
    batch = build_official_citations(result.citation_batch())
    assert batch["scope_year"] == 2027
    assert len(batch["citations"]) == len(result.fragments)


def test_repeated_headings_get_distinct_locators():
    result = parse_public_html(
        gzip.decompress(HTML.read_bytes()),
        content_type="text/html",
        final_url=SOURCE_URL,
        request=request(),
    )
    sections = [
        fragment.locator_text for fragment in result.fragments if fragment.locator.kind == "section"
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
        )
    assert error.value.code == "unsupported_content_type"


def test_empty_content_is_rejected():
    with pytest.raises(SourceReadError) as error:
        parse_public_html(
            b"",
            content_type="text/html",
            final_url=SOURCE_URL,
            request=request(),
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
        read_public_html({"url": SOURCE_URL, "publisher": "x" * 161, "scope_year": 2027})
    assert error.value.code == "invalid_request"


def test_real_notice_uses_structured_list_and_table_locators():
    result = parse_fixture()
    assert any(fragment.locator.kind == "list_item" for fragment in result.fragments)
    assert any(fragment.locator.kind == "table_row" for fragment in result.fragments)


def test_cli_reports_missing_arguments_as_json(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["offerpilot-source-reader"])
    assert reader_main() == 2
    error = json.loads(capsys.readouterr().err)
    assert error["code"] == "invalid_request"
    assert "status" not in error


def test_cli_reports_unsafe_url_as_json(monkeypatch, capsys):
    monkeypatch.setattr(
        "sys.argv",
        [
            "offerpilot-source-reader",
            "http://127.0.0.1/notice",
            "--publisher",
            "福州大学",
            "--scope-year",
            "2027",
        ],
    )
    assert reader_main() == 1
    error = json.loads(capsys.readouterr().err)
    assert error["code"] == "unsafe_url"
    assert "status" not in error
