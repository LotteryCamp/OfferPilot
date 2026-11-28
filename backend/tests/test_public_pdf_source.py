"""Verify page citations and explicit failures for public PDF sources."""

from datetime import UTC, datetime
from io import BytesIO

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from backend.sources import (
    SourceReadError,
    parse_public_pdf,
    source_registration_payload,
)

PDF_URL = "https://example.org/notice.pdf"
REQUEST = {"url": PDF_URL, "publisher": "Example University", "scope_year": 2027}


def _pdf_with_text_on_second_page() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    page = writer.add_blank_page(width=200, height=200)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
    )
    content = DecodedStreamObject()
    content.set_data(b"BT /F1 12 Tf 10 100 Td (Submit a transcript.) Tj ET")
    page[NameObject("/Contents")] = content
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def test_pdf_citation_keeps_physical_page_number():
    result = parse_public_pdf(
        _pdf_with_text_on_second_page(),
        final_url=PDF_URL,
        request=REQUEST,
        fetched_at=datetime.now(UTC),
    )
    assert result.content_type == "application/pdf"
    assert source_registration_payload(result)["fragments"] == [
        {"locator_kind": "page", "locator": "第2页", "quote": "Submit a transcript."}
    ]


@pytest.mark.parametrize(
    ("body", "code"),
    [
        (b"%PDF-1.7\n", "pdf_parse_error"),
        (b"%PDF-1.7\n" + b"x" * (4 * 1024 * 1024), "response_too_large"),
    ],
)
def test_pdf_failure_returns_a_structured_error(body: bytes, code: str):
    with pytest.raises(SourceReadError) as error:
        parse_public_pdf(
            body, final_url=PDF_URL, request=REQUEST, fetched_at=datetime.now(UTC)
        )
    assert error.value.code == code
    assert not error.value.retryable


def test_pdf_without_a_text_layer_returns_a_structured_error():
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    output = BytesIO()
    writer.write(output)

    with pytest.raises(SourceReadError) as error:
        parse_public_pdf(
            output.getvalue(),
            final_url=PDF_URL,
            request=REQUEST,
            fetched_at=datetime.now(UTC),
        )
    assert error.value.code == "pdf_no_text"
