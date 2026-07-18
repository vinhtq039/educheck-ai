from __future__ import annotations

from config.settings import Settings
from schemas.document import ParsedDocument
from services.docx_parser import parse_docx
from services.pdf_parser import parse_pdf
from utils.validators import validate_upload


def parse_document(
    data: bytes, file_name: str, settings: Settings
) -> ParsedDocument:
    document_type = validate_upload(data, file_name, settings.max_file_size_bytes)
    if document_type == "pdf":
        return parse_pdf(data, settings.max_pdf_pages)
    return parse_docx(data)

