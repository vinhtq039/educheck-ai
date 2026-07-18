from __future__ import annotations

import io

import pytest
from docx import Document

from utils.validators import FileValidationError, detect_document_type, validate_upload


def docx_bytes() -> bytes:
    stream = io.BytesIO()
    document = Document()
    document.add_paragraph("Nội dung")
    document.save(stream)
    return stream.getvalue()


def test_detects_real_docx() -> None:
    assert detect_document_type(docx_bytes(), "lesson.docx") == "docx"


def test_rejects_fake_pdf() -> None:
    with pytest.raises(FileValidationError, match="không đúng định dạng"):
        detect_document_type(b"not a pdf", "lesson.pdf")


def test_rejects_empty_file() -> None:
    with pytest.raises(FileValidationError, match="không được để trống"):
        detect_document_type(b"", "lesson.pdf")


def test_rejects_file_over_limit() -> None:
    with pytest.raises(FileValidationError, match="vượt quá dung lượng"):
        validate_upload(b"%PDF-" + b"x" * 100, "lesson.pdf", 10)

