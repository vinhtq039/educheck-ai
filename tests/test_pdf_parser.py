from __future__ import annotations

import pymupdf
import pytest

from services.pdf_parser import parse_pdf, split_pdf_bytes
from utils.validators import FileValidationError


def make_pdf(page_texts: list[str]) -> bytes:
    document = pymupdf.open()
    for text in page_texts:
        page = document.new_page()
        if text:
            page.insert_text((72, 72), text)
    data = document.tobytes()
    document.close()
    return data


def test_parses_pages_and_blocks() -> None:
    parsed = parse_pdf(make_pdf(["First page", "Second page"]), max_pages=5)
    assert parsed.page_count == 2
    assert parsed.pages[0].page_number == 1
    assert "First page" in parsed.pages[0].text
    assert parsed.pages[0].blocks[0].bbox


def test_detects_scanned_or_text_sparse_pdf() -> None:
    parsed = parse_pdf(make_pdf(["", "", "small"]), max_pages=5)
    assert parsed.is_scanned_pdf is True
    assert parsed.warnings


def test_rejects_corrupt_pdf() -> None:
    with pytest.raises(FileValidationError, match="Không thể đọc"):
        parse_pdf(b"%PDF-broken", max_pages=5)


def test_rejects_page_limit() -> None:
    with pytest.raises(FileValidationError, match="vượt quá giới hạn"):
        parse_pdf(make_pdf(["1", "2"]), max_pages=1)


def test_splits_pdf_with_original_ranges() -> None:
    chunks = split_pdf_bytes(make_pdf(["1", "2", "3"]), pages_per_chunk=2)
    assert [(start, end) for start, end, _ in chunks] == [(1, 2), (3, 3)]
    assert parse_pdf(chunks[0][2], max_pages=5).page_count == 2

