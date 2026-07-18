from __future__ import annotations

import pytest
from pydantic import ValidationError

from schemas.analysis import AnalysisIssue, AnalysisResult, DocumentSummary
from services.result_merge_service import merge_results


def test_suitability_issue_requires_lesson_plan_reference() -> None:
    with pytest.raises(ValidationError, match="căn cứ cụ thể"):
        AnalysisIssue(
            issue_id="scope-1",
            category="learning_objective_mismatch",
            severity="warning",
            original_text="Câu hỏi về nội dung khác.",
            explanation="Không đo đúng mục tiêu.",
            confidence=0.9,
        )


def test_low_confidence_requires_human_review() -> None:
    with pytest.raises(ValidationError, match="giáo viên xác minh"):
        AnalysisIssue(
            issue_id="uncertain-1",
            category="uncertain_content",
            severity="warning",
            original_text="Nội dung cần kiểm tra.",
            explanation="Chưa đủ dữ kiện kết luận.",
            confidence=0.6,
            requires_human_review=False,
        )


def test_merge_does_not_concatenate_chunk_summaries() -> None:
    results = [
        AnalysisResult(
            document_summary=DocumentSummary(
                document_type="docx",
                detected_languages=["vi"],
                summary=f"Tóm tắt phần {index} với nội dung chi tiết.",
            ),
            issues=[],
            general_recommendations=[],
            limitations=[],
        )
        for index in range(1, 4)
    ]
    merged = merge_results(results)
    assert "Tóm tắt phần 1" not in merged.document_summary.summary
    assert "3 phần" in merged.document_summary.summary
