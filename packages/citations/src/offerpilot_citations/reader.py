"""Read one public HTML source and produce versioned, reviewable evidence."""

from __future__ import annotations

import re
import urllib.error
import urllib.request
from datetime import UTC, datetime
from hashlib import sha256
from html.parser import HTMLParser
from typing import Any, Literal
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import Field, TypeAdapter, ValidationError

from .models import (
    Contract,
    Locator,
    PositiveInt,
    Text,
    Timestamp,
    WebUrl,
    Year,
    locator_text,
)

_BLOCK_TAGS = frozenset(
    {
        "address",
        "blockquote",
        "caption",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "li",
        "p",
        "pre",
        "td",
        "th",
    }
)
_IGNORED_TAGS = frozenset({"script", "style", "noscript", "template", "svg"})
_CHARSET_RE = re.compile(rb"charset\s*=\s*[\"']?([A-Za-z0-9._-]+)", re.I)
AnnotatedText = Text


class SourceReadError(ValueError):
    """A safe, structured failure that never includes response bodies or secrets."""

    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        self.code = code
        self.message = message
        self.retryable = retryable
        super().__init__(message)

    def as_dict(self) -> dict[str, object]:
        return {
            "error": "source_read_failed",
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
        }


class PublicSourceRequest(Contract):
    """Request accepted from the trusted source/agent adapter."""

    url: WebUrl
    publisher: AnnotatedText
    scope_year: Year
    title: Text | None = None
    matter_id: UUID | None = None
    timeout_seconds: float = Field(default=10.0, gt=0, le=30)
    max_bytes: int = Field(default=2 * 1024 * 1024, gt=0, le=8 * 1024 * 1024)


class SourceFragment(Contract):
    locator: Locator
    locator_text: Text
    quote: Text


class PublicSourceResult(Contract):
    status: Literal["success"]
    matter_id: UUID | None = None
    origin: Literal["official_retrieval"]
    source_id: UUID
    snapshot_id: UUID
    version_no: PositiveInt
    url: WebUrl
    title: Text
    publisher: AnnotatedText
    scope_year: Year
    fetched_at: Timestamp
    content_type: Literal["text/html", "application/xhtml+xml"]
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    normalized_text: Text
    fragments: list[SourceFragment] = Field(min_length=1)

    def citation_batch(self) -> dict[str, Any]:
        """Adapt the result to the citation normalizer without copying page text."""
        snapshot = {
            "origin": self.origin,
            "source_id": str(self.source_id),
            "snapshot_id": str(self.snapshot_id),
            "version_no": self.version_no,
            "url": str(self.url),
            "title": self.title,
            "publisher": self.publisher,
            "scope_year": self.scope_year,
            "fetched_at": self.fetched_at.isoformat(),
        }
        citations = [
            {
                "kind": "official",
                "source_id": str(self.source_id),
                "snapshot_id": str(self.snapshot_id),
                "fetched_at": self.fetched_at.isoformat(),
                "locator": fragment.locator.model_dump(mode="json"),
                "quote": fragment.quote,
            }
            for fragment in self.fragments
        ]
        return {"scope_year": self.scope_year, "snapshots": [snapshot], "citations": citations}


def _validate_url(value: str) -> str:
    try:
        return str(TypeAdapter(WebUrl).validate_python(value))
    except ValidationError as error:
        raise SourceReadError("unsafe_url", "only public HTTP/HTTPS URLs are allowed") from error


