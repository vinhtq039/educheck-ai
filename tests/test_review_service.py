from __future__ import annotations

from schemas.analysis import AnalysisIssue, AnalysisResult, DocumentSummary
from schemas.document import DocumentBlock, DocumentType, ParsedDocument
from schemas.review import FinalReviewResult
from services.review_service import apply_review, validate_result_locations


def candidate_result() -> AnalysisResult:
    return AnalysisResult(
        document_summary=DocumentSummary(
            document_type="docx",
            detected_languages=["vi"],
            summary="Tóm tắt ứng viên.",
        ),
        issues=[
            AnalysisIssue(
                issue_id="keep-me",
                category="ambiguous_question",
                severity="warning",
                block_id="block-0001",
                original_text="Hãy làm bài.",
                explanation="Chưa rõ yêu cầu.",
                confidence=0.8,
            ),
            AnalysisIssue(
                issue_id="remove-me",
                category="vietnamese_expression",
                severity="suggestion",
                block_id="block-0002",
                original_text="Đọc đoạn văn.",
                explanation="Có thể viết hay hơn.",
                confidence=0.8,
            ),
        ],
        general_recommendations=[],
        limitations=[],
    )


def test_review_can_remove_noise_but_cannot_change_source_location() -> None:
    review = FinalReviewResult(
        summary="Một vấn đề cần sửa.",
        reviews=[
            {
                "issue_id": "keep-me",
                "action": "revise",
                "severity": "warning",
                "confidence": 0.92,
                "explanation": "Đề bài không nêu hành động hoặc sản phẩm cần hoàn thành.",
                "suggested_text": "Hãy trả lời ba câu hỏi sau.",
                "requires_human_review": False,
                "review_reason": "Ảnh hưởng trực tiếp đến khả năng thực hiện.",
            },
            {
                "issue_id": "remove-me",
                "action": "remove",
                "severity": "suggestion",
                "confidence": 0.8,
                "explanation": "Chỉ là khác biệt văn phong.",
                "requires_human_review": False,
                "review_reason": "Không ảnh hưởng đến tính đúng hoặc khả năng hiểu.",
            },
        ],
        general_recommendations=["Chuẩn hóa động từ yêu cầu."],
        limitations=[],
    )
    result = apply_review(candidate_result(), review)
    assert [issue.issue_id for issue in result.issues] == ["keep-me"]
    issue = result.issues[0]
    assert issue.block_id == "block-0001"
    assert issue.original_text == "Hãy làm bài."
    assert issue.explanation.startswith("Đề bài không nêu")
    assert result.document_summary.summary == "Một vấn đề cần sửa."


def test_location_validator_removes_unknown_block() -> None:
    result = candidate_result()
    parsed = ParsedDocument(
        document_type=DocumentType.DOCX,
        blocks=[
            DocumentBlock(
                block_id="block-0001",
                block_type="paragraph",
                text="Hãy làm bài.",
                order=1,
            )
        ],
    )
    validated = validate_result_locations(result, parsed)
    assert [issue.issue_id for issue in validated.issues] == ["keep-me"]
    assert any("remove-me" in limitation for limitation in validated.limitations)


def test_quote_mismatch_requires_human_review() -> None:
    result = candidate_result()
    parsed = ParsedDocument(
        document_type=DocumentType.DOCX,
        blocks=[
            DocumentBlock(
                block_id="block-0001",
                block_type="paragraph",
                text="Nội dung hoàn toàn khác.",
                order=1,
            ),
            DocumentBlock(
                block_id="block-0002",
                block_type="paragraph",
                text="Đọc đoạn văn.",
                order=2,
            ),
        ],
    )
    validated = validate_result_locations(result, parsed)
    issue = next(item for item in validated.issues if item.issue_id == "keep-me")
    assert issue.requires_human_review is True
