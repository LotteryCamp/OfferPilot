"""Read a public HTML or PDF source and produce versioned evidence."""

from __future__ import annotations

import http.client
import ipaddress
import re
import socket
import ssl
import time
import urllib.parse
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from datetime import UTC, date, datetime
from hashlib import sha256
from html.parser import HTMLParser
from io import BytesIO
from threading import BoundedSemaphore
from typing import Any, Literal
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import Field, HttpUrl, TypeAdapter, ValidationError
from pypdf import PdfReader
from pypdf.errors import PyPdfError

from .models import (
    Contract,
    Locator,
    PageLocator,
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
_CHARSET_RE = re.compile(rb"charset\s*=\s*[\"']?([A-Za-z0-9._-]+)", re.IGNORECASE)
_PUBLICATION_DATE_RE = re.compile(
    r"^(?:发布日期|发布时间)\s*[:：]\s*(\d{4}-\d{2}-\d{2})(?=\s|$)"
)
_MAX_FRAGMENT_COUNT = 4096
_MAX_PDF_BYTES = 4 * 1024 * 1024
_MAX_PDF_PAGES = 50
_MAX_PDF_TEXT_CHARS = 250_000
_HTML_TYPES = frozenset({"text/html", "application/xhtml+xml"})
_PDF_TYPES = frozenset({"application/pdf", "application/octet-stream"})
_DNS_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="offerpilot-dns")
_DNS_SLOTS = BoundedSemaphore(4)
AnnotatedText = Text
type AddressInfo = tuple[int, int, int, str, tuple[Any, ...]]


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
    scope: Text | None = Field(default=None, max_length=200)
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
    url: WebUrl
    title: Text
    publisher: AnnotatedText = Field(max_length=160)
    scope_year: Year
    scope: Text | None = None
    published_date: date | None = None
    fetched_at: Timestamp
    content_type: Literal["text/html", "application/xhtml+xml", "application/pdf"]
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    normalized_text: Text
    fragments: list[SourceFragment] = Field(min_length=1)


def _validated_url(value: str) -> HttpUrl:
    try:
        return TypeAdapter(WebUrl).validate_python(value)
    except ValidationError as error:
        raise SourceReadError(
            "unsafe_url", "only public HTTP/HTTPS URLs are allowed"
        ) from error


def _canonical_url(value: str) -> tuple[str, HttpUrl]:
    url = _validated_url(value)
    parts = urllib.parse.urlsplit(str(url))
    canonical = urllib.parse.urlunsplit(
        (parts.scheme, parts.netloc, parts.path, parts.query, "")
    )
    canonical_url = _validated_url(canonical)
    return str(canonical_url), canonical_url


def _resolve_public_url(
    value: str, *, deadline: float | None = None
) -> tuple[str, HttpUrl, Sequence[AddressInfo]]:
    canonical_url, url = _canonical_url(value)
    hostname = url.host
    if not hostname:
        raise SourceReadError("unsafe_url", "source URL must include a hostname")
    if deadline is not None and time.monotonic() >= deadline:
        raise SourceReadError(
            "network_error", "source request timed out", retryable=True
        )
    remaining = None if deadline is None else max(deadline - time.monotonic(), 0)
    if not _DNS_SLOTS.acquire(timeout=remaining):
        raise SourceReadError(
            "network_error", "source request timed out", retryable=True
        )
    try:
        resolver = _DNS_EXECUTOR.submit(
            socket.getaddrinfo,
            hostname,
            url.port or (443 if url.scheme == "https" else 80),
            0,
            socket.SOCK_STREAM,
        )
    except Exception:
        _DNS_SLOTS.release()
        raise
    resolver.add_done_callback(lambda _: _DNS_SLOTS.release())
    try:
        addresses = resolver.result(timeout=remaining)
    except FuturesTimeoutError as error:
        resolver.cancel()
        raise SourceReadError(
            "network_error", "source request timed out", retryable=True
        ) from error
    except socket.gaierror as error:
        raise SourceReadError(
            "network_error", "source host could not be resolved", retryable=True
        ) from error
    if deadline is not None and time.monotonic() >= deadline:
        raise SourceReadError(
            "network_error", "source request timed out", retryable=True
        )
    if not addresses or any(
        not ipaddress.ip_address(info[4][0]).is_global for info in addresses
    ):
        raise SourceReadError(
            "unsafe_url", "source URL must resolve to a public address"
        )
    return canonical_url, url, addresses


