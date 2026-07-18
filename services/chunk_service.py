from __future__ import annotations

from schemas.document import DocumentChunk, DocumentType, ParsedDocument
from services.pdf_parser import split_pdf_bytes


def chunk_document(
    parsed: ParsedDocument,
    original_bytes: bytes,
    pdf_pages_per_chunk: int,
    docx_chars_per_chunk: int,
) -> list[DocumentChunk]:
    if parsed.document_type == DocumentType.PDF:
        assert parsed.page_count is not None
        if parsed.page_count <= 25:
            return [
                DocumentChunk(
                    chunk_index=1,
                    content=parsed.text,
                    start_page=1,
                    end_page=parsed.page_count,
                    pdf_bytes=original_bytes,
                )
            ]
        return [
            DocumentChunk(
                chunk_index=index,
                content="\n\n".join(
                    page.text
                    for page in parsed.pages
                    if start <= page.page_number <= end
                ),
                start_page=start,
                end_page=end,
                page_offset=start - 1,
                pdf_bytes=pdf_bytes,
            )
            for index, (start, end, pdf_bytes) in enumerate(
                split_pdf_bytes(original_bytes, pdf_pages_per_chunk), start=1
            )
        ]

    chunks: list[DocumentChunk] = []
    current = []
    current_length = 0

    def flush() -> None:
        nonlocal current, current_length
        if not current:
            return
        content = "\n\n".join(
            f"[{block.block_id} | {block.block_type}"
            f"{f' | mục: {block.section_title}' if block.section_title else ''}]\n{block.text}"
            for block in current
        )
        chunks.append(
            DocumentChunk(
                chunk_index=len(chunks) + 1,
                content=content,
                start_block=current[0].order,
                end_block=current[-1].order,
            )
        )
        current = []
        current_length = 0

    for block in parsed.blocks:
        incoming = len(block.text) + 100
        starts_section = block.block_type == "heading"
        if current and (
            current_length + incoming > docx_chars_per_chunk
            or (starts_section and current_length >= docx_chars_per_chunk * 0.6)
        ):
            flush()
        current.append(block)
        current_length += incoming
    flush()
    return chunks

