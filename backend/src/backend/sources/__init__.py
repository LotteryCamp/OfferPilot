"""Read public HTML or PDF and preserve source evidence."""

from .integration import source_document_from_registration, source_registration_payload
from .reader import (
    PublicSourceRequest,
    PublicSourceResult,
    SourceReadError,
    parse_public_html,
    parse_public_pdf,
    read_public_html,
    read_public_source,
)

__all__ = [
    "PublicSourceRequest",
    "PublicSourceResult",
    "SourceReadError",
    "parse_public_html",
    "parse_public_pdf",
    "read_public_html",
    "read_public_source",
    "source_document_from_registration",
    "source_registration_payload",
]
