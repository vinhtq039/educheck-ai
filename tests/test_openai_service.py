from __future__ import annotations

from types import SimpleNamespace

import pytest

from config.settings import Settings
from schemas.analysis import AnalysisResult, DocumentSummary
from schemas.document import DocumentChunk, DocumentType
from services.openai_service import OpenAIService, OpenAIServiceError


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
    user_content = call["input"][1]["content"]
    assert user_content[0]["type"] == "input_file"
    assert user_content[0]["file_data"].startswith("data:application/pdf;base64,")
    assert user_content[1]["type"] == "input_text"


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
