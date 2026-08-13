from __future__ import annotations

import io
from collections import Counter

import pymupdf

from schemas.document import DocumentType, ParsedDocument, PdfBlock, PdfPage
from utils.text_utils import normalize_text
from utils.validators import FileValidationError


SCAN_TEXT_THRESHOLD = 40
SCAN_PAGE_RATIO = 0.6


def _repeated_margin_text(pages: list[PdfPage]) -> set[str]:
    if len(pages) < 3:
        return set()
    occurrences: Counter[str] = Counter()
    for page in pages:
        candidates = {
            block.text.strip()
            for block in (page.blocks[:2] + page.blocks[-2:])
            if 0 < len(block.text.strip()) <= 160
        }
        occurrences.update(candidates)
    minimum = max(3, int(len(pages) * 0.7))
    return {text for text, count in occurrences.items() if count >= minimum}


def parse_pdf(data: bytes, max_pages: int) -> ParsedDocument:
    try:
        document = pymupdf.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise FileValidationError(
            "Không thể đọc tài liệu PDF. File có thể bị hỏng."
        ) from exc

    try:
        if document.needs_pass:
            raise FileValidationError(
                "Tài liệu PDF đang được bảo vệ bằng mật khẩu. "
                "Vui lòng bỏ mật khẩu rồi tải lại."
            )
        if document.page_count < 1:
            raise FileValidationError("Tài liệu PDF không có trang nào.")
        if document.page_count > max_pages:
            raise FileValidationError(
                f"Tài liệu PDF vượt quá giới hạn {max_pages} trang."
            )

        pages: list[PdfPage] = []
        has_images = False
        for index, page in enumerate(document):
            has_images = has_images or bool(page.get_images(full=True))
            raw_blocks = page.get_text("blocks", sort=True)
            blocks = [
                PdfBlock(
                    text=normalize_text(str(item[4])),
                    bbox=(float(item[0]), float(item[1]), float(item[2]), float(item[3])),
                )
                for item in raw_blocks
                if len(item) >= 5 and normalize_text(str(item[4]))
            ]
            pages.append(
                PdfPage(
                    page_number=index + 1,
                    text=normalize_text("\n".join(block.text for block in blocks)),
                    blocks=blocks,
                )
            )

        repeated = _repeated_margin_text(pages)
        if repeated:
            for page in pages:
                page.blocks = [block for block in page.blocks if block.text not in repeated]
                page.text = normalize_text("\n".join(block.text for block in page.blocks))

        sparse_pages = sum(len(page.text) < SCAN_TEXT_THRESHOLD for page in pages)
        scanned = sparse_pages / len(pages) >= SCAN_PAGE_RATIO
        warnings: list[str] = []
        if scanned:
            warnings.append(
                "Tài liệu có thể là PDF scan. AI sẽ phân tích trực tiếp nội dung hiển thị "
                "trên trang, nhưng vị trí lỗi có thể không chính xác tuyệt đối."
            )

        return ParsedDocument(
            document_type=DocumentType.PDF,
            pages=pages,
            page_count=document.page_count,
            is_scanned_pdf=scanned,
            has_images=has_images,
            warnings=warnings,
        )
    finally:
        document.close()


def split_pdf_bytes(data: bytes, pages_per_chunk: int) -> list[tuple[int, int, bytes]]:
    source = pymupdf.open(stream=data, filetype="pdf")
    try:
        chunks: list[tuple[int, int, bytes]] = []
        for start in range(0, source.page_count, pages_per_chunk):
            end = min(start + pages_per_chunk, source.page_count)
            output = pymupdf.open()
            try:
                output.insert_pdf(source, from_page=start, to_page=end - 1)
                chunks.append((start + 1, end, output.tobytes(garbage=4, deflate=True)))
            finally:
                output.close()
        return chunks
    finally:
        source.close()
