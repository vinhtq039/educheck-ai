from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher

import pymupdf

from schemas.analysis import AnalysisIssue, IssueSeverity
from schemas.document import PdfBlock, PdfPage
from utils.text_utils import similarity_key


SEVERITY_COLORS: dict[IssueSeverity, tuple[float, float, float]] = {
    IssueSeverity.CRITICAL: (0.86, 0.15, 0.15),
    IssueSeverity.WARNING: (0.95, 0.55, 0.08),
    IssueSeverity.SUGGESTION: (0.10, 0.48, 0.85),
}


@dataclass(frozen=True, slots=True)
class PdfPreview:
    image_bytes: bytes
    matched_issue_numbers: set[int]
    unmatched_issue_numbers: set[int]


def _match_block(issue: AnalysisIssue, blocks: list[PdfBlock]) -> PdfBlock | None:
    issue_key = similarity_key(issue.original_text)
    if not issue_key or not blocks:
        return None

    for block in blocks:
        block_key = similarity_key(block.text)
        if len(block_key) >= 5 and (
            issue_key in block_key or block_key in issue_key
        ):
            return block

    scored = [
        (
            SequenceMatcher(None, issue_key, similarity_key(block.text)).ratio(),
            block,
        )
        for block in blocks
        if block.text.strip()
    ]
    if not scored:
        return None
    score, block = max(scored, key=lambda item: item[0])
    return block if score >= 0.60 else None


def render_pdf_page_preview(
    pdf_bytes: bytes,
    parsed_page: PdfPage,
    numbered_issues: list[tuple[int, AnalysisIssue]],
    zoom: float = 1.35,
) -> PdfPreview:
    document = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    matched: set[int] = set()
    unmatched: set[int] = set()
    try:
        page = document.load_page(parsed_page.page_number - 1)
        for number, issue in numbered_issues:
            color = SEVERITY_COLORS[issue.severity]
            block = _match_block(issue, parsed_page.blocks)
            if block is None:
                unmatched.add(number)
                page.draw_rect(
                    page.rect + (2, 2, -2, -2),
                    color=color,
                    width=2.5,
                    overlay=True,
                )
                continue

            matched.add(number)
            rect = pymupdf.Rect(block.bbox)
            page.draw_rect(
                rect,
                color=color,
                fill=color,
                fill_opacity=0.16,
                width=2.0,
                overlay=True,
            )
            label_rect = pymupdf.Rect(
                max(0, rect.x0 - 2),
                max(0, rect.y0 - 13),
                min(page.rect.width, rect.x0 + 30),
                max(12, rect.y0),
            )
            page.draw_rect(label_rect, color=color, fill=color, overlay=True)
            page.insert_text(
                (label_rect.x0 + 3, label_rect.y1 - 3),
                f"#{number}",
                fontsize=8,
                color=(1, 1, 1),
                overlay=True,
            )

        pixmap = page.get_pixmap(
            matrix=pymupdf.Matrix(zoom, zoom),
            alpha=False,
            annots=True,
        )
        return PdfPreview(
            image_bytes=pixmap.tobytes("png"),
            matched_issue_numbers=matched,
            unmatched_issue_numbers=unmatched,
        )
    finally:
        document.close()
