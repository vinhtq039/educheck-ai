from __future__ import annotations

from schemas.document import DocumentType, ParsedDocument, PdfPage
from services.chunk_service import chunk_document


def pdf_document(*, scanned: bool = False, has_images: bool = False) -> ParsedDocument:
    return ParsedDocument(
        document_type=DocumentType.PDF,
        pages=[
            PdfPage(page_number=1, text="Nội dung trang 1."),
            PdfPage(page_number=2, text="Nội dung trang 2."),
        ],
        page_count=2,
        is_scanned_pdf=scanned,
        has_images=has_images,
    )


def test_text_native_pdf_uses_extracted_text_without_file_payload() -> None:
    chunks = chunk_document(pdf_document(), b"%PDF-large", 10, 30_000)

    assert len(chunks) == 1
    assert chunks[0].pdf_bytes is None
    assert chunks[0].pdf_detail is None
    assert "Nội dung trang 1" in chunks[0].content


def test_scanned_pdf_keeps_high_detail_visual_input() -> None:
    chunks = chunk_document(
        pdf_document(scanned=True),
        b"%PDF-scanned",
        10,
        30_000,
    )

    assert chunks[0].pdf_bytes == b"%PDF-scanned"
    assert chunks[0].pdf_detail == "high"


def test_pdf_with_images_uses_low_detail_visual_input() -> None:
    chunks = chunk_document(
        pdf_document(has_images=True),
        b"%PDF-visual",
        10,
        30_000,
    )

    assert chunks[0].pdf_bytes == b"%PDF-visual"
    assert chunks[0].pdf_detail == "low"
