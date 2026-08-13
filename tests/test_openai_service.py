from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

from config.settings import Settings
from schemas.analysis import AnalysisResult, DocumentSummary
from schemas.document import DocumentChunk, DocumentType
from schemas.lesson_plan import LessonPlanProfile
from schemas.package import (
    ExtractedQuestionSet,
    PackageComparisonResult,
    QuestionSolutionSet,
)
from schemas.review import FinalReviewResult
from services.openai_service import OpenAIService, OpenAIServiceError
from services.usage_service import usage_record_from_response


def settings(retries: int = 0) -> Settings:
    return Settings(
        openai_api_key="test-key",
        openai_model="gpt-5.6-sol",
        openai_reasoning_effort="medium",
        max_file_size_mb=30,
        max_pdf_pages=150,
        pdf_pages_per_chunk=10,
        docx_chars_per_chunk=30000,
        ai_max_retries=retries,
        ai_timeout_seconds=180,
    )


def valid_result(page_number: int = 1) -> AnalysisResult:
    return AnalysisResult(
        document_summary=DocumentSummary(
            document_type="pdf",
            detected_languages=["vi"],
            total_questions=1,
            summary="Một câu hỏi.",
        ),
        issues=[
            {
                "issue_id": "issue-1",
                "category": "ambiguous_question",
                "severity": "warning",
                "page_number": page_number,
                "original_text": "Câu hỏi?",
                "explanation": "Chưa rõ yêu cầu.",
                "confidence": 0.8,
                "requires_human_review": True,
            }
        ],
        general_recommendations=[],
        limitations=[],
    )


class FakeResponses:
    def __init__(self, responses) -> None:
        self.responses = iter(responses)
        self.calls = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        if hasattr(response, "output_parsed"):
            return response
        return SimpleNamespace(output_parsed=response)


def test_uses_responses_structured_output_and_applies_pdf_page_offset() -> None:
    responses = FakeResponses([valid_result(2)])
    service = OpenAIService(settings(), client=SimpleNamespace(responses=responses))
    result = service.analyze_chunk(
        DocumentChunk(
            chunk_index=2,
            content="",
            start_page=11,
            end_page=20,
            page_offset=10,
            pdf_bytes=b"%PDF-test",
        ),
        DocumentType.PDF,
        "Phân tích",
    )
    assert result.issues[0].page_number == 12
    call = responses.calls[0]
    assert call["model"] == "gpt-5.6-sol"
    assert call["text_format"] is AnalysisResult
    assert call["reasoning"] == {"effort": "medium"}
    assert call["text"] == {"verbosity": "low"}
    assert call["max_output_tokens"] == 8000
    assert call["store"] is False
    user_content = call["input"][1]["content"]
    assert user_content[0]["type"] == "input_file"
    assert user_content[0]["file_data"].startswith("data:application/pdf;base64,")
    assert user_content[1]["type"] == "input_text"


def test_text_pdf_can_be_analyzed_without_resending_pdf_bytes() -> None:
    responses = FakeResponses([valid_result()])
    service = OpenAIService(settings(), client=SimpleNamespace(responses=responses))

    service.analyze_chunk(
        DocumentChunk(chunk_index=1, content="Văn bản PDF đã trích xuất"),
        DocumentType.PDF,
        "Phân tích phần văn bản đã trích xuất",
    )

    user_content = responses.calls[0]["input"][1]["content"]
    assert [item["type"] for item in user_content] == ["input_text"]


def test_student_solving_and_comparison_use_different_model_roles() -> None:
    question_set = QuestionSolutionSet(
        solutions=[],
        limitations=[],
    )
    comparison = PackageComparisonResult(
        summary="Không có mục đối chiếu.",
        comparisons=[],
        recommendations=[],
        limitations=[],
    )
    responses = FakeResponses([question_set, comparison])
    configured = settings()
    configured = replace(
        configured,
        openai_model="gpt-5-nano",
        openai_solving_model="gpt-5-mini",
        openai_escalation_model="gpt-5-mini",
        openai_solving_reasoning_effort="low",
        openai_escalation_reasoning_effort="low",
    )
    service = OpenAIService(
        configured,
        client=SimpleNamespace(responses=responses),
    )

    service.solve_question_batch("Tự giải", set())
    service.compare_package("Đối chiếu", set(), set())

    assert responses.calls[0]["model"] == "gpt-5-mini"
    assert responses.calls[0]["reasoning"] == {"effort": "low"}
    assert responses.calls[1]["model"] == "gpt-5-mini"
    assert responses.calls[1]["reasoning"] == {"effort": "low"}