def _connect_public(
    url: HttpUrl,
    addresses: Sequence[AddressInfo],
    deadline: float,
) -> http.client.HTTPConnection:
    hostname = url.host
    if hostname is None:
        raise SourceReadError("unsafe_url", "source URL must include a hostname")
    port = url.port or (443 if url.scheme == "https" else 80)
    last_error: OSError | None = None
    for family, socktype, protocol, _, address in addresses:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise SourceReadError(
                "network_error", "source request timed out", retryable=True
            )
        raw_socket = socket.socket(family, socktype, protocol)
        try:
            raw_socket.settimeout(remaining)
            raw_socket.connect(address)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise SourceReadError(
                    "network_error", "source request timed out", retryable=True
                )
            raw_socket.settimeout(remaining)
            if url.scheme == "https":
                context = ssl.create_default_context()
                context.minimum_version = ssl.TLSVersion.TLSv1_2
                raw_socket = context.wrap_socket(raw_socket, server_hostname=hostname)
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise SourceReadError(
                        "network_error", "source request timed out", retryable=True
                    )
                raw_socket.settimeout(remaining)
            connection = http.client.HTTPConnection(hostname, port, timeout=remaining)
            connection.sock = raw_socket
            return connection
        except SourceReadError:
            raw_socket.close()
            raise
        except (OSError, ssl.SSLError) as error:
            last_error = error
            raw_socket.close()
    if last_error is not None:
        raise last_error
    raise OSError("source host has no usable public address")


def _refresh_connection_timeout(
    connection: http.client.HTTPConnection, deadline: float
) -> None:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise SourceReadError(
            "network_error", "source request timed out", retryable=True
        )
    if connection.sock is not None:
        connection.sock.settimeout(remaining)


def _open_public_response(
    initial_url: str, deadline: float
) -> tuple[http.client.HTTPConnection, http.client.HTTPResponse, str]:
    current_url = initial_url
    for redirect_count in range(6):
        canonical_url, parsed_url, addresses = _resolve_public_url(
            current_url, deadline=deadline
        )
        connection = _connect_public(parsed_url, addresses, deadline)
        path = parsed_url.path or "/"
        if parsed_url.query:
            path = f"{path}?{parsed_url.query}"
        host_header = urllib.parse.urlsplit(canonical_url).netloc
        try:
            _refresh_connection_timeout(connection, deadline)
            connection.request(
                "GET",
                path,
                headers={
                    "Accept": "text/html,application/xhtml+xml,application/pdf",
                    "Host": host_header,
                    "User-Agent": "OfferPilot/0.1",
                },
            )
            _refresh_connection_timeout(connection, deadline)
            response = connection.getresponse()
        except http.client.IncompleteRead as error:
            connection.close()
            raise SourceReadError(
                "incomplete_response",
                "source returned an incomplete HTTP response",
                retryable=True,
            ) from error
        except (http.client.HTTPException, OSError, TimeoutError) as error:
            connection.close()
            raise SourceReadError(
                "network_error", "source could not be reached", retryable=True
            ) from error

        if response.status not in {301, 302, 303, 307, 308}:
            return connection, response, canonical_url
        location = response.getheader("Location")
        response.close()
        connection.close()
        if not location:
            raise SourceReadError(
                "http_error", "redirect response did not include a location"
            )
        if redirect_count == 5:
            raise SourceReadError("http_error", "source exceeded the redirect limit")
        current_url = urllib.parse.urljoin(canonical_url, location)
    raise SourceReadError("http_error", "source exceeded the redirect limit")


class _TooManyFragments(ValueError):
    """The page contains more text blocks than the reader can safely retain."""


class _HtmlBlock:
    def __init__(self, tag: str, depth: int) -> None:
        self.tag = tag
        self.depth = depth
        self.parts: list[str] = []


