"""Adapters bridging public HTML source reader (PR #37) and backend source records (PR #41)."""

from __future__ import annotations

import importlib
from collections.abc import Callable, Mapping
from typing import Any, Literal

from pydantic import BaseModel

from backend.agent.schemas import SourceDocument, SourceFragmentRecord

SourceStatus = Literal["active", "withdrawn", "invalid"]
AutoCheckStatus = Literal["pending", "passed", "failed", "conflict"]
RoiStatus = Literal["original", "reposted", "expired", "ambiguous"]


class SourceReadUnavailableError(RuntimeError):
    """Explicit failure raised when reading a public official source fails (A-03)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def source_document_from_public_result(result: BaseModel | Mapping[str, Any]) -> SourceDocument:
    """Convert PR #37 PublicSourceResult into an Agent SourceDocument."""
    data = result.model_dump(mode="python") if isinstance(result, BaseModel) else dict(result)
    snapshot_id = str(data["snapshot_id"])
    source_id = str(data["source_id"])

    fragments = [
        SourceFragmentRecord(
            locator_kind=frag["locator"]["kind"] if isinstance(frag.get("locator"), dict) else "section",
            locator=str(frag["locator_text"]),
            quote=str(frag["quote"]),
        )
        for frag in data.get("fragments", [])
    ]

    return SourceDocument(
        source_version_id=snapshot_id,
        source_id=source_id,
        snapshot_id=snapshot_id,
        version_no=int(data.get("version_no", 1)),
        title=str(data["title"]),
        publisher=str(data["publisher"]),
        url=str(data["url"]),
        year=int(data["scope_year"]),
        content=str(data["normalized_text"]),
        content_hash=str(data["content_hash"]) if data.get("content_hash") else None,
        fetched_at=data.get("fetched_at"),
        fragments=fragments,
    )


def source_document_from_backend_record(
    source_payload: Mapping[str, Any],
    snapshot_payload: Mapping[str, Any],
) -> SourceDocument:
    """Convert PR #41 backend source + snapshot JSON payloads into an Agent SourceDocument."""
    snapshot_id = str(snapshot_payload["id"])
    source_id = str(source_payload["id"])
    roi_status = _coerce_roi_status(source_payload.get("roi_status"))
    source_status = _coerce_source_status(source_payload.get("status"))
    auto_check_status = _coerce_check_status(source_payload.get("auto_check_status"))

    fragments = [
        SourceFragmentRecord(
            locator_kind=frag.get("locator_kind", "section"),
            locator=str(frag["locator"]),
            quote=str(frag["quote"]),
        )
        for frag in snapshot_payload.get("fragments", [])
        if frag.get("quote")
    ]

    return SourceDocument(
        source_version_id=snapshot_id,
        source_id=source_id,
        snapshot_id=snapshot_id,
        version_no=int(snapshot_payload.get("version_no", 1)),
        title=str(snapshot_payload["title"]),
        publisher=str(source_payload["publisher"]),
        url=str(source_payload["url"]) if source_payload.get("url") else None,
        year=int(source_payload["scope_year"]) if source_payload.get("scope_year") is not None else None,
        scope=str(source_payload["scope"]) if source_payload.get("scope") else None,
        published_date=snapshot_payload.get("published_date"),
        content=str(snapshot_payload["text"]),
        content_hash=str(snapshot_payload["content_hash"]) if snapshot_payload.get("content_hash") else None,
        fetched_at=snapshot_payload.get("fetched_at"),
        source_status=source_status,
        auto_check_status=auto_check_status,
        roi_status=roi_status,
        is_repost=(roi_status == "reposted"),
        is_expired=(roi_status == "expired" or source_status != "active"),
        fragments=fragments,
    )


def _coerce_source_status(value: object) -> SourceStatus:
    if value == "withdrawn":
        return "withdrawn"
    if value == "invalid":
        return "invalid"
    return "active"


def _coerce_check_status(value: object) -> AutoCheckStatus:
    if value == "passed":
        return "passed"
    if value == "failed":
        return "failed"
    if value == "conflict":
        return "conflict"
    return "pending"


def _coerce_roi_status(value: object) -> RoiStatus:
    if value == "reposted":
        return "reposted"
    if value == "expired":
        return "expired"
    if value == "ambiguous":
        return "ambiguous"
    return "original"


class PublicHtmlSourceReader:
    """SourceReaderPort implementation wrapping PR #37 read_public_html or preloaded docs."""

    def __init__(
        self,
        *,
        preloaded_sources: list[SourceDocument] | None = None,
        read_public_html_fn: Callable[[dict[str, Any]], Any] | None = None,
        default_publisher: str = "官方公开来源",
        default_scope_year: int = 2027,
    ) -> None:
        self._preloaded = list(preloaded_sources) if preloaded_sources is not None else None
        self._read_fn = read_public_html_fn
        self._default_publisher = default_publisher
        self._default_scope_year = default_scope_year

    def fetch_sources(
        self,
        urls: list[str],
        goal: str,
        *,
        scope_year: int | None = None,
    ) -> list[SourceDocument]:
        """Return preloaded sources or fetch each public URL via read_public_html_fn."""
        if self._preloaded is not None:
            return list(self._preloaded)

        if not urls:
            return []

        effective_year = scope_year if scope_year is not None else self._default_scope_year
        reader = self._resolve_reader()
        docs: list[SourceDocument] = []
        for url in urls:
            request = {
                "url": url,
                "publisher": self._default_publisher,
                "scope_year": effective_year,
            }
            try:
                raw_result = reader(request)
            except SourceReadUnavailableError:
                raise
            except Exception as exc:
                code = str(getattr(exc, "code", "source_read_failed"))
                raise SourceReadUnavailableError(code, f"来源读取失败 ({url}): {exc}") from exc
            docs.append(source_document_from_public_result(raw_result))
        return docs

    def _resolve_reader(self) -> Callable[[dict[str, Any]], Any]:
        if self._read_fn is not None:
            return self._read_fn
        try:
            module = importlib.import_module("backend.sources.reader")
        except ImportError as exc:
            raise SourceReadUnavailableError(
                "READER_UNAVAILABLE",
                "未找到 backend.sources.reader 来源读取模块，无法拉取在线页面",
            ) from exc
        return module.read_public_html
