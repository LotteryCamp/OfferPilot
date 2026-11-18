"""Input contracts aligned with the system design's versioned evidence references."""

from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    HttpUrl,
    StringConstraints,
    UrlConstraints,
    field_validator,
    model_validator,
)
from pydantic_core import PydanticCustomError

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
PositiveInt = Annotated[int, Field(strict=True, gt=0)]
Year = Annotated[int, Field(strict=True, ge=2020, le=2100)]


def _http_input(value: object) -> object:
    if isinstance(value, str) and any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise PydanticCustomError("url_control_character", "URL contains a control character")
    return value


def _public_url(value: HttpUrl) -> HttpUrl:
    if value.username is not None or value.password is not None:
        raise PydanticCustomError("url_credentials", "URL credentials are not allowed")
    return value


WebUrl = Annotated[
    HttpUrl,
    UrlConstraints(max_length=500),
    BeforeValidator(_http_input),
    AfterValidator(_public_url),
]


def _timestamp_input(value: object) -> object:
    if not isinstance(value, datetime) and not (isinstance(value, str) and "T" in value):
        raise PydanticCustomError("timestamp_format", "Use an ISO 8601 timestamp with timezone")
    return value


Timestamp = Annotated[
    AwareDatetime,
    BeforeValidator(_timestamp_input),
    AfterValidator(lambda value: value.astimezone(UTC)),
]


class Contract(BaseModel):
    model_config = ConfigDict(
        extra="forbid", frozen=True, str_strip_whitespace=True, hide_input_in_errors=True
    )


class SectionLocator(Contract):
    kind: Literal["section"]
    section: Annotated[Text, Field(max_length=300)]


class PageLocator(Contract):
    kind: Literal["page"]
    page: PositiveInt
    end_page: PositiveInt | None = None

    @model_validator(mode="after")
    def check_range(self) -> PageLocator:
        if self.end_page is not None and self.end_page < self.page:
            raise PydanticCustomError("page_range", "end_page must be at least page")
        return self


class TextSpanLocator(Contract):
    kind: Literal["text_span"]
    paragraph: PositiveInt
    start: Annotated[int, Field(strict=True, ge=0)]
    end: PositiveInt

    @model_validator(mode="after")
    def check_range(self) -> TextSpanLocator:
        if self.end <= self.start:
            raise PydanticCustomError("text_span_range", "end must be greater than start")
        return self


class TableRowLocator(Contract):
    kind: Literal["table_row"]
    table: Annotated[Text, Field(max_length=250)]
    row: PositiveInt


Locator = Annotated[
    SectionLocator | PageLocator | TextSpanLocator | TableRowLocator,
    Field(discriminator="kind"),
]


class SourceSnapshot(Contract):
    """A source/snapshot join supplied by the official-source collector or backend."""

    origin: Literal["official_retrieval"]
    source_id: UUID
    snapshot_id: UUID
    version_no: PositiveInt
    url: WebUrl
    title: Text
    publisher: Annotated[Text, Field(max_length=160)]
    scope_year: Year
    fetched_at: Timestamp


class OfficialReference(Contract):
    kind: Literal["official"]
    source_id: UUID
    snapshot_id: UUID
    fetched_at: Timestamp
    locator: Locator
    quote: Text | None = None

    @field_validator("locator")
    @classmethod
    def check_storage_length(cls, value: Locator) -> Locator:
        if len(locator_text(value)) > 300:
            raise PydanticCustomError("locator_too_long", "Locator exceeds the storage limit")
        return value


class OfficialBatch(Contract):
    scope_year: Year
    snapshots: Annotated[list[SourceSnapshot], Field(min_length=1)]
    citations: Annotated[list[OfficialReference], Field(min_length=1)]


class FactReference(Contract):
    """A private reference; its authorization is checked by the calling service."""

    kind: Literal["personal_fact"]
    owner_id: UUID
    matter_id: UUID
    fact_id: UUID
    fact_version: PositiveInt
    confirmed_at: Timestamp


def locator_text(locator: Locator) -> str:
    """Produce a deterministic, readable locator for ops.evidence.locator."""
    match locator:
        case SectionLocator(section=section):
            return section
        case PageLocator(page=page, end_page=end_page):
            if end_page is None or end_page == page:
                return f"第{page}页"
            return f"第{page}—{end_page}页"
        case TextSpanLocator(paragraph=paragraph, start=start, end=end):
            return f"第{paragraph}段，字符[{start}:{end}]"
        case TableRowLocator(table=table, row=row):
            return f"{table}，第{row}行"
    raise TypeError("Unsupported locator")
