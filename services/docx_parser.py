from __future__ import annotations

import io

from docx import Document
from docx.document import Document as DocumentObject
from docx.table import Table
from docx.text.paragraph import Paragraph
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P

from schemas.document import DocumentBlock, DocumentType, ParsedDocument
from utils.text_utils import detect_question_number, normalize_text
from utils.validators import FileValidationError


def iter_body_items(document: DocumentObject):
    for child in document.element.body.iterchildren():
        if isinstance(child, CT_P):
            yield Paragraph(child, document)
        elif isinstance(child, CT_Tbl):
            yield Table(child, document)


def _count_images(document: DocumentObject) -> int:
    return len(document.inline_shapes) + len(document.element.xpath(".//a:graphic"))


def parse_docx(data: bytes) -> ParsedDocument:
    try:
        document = Document(io.BytesIO(data))
    except Exception as exc:
        raise FileValidationError(
            "Không thể đọc tài liệu Word. File có thể bị hỏng hoặc không đúng định dạng DOCX."
        ) from exc

    blocks: list[DocumentBlock] = []
    current_heading: str | None = None
    for item in iter_body_items(document):
        if isinstance(item, Paragraph):
            text = normalize_text(item.text)
            if not text:
                continue
            style_name = item.style.name if item.style else ""
            block_type = "heading" if style_name.lower().startswith("heading") else "paragraph"
            if block_type == "heading":
                current_heading = text
            order = len(blocks) + 1
            blocks.append(
                DocumentBlock(
                    block_id=f"block-{order:04d}",
                    block_type=block_type,
                    section_title=current_heading,
                    text=text,
                    order=order,
                    question_number=detect_question_number(text),
                )
            )
        else:
            rows = [
                [normalize_text(cell.text) for cell in row.cells]
                for row in item.rows
            ]
            text = normalize_text("\n".join(" | ".join(row) for row in rows))
            if not text:
                continue
            order = len(blocks) + 1
            blocks.append(
                DocumentBlock(
                    block_id=f"block-{order:04d}",
                    block_type="table",
                    section_title=current_heading,
                    text=text,
                    rows=rows,
                    order=order,
                )
            )

    image_count = _count_images(document)
    warnings: list[str] = []
    if image_count:
        warnings.append(
            "Tài liệu Word có thể chứa hình ảnh hoặc đối tượng không được trích xuất đầy đủ. "
            "Các câu hỏi phụ thuộc vào hình cần được kiểm tra lại."
        )
    return ParsedDocument(
        document_type=DocumentType.DOCX,
        blocks=blocks,
        has_images=image_count > 0,
        warnings=warnings,
    )

