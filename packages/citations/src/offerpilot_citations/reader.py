"""Read one public HTML source and produce versioned, reviewable evidence."""

from __future__ import annotations

import ipaddress
import re
import socket
import time
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
_MAX_FRAGMENT_COUNT = 4096
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
    publisher: AnnotatedText = Field(max_length=160)
    scope_year: Year
    title: Text | None = None
    matter_id: UUID | None = None
    timeout_seconds: float = Field(default=10.0, gt=0, le=30)
    max_bytes: int = Field(default=2 * 1024 * 1024, gt=0, le=8 * 1024 * 1024)
    max_fragments: int = Field(default=_MAX_FRAGMENT_COUNT, gt=0, le=100_000)


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
    publisher: AnnotatedText = Field(max_length=160)
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


def _validate_url(value: str, *, resolve: bool = True) -> str:
    try:
        url = TypeAdapter(WebUrl).validate_python(value)
    except ValidationError as error:
        raise SourceReadError("unsafe_url", "only public HTTP/HTTPS URLs are allowed") from error
    hostname = url.host
    if not hostname:
        raise SourceReadError("unsafe_url", "source URL must include a hostname")
    if resolve:
        try:
            addresses = {
                info[4][0]
                for info in socket.getaddrinfo(
                    hostname,
                    url.port or (443 if url.scheme == "https" else 80),
                    type=socket.SOCK_STREAM,
                )
            }
        except socket.gaierror as error:
            raise SourceReadError(
                "network_error", "source host could not be resolved", retryable=True
            ) from error
        if not addresses or any(
            not ipaddress.ip_address(address).is_global for address in addresses
        ):
            raise SourceReadError("unsafe_url", "source URL must resolve to a public address")
    return str(url)


class _PublicRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        _validate_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class _TooManyFragments(ValueError):
    """The page contains more text blocks than the reader can safely retain."""


class _HtmlBlock:
    def __init__(self, tag: str, depth: int, order: int) -> None:
        self.tag = tag
        self.depth = depth
        self.order = order
        self.parts: list[str] = []


class _HtmlBlocks(HTMLParser):
    def __init__(self, *, max_blocks: int = _MAX_FRAGMENT_COUNT) -> None:
        super().__init__(convert_charrefs=True)
        self._max_blocks = max_blocks
        self._completed: list[tuple[int, str, str]] = []
        self.title_parts: list[str] = []
        self.all_parts: list[str] = []
        self._blocked_depth = 0
        self._element_stack: list[str] = []
        self._block_stack: list[_HtmlBlock] = []
        self._block_order = 0
        self._in_title = False

    @property
    def blocks(self) -> list[tuple[str, str]]:
        return [(tag, text) for _, tag, text in sorted(self._completed, key=lambda item: item[0])]

    def _close_block(self) -> None:
        block = self._block_stack.pop()
        text = _normalize_text("".join(block.parts))
        if text:
            self._completed.append((block.order, block.tag, text))

    def _close_nested_blocks(self, depth: int) -> None:
        while self._block_stack and self._block_stack[-1].depth >= depth:
            self._close_block()

    def _start_block(self, tag: str) -> None:
        current_depth = len(self._element_stack)
        if tag == "p" and self._block_stack and self._block_stack[-1].tag == "p":
            self._close_block()
        elif (
            tag == "li"
            and self._block_stack
            and self._block_stack[-1].tag == "li"
            and self._block_stack[-1].depth == current_depth
        ):
            self._close_block()
        if self._block_order >= self._max_blocks:
            raise _TooManyFragments("HTML document contains too many text blocks")
        self._block_stack.append(_HtmlBlock(tag, current_depth, self._block_order))
        self._block_order += 1

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in _IGNORED_TAGS:
            self._blocked_depth += 1
            self._element_stack.append(tag)
            return
        if self._blocked_depth:
            self._element_stack.append(tag)
            return
        if tag == "br":
            if self._block_stack:
                self._block_stack[-1].parts.append("\n")
            return
        if tag == "title":
            self._in_title = True
        elif tag in _BLOCK_TAGS:
            self._start_block(tag)
        self._element_stack.append(tag)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "br" and self._blocked_depth == 0 and self._block_stack:
            self._block_stack[-1].parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in _IGNORED_TAGS:
            if self._blocked_depth:
                self._blocked_depth -= 1
            if tag in self._element_stack:
                index = len(self._element_stack) - 1 - self._element_stack[::-1].index(tag)
                del self._element_stack[index:]
            return
        if self._blocked_depth:
            if tag in self._element_stack:
                index = len(self._element_stack) - 1 - self._element_stack[::-1].index(tag)
                del self._element_stack[index:]
            return
        if tag not in self._element_stack:
            return
        index = len(self._element_stack) - 1 - self._element_stack[::-1].index(tag)
        self._close_nested_blocks(index)
        if tag == "title":
            self._in_title = False
        del self._element_stack[index:]

    def handle_data(self, data: str) -> None:
        if self._blocked_depth:
            return
        text = _normalize_text(data)
        if not text:
            return
        if self._in_title:
            self.title_parts.append(text)
            return
        if self._block_stack:
            self._block_stack[-1].parts.append(data)
        else:
            self.all_parts.append(text)


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


