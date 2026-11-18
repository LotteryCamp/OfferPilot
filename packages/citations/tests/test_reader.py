"""Integration tests for the public HTML reader using a local HTTP server."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import UUID

import pytest

from offerpilot_citations import PublicSourceRequest, SourceReadError, read_public_html
from offerpilot_citations.reader_cli import main as reader_main

ROOT = Path(__file__).resolve().parents[1]
OWNER_MATTER = UUID("3e8d27b5-07d4-44ca-bae5-f2f4e57bf631")


class _SourceHandler(BaseHTTPRequestHandler):
    body = b""
    content_type = "text/html; charset=utf-8"
    status = 200
    redirect_to = None

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", self.redirect_to or "/notice")
            self.end_headers()
            return
        if self.path == "/not-found":
            self.send_response(404)
            self.end_headers()
            return
        if self.path == "/empty":
            body = b"<html><body><script>private()</script></body></html>"
        elif self.path == "/non-html":
            body = b"%PDF-1.7"
        elif self.path == "/large":
            body = b"<p>" + (b"x" * 5000) + b"</p>"
        else:
            body = self.body
        self.send_response(self.status)
        content_type = "application/pdf" if self.path == "/non-html" else self.content_type
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


@pytest.fixture
def source_server():
    html = """<!doctype html>
    <html><head><title>推免工作方案</title><style>.hidden {}</style></head>
    <body><h1>福州大学推免工作方案</h1>
    <p>申请人应提交成绩单。</p>
    <p>思想品德考核不合格者不予推荐和录取。</p>
    <script>secret_should_not_be_returned()</script>
    <h2>材料要求</h2><ul><li>申请表</li><li>证明材料</li></ul></body></html>"""
    _SourceHandler.body = html.encode("utf-8")
    server = ThreadingHTTPServer(("127.0.0.1", 0), _SourceHandler)
    _SourceHandler.redirect_to = f"http://127.0.0.1:{server.server_port}/notice"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(timeout=2)


def request(url: str, **kwargs):
    return PublicSourceRequest(url=url, publisher="福州大学", scope_year=2027, **kwargs)


def test_reader_returns_stable_traceable_html(source_server):
    result = read_public_html(request(f"{source_server}/notice", matter_id=OWNER_MATTER))
    assert result.status == "success"
    assert result.matter_id == OWNER_MATTER
    assert str(result.url) == f"{source_server}/notice"
    assert result.title == "推免工作方案"
    assert result.publisher == "福州大学"
    assert result.scope_year == 2027
    assert result.content_type == "text/html"
    assert len(result.content_hash) == 64
    assert "申请人应提交成绩单。" in result.normalized_text
    assert "secret_should_not_be_returned" not in result.normalized_text
    assert [fragment.locator_text for fragment in result.fragments] == [
        "福州大学推免工作方案",
        "第1段，字符[0:10]",
        "第2段，字符[0:18]",
        "材料要求",
        "第3段，字符[0:3]",
        "第4段，字符[0:4]",
    ]
    assert result.fragments[1].quote == "申请人应提交成绩单。"
    assert result.fragments[2].quote == "思想品德考核不合格者不予推荐和录取。"
    batch = result.citation_batch()
    assert batch["snapshots"][0]["snapshot_id"] == str(result.snapshot_id)
    assert len(batch["citations"]) == len(result.fragments)


def test_reader_identifiers_are_stable_for_same_bytes(source_server):
    first = read_public_html(request(f"{source_server}/notice"))
    second = read_public_html(request(f"{source_server}/notice"))
    assert first.source_id == second.source_id
    assert first.snapshot_id == second.snapshot_id
    assert first.content_hash == second.content_hash


def test_reader_follows_public_redirect(source_server):
    result = read_public_html(request(f"{source_server}/redirect"))
    assert str(result.url).endswith("/notice")
    assert result.normalized_text.startswith("福州大学推免工作方案")


@pytest.mark.parametrize(
    ("path", "code"),
    [
        ("/empty", "empty_content"),
        ("/not-found", "http_error"),
        ("/non-html", "unsupported_content_type"),
    ],
)
def test_reader_reports_failure_without_success_result(source_server, path, code):
    with pytest.raises(SourceReadError) as error:
        read_public_html(request(f"{source_server}{path}"))
    assert error.value.code == code
    assert error.value.as_dict()["error"] == "source_read_failed"


def test_reader_enforces_response_size(source_server):
    with pytest.raises(SourceReadError) as error:
        read_public_html(request(f"{source_server}/large", max_bytes=100))
    assert error.value.code == "response_too_large"


@pytest.mark.parametrize(
    "url",
    [
        "file:///C:/private.html",
        "javascript:alert(1)",
        "https://user:secret@example.com/notice",
    ],
)
def test_reader_rejects_non_public_urls(url):
    with pytest.raises((SourceReadError, ValueError)):
        read_public_html(request(url))


def test_reader_rejects_missing_contract_fields():
    with pytest.raises(SourceReadError) as error:
        read_public_html({"url": "https://example.com/notice", "scope_year": 2027})
    assert error.value.code == "invalid_request"


def test_cli_success_and_json_output(source_server, monkeypatch, capsys):
    monkeypatch.setattr(
        "sys.argv",
        [
            "offerpilot-source-reader",
            f"{source_server}/notice",
            "--publisher",
            "福州大学",
            "--scope-year",
            "2027",
        ],
    )
    assert reader_main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "success"
    assert payload["fragments"]


def test_cli_failure_is_nonzero(source_server, monkeypatch, capsys):
    monkeypatch.setattr(
        "sys.argv",
        [
            "offerpilot-source-reader",
            f"{source_server}/empty",
            "--publisher",
            "福州大学",
            "--scope-year",
            "2027",
        ],
    )
    assert reader_main() == 1
    error = json.loads(capsys.readouterr().err)
    assert error["code"] == "empty_content"
    assert "status" not in error
