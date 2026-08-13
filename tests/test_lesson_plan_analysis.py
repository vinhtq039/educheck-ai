from __future__ import annotations

from config.settings import Settings
from schemas.document import DocumentBlock, DocumentType, ParsedDocument
from schemas.analysis import AnalysisIssue, AnalysisResult, DocumentSummary
from schemas.lesson_plan import LessonPlanProfile
from schemas.package import AnswerKeyProfile
from schemas.review import FinalReviewResult
from services.analysis_service import (
    analyze_document,
    analyze_lesson_plan,
    merge_lesson_plan_profiles,
)
from services.review_service import filter_subjective_issues


def settings() -> Settings:
    return Settings(
        openai_api_key="test-key",
        openai_model="gpt-5.6-sol",
        openai_reasoning_effort="medium",
        max_file_size_mb=30,
        max_pdf_pages=150,
        pdf_pages_per_chunk=10,
        docx_chars_per_chunk=30000,
        ai_max_retries=0,
        ai_timeout_seconds=180,
    )


def profile(**overrides) -> LessonPlanProfile:
    values = {
        "source_document_type": "docx",
        "subject": "Toán",
        "grade_level": "6",
        "topic": "Phân số",
        "objectives": ["Nhận biết phân số."],
        "knowledge_scope": ["Khái niệm phân số."],
        "summary": "Giáo án về phân số.",
    }
    values.update(overrides)
    return LessonPlanProfile(**values)


class FakeLessonPlanAI:
    def __init__(self, result: LessonPlanProfile) -> None:
        self.result = result
        self.calls = []

    def analyze_lesson_plan_chunk(self, chunk, document_type, prompt):
        self.calls.append((chunk, document_type, prompt))
        return self.result


def test_lesson_plan_is_analyzed_before_being_used_as_context() -> None:
    parsed = ParsedDocument(
        document_type=DocumentType.DOCX,
        blocks=[
            DocumentBlock(
                block_id="block-0001",
                block_type="paragraph",
                text="Mục tiêu: Nhận biết phân số.",
                order=1,
            )
        ],
    )
    ai = FakeLessonPlanAI(profile())
    result = analyze_lesson_plan(
        parsed=parsed,
        original_bytes=b"docx",
        settings=settings(),
        ai_service=ai,
    )
    assert result.topic == "Phân số"
    assert len(ai.calls) == 1
    assert "Không bổ sung kiến thức" in ai.calls[0][2]


def test_merge_lesson_plan_profiles_deduplicates_context() -> None:
    merged = merge_lesson_plan_profiles(
        [
            profile(),
            profile(
                objectives=["Nhận biết phân số.", "So sánh hai phân số."],
                uncertainties=["Chưa rõ thời lượng."],
                summary="Có hoạt động luyện tập.",
            ),
        ],
        DocumentType.DOCX,
    )
    assert merged.objectives == [
        "Nhận biết phân số.",
        "So sánh hai phân số.",
    ]
    assert merged.uncertainties == ["Chưa rõ thời lượng."]
    assert "Có hoạt động luyện tập." in merged.summary


class FakeTwoPassAI:
    def __init__(self) -> None:
        self.analysis_prompt = ""
        self.review_prompt = ""

    def analyze_chunk(self, chunk, document_type, prompt):
        self.analysis_prompt = prompt
        return AnalysisResult(
            document_summary=DocumentSummary(
                document_type="docx",
                detected_languages=["vi"],
                summary="Một câu hỏi ngắn.",
            ),
            issues=[
                AnalysisIssue(
                    issue_id="temporary",
                    category="ambiguous_question",
                    severity="warning",
                    block_id="block-0001",
                    original_text="Hãy làm bài.",
                    explanation="Yêu cầu chưa rõ.",
                    confidence=0.8,
                )
            ],
            general_recommendations=[],
            limitations=[],
        )

    def review_analysis(self, prompt, expected_issue_ids):
        self.review_prompt = prompt
        issue_id = next(iter(expected_issue_ids))
        return FinalReviewResult(
            summary="Đề bài cần nêu rõ hành động.",
            reviews=[
                {
                    "issue_id": issue_id,
                    "action": "keep",
                    "severity": "warning",
                    "confidence": 0.9,
                    "explanation": "Đề bài chưa nêu sản phẩm học sinh cần hoàn thành.",
                    "requires_human_review": False,
                    "review_reason": "Ảnh hưởng trực tiếp đến khả năng thực hiện.",
                }
            ],
            general_recommendations=[],
            limitations=[],
        )


