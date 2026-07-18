from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class DocumentType(str, Enum):
    PDF = "pdf"
    DOCX = "docx"


class PdfBlock(BaseModel):
    text: str
    bbox: tuple[float, float, float, float]


class PdfPage(BaseModel):
    page_number: int = Field(ge=1)
    text: str
    blocks: list[PdfBlock] = Field(default_factory=list)


class DocumentBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    block_id: str
    block_type: str
    section_title: str | None = None
    text: str
    order: int = Field(ge=1)
    rows: list[list[str]] | None = None
    question_number: str | None = None


class DocumentChunk(BaseModel):
    chunk_index: int = Field(ge=1)
    content: str
    start_page: int | None = None
    end_page: int | None = None
    page_offset: int = 0
    start_block: int | None = None
    end_block: int | None = None
    pdf_bytes: bytes | None = None


class ParsedDocument(BaseModel):
    document_type: DocumentType
    pages: list[PdfPage] = Field(default_factory=list)
    blocks: list[DocumentBlock] = Field(default_factory=list)
    page_count: int | None = None
    is_scanned_pdf: bool = False
    has_images: bool = False
    warnings: list[str] = Field(default_factory=list)

    @property
    def text(self) -> str:
        if self.document_type == DocumentType.PDF:
            return "\n\n".join(page.text for page in self.pages if page.text)
        return "\n\n".join(block.text for block in self.blocks if block.text)

