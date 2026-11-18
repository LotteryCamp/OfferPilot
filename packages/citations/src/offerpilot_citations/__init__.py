"""Public API for OfferPilot source and citation processing."""

from .reader import (
    PublicSourceRequest,
    PublicSourceResult,
    SourceReadError,
    parse_public_html,
    read_public_html,
)
from .registry import SourceRegistrationError, SourceRegistry
from .service import (
    CitationIssue,
    CitationValidationError,
    build_fact_references,
    build_official_citations,
)

__all__ = [
    "CitationIssue",
    "CitationValidationError",
    "build_fact_references",
    "build_official_citations",
    "PublicSourceRequest",
    "PublicSourceResult",
    "SourceReadError",
    "parse_public_html",
    "read_public_html",
    "SourceRegistrationError",
    "SourceRegistry",
]
