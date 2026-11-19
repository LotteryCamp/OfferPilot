"""Read public HTML and preserve source evidence for Alpha."""

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
]