class _HtmlBlocks(HTMLParser):
    def __init__(self, *, max_blocks: int = _MAX_FRAGMENT_COUNT) -> None:
        super().__init__(convert_charrefs=True)
        self._max_blocks = max_blocks
        self._completed: list[tuple[int, str, str]] = []
        self.title_parts: list[str] = []
        self._blocked_depth = 0
        self._element_stack: list[str] = []
        self._block_stack: list[_HtmlBlock] = []
        self._next_order = 0
        self._table_row_number = 0
        self._in_title = False

    @property
    def blocks(self) -> list[tuple[str, str]]:
        return [
            (tag, text)
            for _, tag, text in sorted(self._completed, key=lambda item: item[0])
        ]

    def _close_block(self) -> None:
        block = self._block_stack.pop()
        self._flush_block_segment(block)

    def _flush_block_segment(self, block: _HtmlBlock) -> None:
        text = _normalize_text("".join(block.parts))
        if text:
            self._append_item(self._next_order, block.tag, text)
            self._next_order += 1
            block.parts.clear()

    def _append_item(self, order: int, tag: str, text: str) -> None:
        if tag == "body" and self._completed and self._completed[-1][1] == "body":
            previous_order, _, previous_text = self._completed[-1]
            self._completed[-1] = (previous_order, "body", f"{previous_text} {text}")
            return
        if len(self._completed) >= self._max_blocks:
            raise _TooManyFragments("HTML document contains too many text blocks")
        self._completed.append((order, tag, text))

    def _close_nested_blocks(self, depth: int) -> None:
        while self._block_stack and self._block_stack[-1].depth >= depth:
            self._close_block()

    def _start_block(self, tag: str) -> None:
        current_depth = len(self._element_stack)
        while self._block_stack and self._block_stack[-1].depth >= current_depth:
            self._close_block()
        if self._block_stack:
            self._flush_block_segment(self._block_stack[-1])
        if any(item in {"td", "th"} for item in self._element_stack):
            block_tag = f"td:{self._table_row_number}"
        else:
            block_tag = tag
        self._block_stack.append(_HtmlBlock(block_tag, current_depth))

    def _element_index(self, tag: str) -> int | None:
        for index in range(len(self._element_stack) - 1, -1, -1):
            if self._element_stack[index] == tag:
                return index
        return None

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
        if tag in {"td", "th"}:
            self._element_stack.append(tag)
            return
        if tag == "tr":
            self._table_row_number += 1
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
            index = self._element_index(tag)
            if index is not None:
                del self._element_stack[index:]
            return
        if self._blocked_depth:
            index = self._element_index(tag)
            if index is not None:
                del self._element_stack[index:]
            return
        index = self._element_index(tag)
        if index is None:
            return
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
        elif any(item in {"td", "th"} for item in self._element_stack):
            self._append_item(self._next_order, f"td:{self._table_row_number}", text)
            self._next_order += 1
        else:
            self._append_item(self._next_order, "body", text)
            self._next_order += 1

    def finish(self) -> None:
        while self._block_stack:
            self._close_block()


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _decode_html(body: bytes, content_type: str | None) -> str:
    charset = None
    if content_type and "charset=" in content_type.lower():
        charset = (
            content_type.lower().split("charset=", 1)[1].split(";", 1)[0].strip(" \"'")
        )
    if charset is None:
        match = _CHARSET_RE.search(body[:8192])
        if match:
            charset = match.group(1).decode("ascii", errors="ignore")
    for encoding in dict.fromkeys([charset, "utf-8", "gb18030"]):
        if not encoding:
            continue
        try:
            return body.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
    raise SourceReadError("decode_error", "HTML encoding could not be decoded")


def _set_response_timeout(response: http.client.HTTPResponse, seconds: float) -> None:
    socket_object = getattr(
        getattr(getattr(response, "fp", None), "raw", None), "_sock", None
    )
    if socket_object is not None:
        socket_object.settimeout(max(seconds, 0.01))