def test_question_extraction_and_batched_solving_use_separate_model_roles() -> None:
    extracted = ExtractedQuestionSet(
        questions=[
            {
                "question_number": "1",
                "question_text": "Choose A.",
                "options": ["A", "B"],
                "block_id": "block-0001",
                "confidence": 0.95,
            }
        ],
        summary="Một câu.",
        limitations=[],
    )
    solved = QuestionSolutionSet(
        solutions=[
            {
                "question_id": "question-0001",
                "independent_answer": "A",
                "reasoning_summary": "A phù hợp.",
                "confidence": 0.9,
                "evidence_ids": ["lesson:summary:1"],
            }
        ],
        limitations=[],
    )
    responses = FakeResponses([extracted, solved])
    configured = replace(
        settings(),
        openai_model="gpt-5-nano",
        openai_reasoning_effort="minimal",
        openai_solving_model="gpt-5-mini",
        openai_solving_reasoning_effort="low",
    )
    service = OpenAIService(
        configured,
        client=SimpleNamespace(responses=responses),
    )

    service.extract_student_questions_chunk(
        DocumentChunk(chunk_index=1, content="Question 1"),
        DocumentType.DOCX,
        "Tách câu",
    )
    service.solve_question_batch("Giải câu", {"question-0001"})

    assert responses.calls[0]["model"] == "gpt-5-nano"
    assert responses.calls[0]["reasoning"] == {"effort": "minimal"}
    assert responses.calls[0]["text_format"] is ExtractedQuestionSet
    assert responses.calls[1]["model"] == "gpt-5-mini"
    assert responses.calls[1]["reasoning"] == {"effort": "low"}
    assert responses.calls[1]["text_format"] is QuestionSolutionSet


def test_estimates_nano_and_mini_standard_api_costs() -> None:
    nano_response = SimpleNamespace(
        output_parsed=valid_result(),
        model="gpt-5-nano",
        usage=SimpleNamespace(
            input_tokens=100_000,
            output_tokens=10_000,
            input_tokens_details=SimpleNamespace(cached_tokens=20_000),
            output_tokens_details=SimpleNamespace(reasoning_tokens=1_000),
        ),
    )
    mini_response = SimpleNamespace(
        output_parsed=valid_result(),
        model="gpt-5-mini",
        usage=SimpleNamespace(
            input_tokens=100_000,
            output_tokens=10_000,
            input_tokens_details=SimpleNamespace(cached_tokens=20_000),
            output_tokens_details=SimpleNamespace(reasoning_tokens=2_000),
        ),
    )
    nano_record = usage_record_from_response(
        nano_response,
        stage="lesson_plan",
        requested_model="gpt-5-nano",
        reasoning_effort="minimal",
        attempt=1,
    )
    mini_record = usage_record_from_response(
        mini_response,
        stage="student_solving",
        requested_model="gpt-5-mini",
        reasoning_effort="low",
        attempt=1,
    )

    assert nano_record.estimated_cost_usd == pytest.approx(0.0081)
    assert mini_record.estimated_cost_usd == pytest.approx(0.0405)


def test_records_usage_and_estimates_standard_api_cost() -> None:
    response = SimpleNamespace(
        output_parsed=valid_result(),
        model="gpt-5.6-terra",
        usage=SimpleNamespace(
            input_tokens=100_000,
            output_tokens=10_000,
            input_tokens_details=SimpleNamespace(cached_tokens=20_000),
            output_tokens_details=SimpleNamespace(reasoning_tokens=4_000),
        ),
    )
    responses = FakeResponses([response])
    configured = settings()
    configured = replace(configured, openai_model="gpt-5.6-terra")
    service = OpenAIService(
        configured,
        client=SimpleNamespace(responses=responses),
    )

    service.analyze_chunk(
        DocumentChunk(chunk_index=1, content="Nội dung"),
        DocumentType.DOCX,
        "Phân tích",
    )
    usage = service.usage_summary()

    assert usage.call_count == 1
    assert usage.input_tokens == 100_000
    assert usage.cached_input_tokens == 20_000
    assert usage.output_tokens == 10_000
    assert usage.reasoning_tokens == 4_000
    assert usage.estimated_cost_usd == pytest.approx(0.355)


