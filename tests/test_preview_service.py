from __future__ import annotations

import pymupdf

from schemas.analysis import AnalysisIssue
from services.pdf_parser import parse_pdf
from services.preview_service import render_pdf_page_preview


def make_pdf(text: str) -> bytes:
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), text)
    data = document.tobytes()
    document.close()
    return data


def test_pdf_preview_highlights_matching_block() -> None:
    data = make_pdf("Cau hoi nay co loi chinh ta.")
    parsed = parse_pdf(data, max_pages=5)
    issue = AnalysisIssue(
        issue_id="issue-1",
        category="vietnamese_spelling",
        severity="warning",
        page_number=1,
        original_text="Cau hoi nay co loi chinh ta.",
        explanation="Sai chinh ta.",
        confidence=0.9,
    )
    preview = render_pdf_page_preview(data, parsed.pages[0], [(1, issue)])
    assert preview.image_bytes.startswith(b"\x89PNG")
    assert preview.matched_issue_numbers == {1}
    assert preview.unmatched_issue_numbers == set()


def test_pdf_preview_marks_page_when_block_cannot_be_matched() -> None:
    data = make_pdf("Noi dung tren trang.")
    parsed = parse_pdf(data, max_pages=5)
    issue = AnalysisIssue(
        issue_id="issue-2",
        category="missing_information",
        severity="critical",
        page_number=1,
        original_text="Van ban khong ton tai trong block.",
        explanation="Thieu du kien.",
        confidence=0.85,
    )
    preview = render_pdf_page_preview(data, parsed.pages[0], [(2, issue)])
    assert preview.image_bytes.startswith(b"\x89PNG")
    assert preview.unmatched_issue_numbers == {2}