def _read_body(
    response: http.client.HTTPResponse, max_bytes: int, deadline: float
) -> bytes:
    length = response.headers.get("Content-Length")
    if length and length.isdigit() and int(length) > max_bytes:
        raise SourceReadError(
            "response_too_large", "source response exceeds the configured size limit"
        )
    chunks: list[bytes] = []
    total = 0
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise SourceReadError(
                "network_error", "source read timed out", retryable=True
            )
        _set_response_timeout(response, remaining)
        try:
            chunk = response.read(min(64 * 1024, max_bytes - total + 1))
        except http.client.IncompleteRead as error:
            raise SourceReadError(
                "incomplete_response",
                "source returned an incomplete HTTP response",
                retryable=True,
            ) from error
        except (http.client.HTTPException, OSError, TimeoutError) as error:
            raise SourceReadError(
                "network_error", "source response could not be read", retryable=True
            ) from error
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise SourceReadError(
                "response_too_large",
                "source response exceeds the configured size limit",
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _fragment_models(blocks: list[tuple[str, str]]) -> list[SourceFragment]:
    fragments = []
    paragraph = 0
    headings: dict[str, int] = {}
    table_row = 0
    grouped_blocks: list[tuple[str, str]] = []
    for tag, quote in blocks:
        if tag.startswith("td:") and grouped_blocks and grouped_blocks[-1][0] == tag:
            previous_tag, previous_quote = grouped_blocks[-1]
            grouped_blocks[-1] = (previous_tag, f"{previous_quote} {quote}")
        else:
            grouped_blocks.append((tag, quote))
    for tag, quote in grouped_blocks:
        if tag.startswith("h"):
            section_base = quote[:280]
            headings[section_base] = headings.get(section_base, 0) + 1
            occurrence = headings[section_base]
            section = (
                section_base
                if occurrence == 1
                else f"{section_base} [第{occurrence}处]"
            )
            locator = {"kind": "section", "section": section}
        elif tag.startswith("td:"):
            row = int(tag.partition(":")[2])
            if row <= 0:
                table_row += 1
                row = table_row
            else:
                table_row = max(table_row, row)
            locator = {"kind": "table_row", "table": "网页表格", "row": row}
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


def _publication_date(blocks: list[tuple[str, str]]) -> date | None:
    for _, quote in blocks:
        match = _PUBLICATION_DATE_RE.match(quote)
        if match:
            try:
                return date.fromisoformat(match[1])
            except ValueError:
                continue
    return None


def _request_model(
    request: PublicSourceRequest | dict[str, Any],
) -> PublicSourceRequest:
    try:
        return PublicSourceRequest.model_validate(request)
    except ValidationError as error:
        url_error = any(
            item["loc"] == ("url",) and item["type"] != "missing"
            for item in error.errors(
                include_input=False, include_context=False, include_url=False
            )
        )
        code = "unsafe_url" if url_error else "invalid_request"
        raise SourceReadError(
            code, "source request does not match the contract"
        ) from error


def parse_public_html(
    body: bytes,
    *,
    content_type: str,
    final_url: str,
    request: PublicSourceRequest | dict[str, Any],
    fetched_at: datetime,
) -> PublicSourceResult:
    """Parse a verified public HTML response into a traceable source result."""
    request_model = _request_model(request)
    final_url, _ = _canonical_url(final_url)
    media_type = content_type.split(";", 1)[0].strip().lower()
    if media_type not in {"text/html", "application/xhtml+xml"}:
        raise SourceReadError(
            "unsupported_content_type", "source is not an HTML document"
        )
    if not body:
        raise SourceReadError("empty_content", "source returned an empty HTML document")
    html = _decode_html(body, content_type)
    parser = _HtmlBlocks(max_blocks=request_model.max_fragments)
    try:
        parser.feed(html)
        parser.close()
        parser.finish()
    except _TooManyFragments as error:
        raise SourceReadError(
            "too_many_fragments", "HTML document contains too many text blocks"
        ) from error
    except (ValueError, AssertionError) as error:
        raise SourceReadError(
            "parse_error", "HTML document could not be parsed"
        ) from error

    blocks = parser.blocks
    if not blocks:
        raise SourceReadError(
            "empty_content", "HTML document contains no readable text"
        )

    fragments = _fragment_models(blocks)
    normalized_text = "\n\n".join(fragment.quote for fragment in fragments)
    content_hash = sha256(body).hexdigest()
    source_id = uuid5(NAMESPACE_URL, final_url)
    snapshot_id = uuid5(NAMESPACE_URL, f"{final_url}#{content_hash}")
    title = request_model.title or _normalize_text(" ".join(parser.title_parts))
    if not title:
        title = next((quote for tag, quote in blocks if tag == "h1"), "未命名公开来源")
    return PublicSourceResult(
        status="success",
        matter_id=request_model.matter_id,
        origin="official_retrieval",
        source_id=source_id,
        snapshot_id=snapshot_id,
        url=final_url,
        title=title,
        publisher=request_model.publisher,
        scope_year=request_model.scope_year,
        scope=request_model.scope,
        published_date=_publication_date(blocks),
        fetched_at=fetched_at,
        content_type=media_type,
        content_hash=content_hash,
        normalized_text=normalized_text,
        fragments=fragments,
    )


def read_public_html(
    request: PublicSourceRequest | dict[str, Any],
) -> PublicSourceResult:
    """Fetch one public HTML page and return normalized text plus traceable fragments."""
    return _read_public_source(request, allow_pdf=False)


def read_public_source(
    request: PublicSourceRequest | dict[str, Any],
) -> PublicSourceResult:
    """Fetch a public HTML page or PDF through the existing public URL reader."""
    return _read_public_source(request, allow_pdf=True)


def _read_public_source(
    request: PublicSourceRequest | dict[str, Any], *, allow_pdf: bool
) -> PublicSourceResult:
    request = _request_model(request)
    deadline = time.monotonic() + request.timeout_seconds
    connection = None
    response = None
    try:
        connection, response, final_url = _open_public_response(
            str(request.url), deadline
        )
        if response.status >= 400:
            raise SourceReadError(
                "http_error",
                f"source returned HTTP {response.status}",
                retryable=response.status >= 500,
            )
        header_type = response.headers.get("Content-Type", "")
        media_type = response.headers.get_content_type()
        is_pdf_type = allow_pdf and media_type in _PDF_TYPES
        if media_type not in _HTML_TYPES and not is_pdf_type:
            raise SourceReadError(
                "unsupported_content_type", "source is not a supported document"
            )
        # Official attachment endpoints can serve PDFs as generic downloads.
        max_bytes = request.max_bytes
        if is_pdf_type:
            max_bytes = _pdf_byte_limit(request)
        body = _read_body(response, max_bytes, deadline)
    except SourceReadError:
        raise
    except (http.client.HTTPException, OSError, TimeoutError) as error:
        raise SourceReadError(
            "network_error", "source could not be reached", retryable=True
        ) from error
    finally:
        if response is not None:
            response.close()
        if connection is not None:
            connection.close()

    if media_type == "application/pdf" or (is_pdf_type and body.startswith(b"%PDF-")):
        return parse_public_pdf(
            body, final_url=final_url, request=request, fetched_at=datetime.now(UTC)
        )
    return parse_public_html(
        body,
        content_type=header_type,
        final_url=final_url,
        request=request,
        fetched_at=datetime.now(UTC),
    )


def _pdf_byte_limit(request: PublicSourceRequest) -> int:
    if "max_bytes" in request.model_fields_set:
        return min(request.max_bytes, _MAX_PDF_BYTES)
    return _MAX_PDF_BYTES


def parse_public_pdf(
    body: bytes,
    *,
    final_url: str,
    request: PublicSourceRequest | dict[str, Any],
    fetched_at: datetime,
) -> PublicSourceResult:
    """Extract page citations from a verified public PDF response."""
    request = _request_model(request)
    if len(body) > _pdf_byte_limit(request):
        raise SourceReadError(
            "response_too_large", "PDF response exceeds the configured size limit"
        )
    if not body.startswith(b"%PDF-"):
        raise SourceReadError("pdf_parse_error", "source has an invalid PDF header")

    fragments: list[SourceFragment] = []
    text_chars = 0
    try:
        with BytesIO(body) as pdf_file:
            pdf = PdfReader(pdf_file, strict=True)
            if pdf.is_encrypted:
                raise SourceReadError("pdf_encrypted", "PDF is encrypted")
            if len(pdf.pages) > _MAX_PDF_PAGES:
                raise SourceReadError("pdf_page_limit", "PDF exceeds the page limit")
            for page_number, page in enumerate(pdf.pages, start=1):
                quote = _normalize_text(page.extract_text())
                if not quote:
                    continue
                text_chars += len(quote)
                if (
                    text_chars > _MAX_PDF_TEXT_CHARS
                    or len(fragments) >= request.max_fragments
                ):
                    raise SourceReadError(
                        "too_many_fragments", "PDF exceeds the extracted text limit"
                    )
                locator = PageLocator(kind="page", page=page_number)
                fragments.append(
                    SourceFragment(
                        locator=locator, locator_text=locator_text(locator), quote=quote
                    )
                )
            metadata = pdf.metadata
            title = request.title or _normalize_text(
                (metadata.title or "") if metadata else ""
            )
    except SourceReadError:
        raise
    except (PyPdfError, ValueError, RecursionError) as error:
        raise SourceReadError(
            "pdf_parse_error", "PDF text extraction failed"
        ) from error
    if not fragments:
        raise SourceReadError("pdf_no_text", "PDF has no extractable text")

    final_url, _ = _canonical_url(final_url)
    content_hash = sha256(body).hexdigest()
    return PublicSourceResult(
        status="success",
        matter_id=request.matter_id,
        origin="official_retrieval",
        source_id=uuid5(NAMESPACE_URL, final_url),
        snapshot_id=uuid5(NAMESPACE_URL, f"{final_url}#{content_hash}"),
        url=final_url,
        title=title or "公开 PDF 附件",
        publisher=request.publisher,
        scope_year=request.scope_year,
        scope=request.scope,
        fetched_at=fetched_at,
        content_type="application/pdf",
        content_hash=content_hash,
        normalized_text="\n\n".join(fragment.quote for fragment in fragments),
        fragments=fragments,
    )