class _PublicRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        _validate_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class _HtmlBlocks(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[tuple[str, str]] = []
        self.title_parts: list[str] = []
        self.all_parts: list[str] = []
        self._blocked_depth = 0
        self._current_tag: str | None = None
        self._current_parts: list[str] = []
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in _IGNORED_TAGS:
            self._blocked_depth += 1
        elif tag == "title" and self._blocked_depth == 0:
            self._in_title = True
        elif tag in _BLOCK_TAGS and self._blocked_depth == 0 and self._current_tag is None:
            self._current_tag = tag
            self._current_parts = []

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "br" and self._current_tag is not None:
            self._current_parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in _IGNORED_TAGS and self._blocked_depth:
            self._blocked_depth -= 1
        elif tag == "title":
            self._in_title = False
        elif tag == self._current_tag:
            text = _normalize_text("".join(self._current_parts))
            if text:
                self.blocks.append((tag, text))
            self._current_tag = None
            self._current_parts = []

    def handle_data(self, data: str) -> None:
        if self._blocked_depth:
            return
        text = _normalize_text(data)
        if not text:
            return
        self.all_parts.append(text)
        if self._in_title:
            self.title_parts.append(text)
        if self._current_tag is not None:
            self._current_parts.append(data)


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _decode_html(body: bytes, content_type: str | None) -> str:
    charset = None
    if content_type and "charset=" in content_type.lower():
        charset = content_type.lower().split("charset=", 1)[1].split(";", 1)[0].strip(" \"'")
    if charset is None:
        match = _CHARSET_RE.search(body[:8192])
        if match:
            charset = match.group(1).decode("ascii", errors="ignore")
    for encoding in dict.fromkeys([charset, "utf-8", "gb18030"]):
        if not encoding:
            continue
        try:
            return body.decode(encoding)
        except LookupError, UnicodeDecodeError:
            continue
    raise SourceReadError("decode_error", "HTML encoding could not be decoded")


def _read_body(response, max_bytes: int) -> bytes:  # noqa: ANN001
    length = response.headers.get("Content-Length")
    if length and length.isdigit() and int(length) > max_bytes:
        raise SourceReadError(
            "response_too_large", "HTML response exceeds the configured size limit"
        )
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = response.read(min(64 * 1024, max_bytes - total + 1))
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise SourceReadError(
                "response_too_large", "HTML response exceeds the configured size limit"
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _fragment_models(blocks: list[tuple[str, str]]) -> list[SourceFragment]:
    fragments = []
    paragraph = 0
    for tag, quote in blocks:
        if tag.startswith("h"):
            locator: Locator = {"kind": "section", "section": quote[:300]}
        else:
            paragraph += 1
            locator = {
                "kind": "text_span",
                "paragraph": paragraph,
                "start": 0,
                "end": len(quote),
            }
        fragment = SourceFragment.model_validate(
            {"locator": locator, "locator_text": "pending", "quote": quote}
        )
        fragments.append(
            fragment.model_copy(update={"locator_text": locator_text(fragment.locator)})
        )
    return fragments


def read_public_html(request: PublicSourceRequest | dict[str, Any]) -> PublicSourceResult:
    """Fetch one public HTML page and return normalized text plus traceable fragments."""
    try:
        request = PublicSourceRequest.model_validate(request)
    except ValidationError as error:
        raise SourceReadError(
            "invalid_request", "source request does not match the contract"
        ) from error

    opener = urllib.request.build_opener(_PublicRedirectHandler)
    url = str(request.url)
    http_request = urllib.request.Request(
        url,
        headers={"Accept": "text/html,application/xhtml+xml", "User-Agent": "OfferPilot/0.1"},
        method="GET",
    )
    try:
        with opener.open(http_request, timeout=request.timeout_seconds) as response:
            status = response.getcode()
            if status is not None and status >= 400:
                raise SourceReadError(
                    "http_error", f"source returned HTTP {status}", retryable=status >= 500
                )
            content_type = response.headers.get_content_type()
            if content_type not in {"text/html", "application/xhtml+xml"}:
                raise SourceReadError("unsupported_content_type", "source is not an HTML document")
            body = _read_body(response, request.max_bytes)
            final_url = _validate_url(response.geturl())
            header_type = response.headers.get("Content-Type")
    except SourceReadError:
        raise
    except urllib.error.HTTPError as error:
        raise SourceReadError(
            "http_error", f"source returned HTTP {error.code}", retryable=error.code >= 500
        ) from error
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise SourceReadError(
            "network_error", "source could not be reached", retryable=True
        ) from error

    if not body:
        raise SourceReadError("empty_content", "source returned an empty HTML document")
    html = _decode_html(body, header_type)
    parser = _HtmlBlocks()
    try:
        parser.feed(html)
        parser.close()
    except (ValueError, AssertionError) as error:
        raise SourceReadError("parse_error", "HTML document could not be parsed") from error

    blocks = parser.blocks
    if not blocks:
        fallback = _normalize_text(" ".join(parser.all_parts))
        if fallback:
            blocks = [("body", fallback)]
    if not blocks:
        raise SourceReadError("empty_content", "HTML document contains no readable text")

    normalized_text = "\n\n".join(quote for _, quote in blocks)
    fragments = _fragment_models(blocks)
    fetched_at = datetime.now(UTC)
    content_hash = sha256(body).hexdigest()
    source_id = uuid5(NAMESPACE_URL, final_url)
    snapshot_id = uuid5(NAMESPACE_URL, f"{final_url}#{content_hash}")
    title = request.title or _normalize_text(" ".join(parser.title_parts))
    if not title:
        title = next((quote for tag, quote in blocks if tag == "h1"), "未命名公开来源")
    return PublicSourceResult(
        status="success",
        matter_id=request.matter_id,
        origin="official_retrieval",
        source_id=source_id,
        snapshot_id=snapshot_id,
        version_no=1,
        url=final_url,
        title=title,
        publisher=request.publisher,
        scope_year=request.scope_year,
        fetched_at=fetched_at,
        content_type=content_type,
        content_hash=content_hash,
        normalized_text=normalized_text,
        fragments=fragments,
    )