def _set_response_timeout(response, seconds: float) -> None:  # noqa: ANN001
    socket_object = getattr(getattr(getattr(response, "fp", None), "raw", None), "_sock", None)
    if socket_object is not None:
        socket_object.settimeout(max(seconds, 0.01))


def _read_body(response, max_bytes: int, deadline: float) -> bytes:  # noqa: ANN001
    length = response.headers.get("Content-Length")
    if length and length.isdigit() and int(length) > max_bytes:
        raise SourceReadError(
            "response_too_large", "HTML response exceeds the configured size limit"
        )
    chunks: list[bytes] = []
    total = 0
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise SourceReadError("network_error", "source read timed out", retryable=True)
        _set_response_timeout(response, remaining)
        try:
            chunk = response.read(min(64 * 1024, max_bytes - total + 1))
        except TimeoutError as error:
            raise SourceReadError(
                "network_error", "source read timed out", retryable=True
            ) from error
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
    headings: dict[str, int] = {}
    for tag, quote in blocks:
        if tag.startswith("h"):
            section_base = quote[:280]
            headings[section_base] = headings.get(section_base, 0) + 1
            occurrence = headings[section_base]
            section = section_base if occurrence == 1 else f"{section_base} [第{occurrence}处]"
            locator: Locator = {"kind": "section", "section": section}
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


def _request_model(request: PublicSourceRequest | dict[str, Any]) -> PublicSourceRequest:
    try:
        return PublicSourceRequest.model_validate(request)
    except ValidationError as error:
        url_error = any(
            item["loc"] == ("url",) and item["type"] != "missing"
            for item in error.errors(include_input=False, include_context=False, include_url=False)
        )
        code = "unsafe_url" if url_error else "invalid_request"
        raise SourceReadError(code, "source request does not match the contract") from error


def parse_public_html(
    body: bytes,
    *,
    content_type: str,
    final_url: str,
    request: PublicSourceRequest | dict[str, Any],
) -> PublicSourceResult:
    """Parse a verified public HTML response into a traceable source result."""
    request_model = _request_model(request)
    final_url = _validate_url(final_url, resolve=False)
    media_type = content_type.split(";", 1)[0].strip().lower()
    if media_type not in {"text/html", "application/xhtml+xml"}:
        raise SourceReadError("unsupported_content_type", "source is not an HTML document")
    if not body:
        raise SourceReadError("empty_content", "source returned an empty HTML document")
    html = _decode_html(body, content_type)
    parser = _HtmlBlocks(max_blocks=request_model.max_fragments)
    try:
        parser.feed(html)
        parser.close()
    except _TooManyFragments as error:
        raise SourceReadError(
            "too_many_fragments", "HTML document contains too many text blocks"
        ) from error
    except (ValueError, AssertionError) as error:
        raise SourceReadError("parse_error", "HTML document could not be parsed") from error

    blocks = parser.blocks
    fallback = _normalize_text(" ".join(parser.all_parts))
    if fallback:
        blocks.append(("body", fallback))
    if not blocks:
        raise SourceReadError("empty_content", "HTML document contains no readable text")

    normalized_text = "\n\n".join(quote for _, quote in blocks)
    fragments = _fragment_models(blocks)
    content_hash = sha256(body).hexdigest()
    source_id = uuid5(NAMESPACE_URL, final_url)
    snapshot_id = uuid5(NAMESPACE_URL, f"{final_url}#{content_hash}")
    fetched_at = datetime.now(UTC)
    title = request_model.title or _normalize_text(" ".join(parser.title_parts))
    if not title:
        title = next((quote for tag, quote in blocks if tag == "h1"), "未命名公开来源")
    return PublicSourceResult(
        status="success",
        matter_id=request_model.matter_id,
        origin="official_retrieval",
        source_id=source_id,
        snapshot_id=snapshot_id,
        version_no=1,
        url=final_url,
        title=title,
        publisher=request_model.publisher,
        scope_year=request_model.scope_year,
        fetched_at=fetched_at,
        content_type=media_type,
        content_hash=content_hash,
        normalized_text=normalized_text,
        fragments=fragments,
    )


def read_public_html(request: PublicSourceRequest | dict[str, Any]) -> PublicSourceResult:
    """Fetch one public HTML page and return normalized text plus traceable fragments."""
    request = _request_model(request)

    opener = urllib.request.build_opener(_PublicRedirectHandler)
    url = _validate_url(str(request.url))
    deadline = time.monotonic() + request.timeout_seconds
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
            final_url = _validate_url(response.geturl())
            body = _read_body(response, request.max_bytes, deadline)
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

    return parse_public_html(
        body,
        content_type=header_type,
        final_url=final_url,
        request=request,
    )
