"""Read public HTML and preserve source evidence."""

from .integration import source_document_from_registration, source_registration_payload
from .reader import (
    PublicSourceRequest,
    PublicSourceResult,
    SourceReadError,
    parse_public_html,
    read_public_html,
)

__all__ = [
    "PublicSourceRequest",
    "PublicSourceResult",
    "SourceReadError",
    "parse_public_html",
    "read_public_html",
    "source_document_from_registration",
    "source_registration_payload",
]