def test_invalid_schema_is_retried(monkeypatch) -> None:
    monkeypatch.setattr("services.openai_service.time.sleep", lambda _seconds: None)
    responses = FakeResponses([{}, valid_result()])
    service = OpenAIService(settings(retries=1), client=SimpleNamespace(responses=responses))
    result = service.analyze_chunk(
        DocumentChunk(chunk_index=1, content="Nội dung"),
        DocumentType.DOCX,
        "Phân tích",
    )
    assert len(responses.calls) == 2
    assert result.document_summary.total_questions == 1


def test_quota_error_is_friendly() -> None:
    responses = FakeResponses([RuntimeError("429 rate limit quota")])
    service = OpenAIService(settings(), client=SimpleNamespace(responses=responses))
    with pytest.raises(OpenAIServiceError, match="quota OpenAI"):
        service.analyze_chunk(
            DocumentChunk(chunk_index=1, content="Nội dung"),
            DocumentType.DOCX,
            "Phân tích",
        )


def test_requires_openai_api_key() -> None:
    no_key = Settings(
        openai_api_key="",
        openai_model="gpt-5.6-sol",
        openai_reasoning_effort="medium",
        max_file_size_mb=30,
        max_pdf_pages=150,
        pdf_pages_per_chunk=10,
        docx_chars_per_chunk=30000,
        ai_max_retries=0,
        ai_timeout_seconds=180,
    )
    with pytest.raises(OpenAIServiceError, match="OPENAI_API_KEY"):
        OpenAIService(no_key)


def test_lesson_plan_uses_separate_structured_output() -> None:
    profile = LessonPlanProfile(
        source_document_type="docx",
        subject="Toán",
        grade_level="6",
        topic="Phân số",
        objectives=["Nhận biết phân số."],
        summary="Bài học nhập môn phân số.",
    )
    responses = FakeResponses([profile])
    service = OpenAIService(settings(), client=SimpleNamespace(responses=responses))
    result = service.analyze_lesson_plan_chunk(
        DocumentChunk(chunk_index=1, content="Giáo án phân số"),
        DocumentType.DOCX,
        "Đọc giáo án",
    )
    assert result.subject == "Toán"
    call = responses.calls[0]
    assert call["text_format"] is LessonPlanProfile
    assert "giáo án" in call["input"][0]["content"].lower()


def test_review_retries_when_issue_ids_do_not_match(monkeypatch) -> None:
    monkeypatch.setattr("services.openai_service.time.sleep", lambda _seconds: None)
    wrong = FinalReviewResult(
        summary="Tóm tắt.",
        reviews=[],
        general_recommendations=[],
        limitations=[],
    )
    correct = FinalReviewResult(
        summary="Tóm tắt đã kiểm duyệt.",
        reviews=[
            {
                "issue_id": "issue-1",
                "action": "keep",
                "severity": "warning",
                "confidence": 0.9,
                "explanation": "Đề bài chưa xác định yêu cầu cần thực hiện.",
                "requires_human_review": False,
                "review_reason": "Có bằng chứng trực tiếp.",
            }
        ],
        general_recommendations=[],
        limitations=[],
    )
    responses = FakeResponses([wrong, correct])
    service = OpenAIService(
        settings(retries=1),
        client=SimpleNamespace(responses=responses),
    )
    result = service.review_analysis("Kiểm duyệt", {"issue-1"})
    assert result.summary == "Tóm tắt đã kiểm duyệt."
    assert len(responses.calls) == 2
    assert responses.calls[-1]["text_format"] is FinalReviewResult
    assert responses.calls[-1]["text"] == {"verbosity": "low"}
