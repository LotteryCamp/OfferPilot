"""Input and locator types for public sources."""

from datetime import UTC, datetime
from typing import Annotated, Literal, Self

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
    model_validator,
)
from pydantic_core import PydanticCustomError

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
PositiveInt = Annotated[int, Field(strict=True, gt=0)]
Year = Annotated[int, Field(strict=True, ge=2020, le=2100)]


def _http_input(value: object) -> object:
    if isinstance(value, str) and any(
        ord(char) < 32 or ord(char) == 127 for char in value
    ):
        raise PydanticCustomError(
            "url_control_character", "URL contains a control character"
        )
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
    if not isinstance(value, datetime) and not (
        isinstance(value, str) and "T" in value
    ):
        raise PydanticCustomError(
            "timestamp_format", "Use an ISO 8601 timestamp with timezone"
        )
    return value


Timestamp = Annotated[
    AwareDatetime,
    BeforeValidator(_timestamp_input),
    AfterValidator(lambda value: value.astimezone(UTC)),
]


class Contract(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        hide_input_in_errors=True,
    )


class SectionLocator(Contract):
    kind: Literal["section"]
    section: Annotated[Text, Field(max_length=300)]


class PageLocator(Contract):
    kind: Literal["page"]
    page: PositiveInt


class TextSpanLocator(Contract):
    kind: Literal["text_span"]
    paragraph: PositiveInt
    start: Annotated[int, Field(strict=True, ge=0)]
    end: PositiveInt

    @model_validator(mode="after")
    def check_range(self) -> Self:
        if self.end <= self.start:
            raise PydanticCustomError(
                "text_span_range", "end must be greater than start"
            )
        return self


class TableRowLocator(Contract):
    kind: Literal["table_row"]
    table: Annotated[Text, Field(max_length=250)]
    row: PositiveInt


Locator = Annotated[
    SectionLocator | PageLocator | TextSpanLocator | TableRowLocator,
    Field(discriminator="kind"),
]


def locator_text(locator: Locator) -> str:
    """Produce a deterministic, readable locator for ops.evidence.locator."""
    match locator:
        case SectionLocator(section=section):
            return section
        case PageLocator(page=page):
            return f"第{page}页"
        case TextSpanLocator(paragraph=paragraph, start=start, end=end):
            return f"第{paragraph}段，字符[{start}:{end}]"
        case TableRowLocator(table=table, row=row):
            return f"{table}，第{row}行"
    raise TypeError("Unsupported locator")
