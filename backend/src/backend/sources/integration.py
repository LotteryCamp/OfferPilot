"""Adapt public source reads to the registration and citation contracts."""

from collections.abc import Mapping
from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, ValidationError

from .models import PositiveInt, Text, Timestamp, WebUrl, Year
from .reader import PublicSourceResult, SourceReadError


class _RegisteredFragment(BaseModel):
    locator_kind: Literal["section", "page", "text_span", "table_row"]
    locator: Text = Field(max_length=300)
    quote: Text


class _RegisteredSource(BaseModel):
    id: UUID
    url: WebUrl
    publisher: Text
    scope: str | None
    scope_year: Year
    status: Literal["active", "withdrawn", "invalid"]
    auto_check_status: Literal["pending", "passed", "failed", "conflict"]
    roi_status: Literal["original", "reposted", "expired", "ambiguous"]


class _RegisteredSnapshot(BaseModel):
    id: UUID
    source_id: UUID
    version_no: PositiveInt
    title: Text
    published_date: date | None
    text: Text
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    fetched_at: Timestamp
    fragments: list[_RegisteredFragment] = Field(min_length=1)


class _SourceRegistration(BaseModel):
    source: _RegisteredSource
    snapshot: _RegisteredSnapshot


def source_registration_payload(result: PublicSourceResult) -> dict[str, object]:
    """Prepare the body of the business API's matter-scoped source request."""
    return {
        "url": str(result.url),
        "publisher": result.publisher,
        "title": result.title[:500],
        "published_date": (
            result.published_date.isoformat() if result.published_date else None
        ),
        "scope": result.scope,
        "scope_year": result.scope_year,
        "content": result.normalized_text,
        "content_hash": result.content_hash,
        "fetched_at": result.fetched_at.isoformat(),
        "fragments": [
            {
                "locator_kind": fragment.locator.kind,
                "locator": fragment.locator_text,
                "quote": fragment.quote,
            }
            for fragment in result.fragments
        ],
    }


def source_document_from_registration(
    response: Mapping[str, object],
) -> dict[str, object]:
    """Use the stored identity, version, and evidence in an Agent source document."""
    try:
        registration = _SourceRegistration.model_validate(response)
    except ValidationError as error:
        raise SourceReadError(
            "invalid_registration", "saved source response lacks citation data"
        ) from error
    source = registration.source
    snapshot = registration.snapshot
    if snapshot.source_id != source.id:
        raise SourceReadError(
            "invalid_registration", "saved snapshot belongs to a different source"
        )

    return {
        "source_version_id": str(snapshot.id),
        "source_id": str(source.id),
        "snapshot_id": str(snapshot.id),
        "version_no": snapshot.version_no,
        "title": snapshot.title,
        "publisher": source.publisher,
        "url": str(source.url),
        "year": source.scope_year,
        "scope": source.scope,
        "published_date": (
            snapshot.published_date.isoformat() if snapshot.published_date else None
        ),
        "content": snapshot.text,
        "content_hash": snapshot.content_hash,
        "fetched_at": snapshot.fetched_at.isoformat(),
        "source_status": source.status,
        "auto_check_status": source.auto_check_status,
        "roi_status": source.roi_status,
        "is_repost": source.roi_status == "reposted",
        "is_expired": source.roi_status == "expired",
        "fragments": [
            fragment.model_dump(mode="json") for fragment in snapshot.fragments
        ],
    }