class FakeVietnameseIssueAI:
    def analyze_chunk(self, chunk, document_type, prompt):
        return AnalysisResult(
            document_summary=DocumentSummary(
                document_type="docx",
                detected_languages=["vi"],
                summary="Một học liệu.",
            ),
            issues=[
                AnalysisIssue(
                    issue_id="temporary",
                    category="vietnamese_spelling",
                    severity="warning",
                    block_id="block-0001",
                    original_text="Nội dung",
                    explanation="Nhận xét tiếng Việt không còn thuộc phạm vi.",
                    confidence=0.9,
                )
            ],
            general_recommendations=[],
            limitations=[],
        )


def test_vietnamese_language_issues_are_always_removed() -> None:
    parsed = ParsedDocument(
        document_type=DocumentType.DOCX,
        blocks=[
            DocumentBlock(
                block_id="block-0001",
                block_type="paragraph",
                text="Nội dung",
                order=1,
            )
        ],
    )

    result = analyze_document(
        parsed=parsed,
        original_bytes=b"docx",
        metadata={"custom_request": ""},
        lesson_plan=profile(),
        selected_checks=["prompt_quality", "vi_spelling"],
        settings=settings(),
        ai_service=FakeVietnameseIssueAI(),
    )

    assert result.issues == []


def test_learning_material_uses_lesson_plan_then_final_review() -> None:
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
    ai = FakeTwoPassAI()
    answer_key = AnswerKeyProfile(
        source_file_name="key.docx",
        entries=[
            {
                "entry_id": "answer-0001",
                "question_number": "1",
                "official_answer": "A",
                "block_id": "block-0001",
                "source_file_name": "key.docx",
            }
        ],
        summary="Một đáp án.",
        limitations=[],
    )
    result = analyze_document(
        parsed=parsed,
        original_bytes=b"docx",
        metadata={"custom_request": ""},
        lesson_plan=profile(),
        selected_checks=["prompt_quality"],
        settings=settings(),
        ai_service=ai,
        answer_key=answer_key,
    )
    assert "LESSON PLAN PROFILE" in ai.analysis_prompt
    assert "TRUSTED ANSWER KEY" in ai.analysis_prompt
    assert '"official_answer":"A"' in ai.analysis_prompt
    assert "candidate_issues" in ai.review_prompt
    assert '"official_answer":"A"' in ai.review_prompt
    assert result.document_summary.summary == "Đề bài cần nêu rõ hành động."
    assert result.issues[0].issue_id == "part-001-issue-001"


def test_subjective_expression_preference_is_removed_after_review() -> None:
    result = AnalysisResult(
        document_summary=DocumentSummary(
            document_type="docx",
            detected_languages=["en"],
            summary="Có một nhận xét.",
        ),
        issues=[
            AnalysisIssue(
                issue_id="issue-style",
                category="english_expression",
                severity="warning",
                block_id="block-0001",
                original_text="Choose the correct response.",
                explanation="Có thể diễn đạt tự nhiên hơn bằng một cách viết khác.",
                suggested_text="Choose the best response.",
                confidence=0.9,
            )
        ],
        general_recommendations=["Nên diễn đạt tự nhiên hơn."],
        limitations=[],
    )

    filtered = filter_subjective_issues(result)

    assert filtered.issues == []
    assert filtered.general_recommendations == []
    assert "Không phát hiện lỗi khách quan" in filtered.document_summary.summary
