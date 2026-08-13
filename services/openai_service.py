from __future__ import annotations

import base64
import time
from collections.abc import Callable
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from config.settings import Settings
from prompts.answer_key_prompt import ANSWER_KEY_SYSTEM_PROMPT
from prompts.lesson_plan_prompt import LESSON_PLAN_SYSTEM_PROMPT
from prompts.package_comparison_prompt import COMPARISON_SYSTEM_PROMPT
from prompts.question_extraction_prompt import QUESTION_EXTRACTION_SYSTEM_PROMPT
from prompts.question_solving_prompt import QUESTION_SOLVING_SYSTEM_PROMPT
from prompts.review_prompt import REVIEW_SYSTEM_PROMPT
from prompts.system_prompt import SYSTEM_PROMPT
from prompts.teaching_context_prompt import TEACHING_CONTEXT_SYSTEM_PROMPT
from schemas.analysis import AnalysisResult
from schemas.document import DocumentChunk, DocumentType
from schemas.lesson_plan import LessonPlanProfile
from schemas.package import (
    AnswerKeyProfile,
    ExtractedQuestionSet,
    PackageComparisonResult,
    QuestionSolutionSet,
    TeachingContextProfile,
)
from schemas.review import FinalReviewResult
from schemas.usage import AIUsageRecord, AIUsageSummary
from services.usage_service import summarize_usage, usage_record_from_response


class OpenAIServiceError(RuntimeError):
    """Friendly OpenAI error safe to display."""


def _friendly_api_error(exc: Exception) -> OpenAIServiceError:
    text = f"{type(exc).__name__}: {exc}".lower()
    if any(token in text for token in ("ratelimit", "rate limit", "quota", "429")):
        return OpenAIServiceError(
            "Không thể gọi AI do đã vượt giới hạn sử dụng API. "
            "Vui lòng kiểm tra quota OpenAI."
        )
    if any(token in text for token in ("timeout", "timed out", "deadline")):
        return OpenAIServiceError(
            "OpenAI phản hồi quá thời gian cho phép. Vui lòng thử lại."
        )
    if any(
        token in text
        for token in ("authentication", "api key", "api_key", "unauthorized", "401", "403")
    ):
        return OpenAIServiceError(
            "Không thể xác thực OpenAI API. Vui lòng kiểm tra OPENAI_API_KEY."
        )
    return OpenAIServiceError(
        "Không thể phân tích tài liệu bằng OpenAI vào lúc này. Vui lòng thử lại."
    )


T = TypeVar("T", bound=BaseModel)


class OpenAIService:
    def __init__(self, settings: Settings, client: Any | None = None) -> None:
        if not settings.openai_api_key and client is None:
            raise OpenAIServiceError("Chưa cấu hình OPENAI_API_KEY.")
        self.settings = settings
        self.usage_records: list[AIUsageRecord] = []
        if client is not None:
            self.client = client
            return

        from openai import OpenAI

        self.client = OpenAI(
            api_key=settings.openai_api_key,
            timeout=settings.ai_timeout_seconds,
            max_retries=0,
        )

    def _request_profile(self, stage: str) -> tuple[str, str]:
        if stage == "package_comparison":
            return (
                self.settings.openai_escalation_model,
                self.settings.openai_escalation_reasoning_effort,
            )
        if stage == "student_solving":
            return (
                self.settings.openai_solving_model,
                self.settings.openai_solving_reasoning_effort,
            )
        return self.settings.openai_model, self.settings.openai_reasoning_effort

    def usage_summary(self) -> AIUsageSummary:
        return summarize_usage(list(self.usage_records))

    def _input_content(
        self,
        chunk: DocumentChunk,
        document_type: DocumentType,
        prompt: str,
        *,
        filename_prefix: str = "document",
    ) -> list[dict[str, Any]]:
        content: list[dict[str, Any]] = []
        if document_type == DocumentType.PDF and chunk.pdf_bytes is not None:
            encoded = base64.b64encode(chunk.pdf_bytes).decode("ascii")
            content.append(
                {
                    "type": "input_file",
                    "filename": f"{filename_prefix}-part-{chunk.chunk_index}.pdf",
                    "file_data": f"data:application/pdf;base64,{encoded}",
                    "detail": chunk.pdf_detail or "high",
                }
            )
        content.append({"type": "input_text", "text": prompt})
        return content

    def _parse_structured(
        self,
        *,
        system_prompt: str,
        user_content: list[dict[str, Any]],
        text_format: type[T],
        empty_message: str,
        invalid_message: str,
        stage: str,
        validate: Callable[[T], None] | None = None,
    ) -> T:
        input_items = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]
        last_error: Exception | None = None
        model, reasoning_effort = self._request_profile(stage)

        for attempt in range(self.settings.ai_max_retries + 1):
            try:
                response = self.client.responses.parse(
                    model=model,
                    input=input_items,
                    text_format=text_format,
                    reasoning={"effort": reasoning_effort},
                    text={"verbosity": self.settings.openai_text_verbosity},
                    max_output_tokens=self.settings.max_output_tokens,
                    store=False,
                )
                self.usage_records.append(
                    usage_record_from_response(
                        response,
                        stage=stage,
                        requested_model=model,
                        reasoning_effort=reasoning_effort,
                        attempt=attempt + 1,
                    )
                )
                parsed = response.output_parsed
                if parsed is None:
                    raise OpenAIServiceError(empty_message)
                result = (
                    parsed
                    if isinstance(parsed, text_format)
                    else text_format.model_validate(parsed)
                )
                if validate is not None:
                    validate(result)
                return result
            except (ValidationError, OpenAIServiceError, ValueError) as exc:
                last_error = exc
            except Exception as exc:
                last_error = exc
                friendly = _friendly_api_error(exc)
                message = str(friendly).lower()
                if "quota" in message or "xác thực" in message:
                    raise friendly from exc
            if attempt < self.settings.ai_max_retries:
                time.sleep(min(2**attempt, 4))

        if isinstance(last_error, OpenAIServiceError):
            raise last_error
        if isinstance(last_error, (ValidationError, ValueError)):
            raise OpenAIServiceError(invalid_message) from last_error
        assert last_error is not None
        raise _friendly_api_error(last_error) from last_error

    def analyze_chunk(
        self,
        chunk: DocumentChunk,
        document_type: DocumentType,
        prompt: str,
    ) -> AnalysisResult:
        result = self._parse_structured(
            system_prompt=SYSTEM_PROMPT,
            user_content=self._input_content(chunk, document_type, prompt),
            text_format=AnalysisResult,
            empty_message="OpenAI không trả về nội dung phân tích có cấu trúc.",
            invalid_message="OpenAI trả về kết quả phân tích không đúng cấu trúc.",
            stage="document_analysis",
        )
        if document_type == DocumentType.PDF and chunk.page_offset:
            for issue in result.issues:
                if issue.page_number is not None:
                    issue.page_number += chunk.page_offset
        return result

    def analyze_lesson_plan_chunk(
        self,
        chunk: DocumentChunk,
        document_type: DocumentType,
        prompt: str,
    ) -> LessonPlanProfile:
        return self._parse_structured(
            system_prompt=LESSON_PLAN_SYSTEM_PROMPT,
            user_content=self._input_content(
                chunk,
                document_type,
                prompt,
                filename_prefix="lesson-plan",
            ),
            text_format=LessonPlanProfile,
            empty_message="OpenAI không trả về hồ sơ giáo án có cấu trúc.",
            invalid_message="OpenAI trả về hồ sơ giáo án không đúng cấu trúc.",
            stage="lesson_plan",
        )

    def analyze_teaching_material_chunk(
        self,
        chunk: DocumentChunk,
        document_type: DocumentType,
        prompt: str,
    ) -> TeachingContextProfile:
        return self._parse_structured(
            system_prompt=TEACHING_CONTEXT_SYSTEM_PROMPT,
            user_content=self._input_content(
                chunk,
                document_type,
                prompt,
                filename_prefix="teaching-material",
            ),
            text_format=TeachingContextProfile,
            empty_message="OpenAI không trả về ngữ cảnh tài liệu dạy.",
            invalid_message="OpenAI trả về ngữ cảnh tài liệu dạy không đúng cấu trúc.",
            stage="teaching_context",
        )

    def extract_student_questions_chunk(
        self,
        chunk: DocumentChunk,
        document_type: DocumentType,
        prompt: str,
    ) -> ExtractedQuestionSet:
        result = self._parse_structured(
            system_prompt=QUESTION_EXTRACTION_SYSTEM_PROMPT,
            user_content=self._input_content(
                chunk,
                document_type,
                prompt,
                filename_prefix="student-material",
            ),
            text_format=ExtractedQuestionSet,
            empty_message="OpenAI không trả về danh sách câu hỏi đã trích xuất.",
            invalid_message="OpenAI trả về cấu trúc câu hỏi không hợp lệ.",
            stage="question_extraction",
        )
        if document_type == DocumentType.PDF and chunk.page_offset:
            for question in result.questions:
                if question.page_number is not None:
                    question.page_number += chunk.page_offset
        return result

    def solve_question_batch(
        self,
        prompt: str,
        expected_question_ids: set[str],
    ) -> QuestionSolutionSet:
        def validate(result: QuestionSolutionSet) -> None:
            returned_ids = [solution.question_id for solution in result.solutions]
            if (
                set(returned_ids) != expected_question_ids
                or len(returned_ids) != len(set(returned_ids))
            ):
                raise OpenAIServiceError(
                    "Lời giải theo nhóm bị thiếu, thừa hoặc trùng mã câu hỏi."
                )

        return self._parse_structured(
            system_prompt=QUESTION_SOLVING_SYSTEM_PROMPT,
            user_content=[{"type": "input_text", "text": prompt}],
            text_format=QuestionSolutionSet,
            empty_message="OpenAI không trả về lời giải theo nhóm.",
            invalid_message="OpenAI trả về lời giải theo nhóm không đúng cấu trúc.",
            stage="student_solving",
            validate=validate,
        )

    def extract_answer_key_chunk(
        self,
        chunk: DocumentChunk,
        document_type: DocumentType,
        prompt: str,
    ) -> AnswerKeyProfile:
        result = self._parse_structured(
            system_prompt=ANSWER_KEY_SYSTEM_PROMPT,
            user_content=self._input_content(
                chunk,
                document_type,
                prompt,
                filename_prefix="answer-key",
            ),
            text_format=AnswerKeyProfile,
            empty_message="OpenAI không trả về dữ liệu đáp án.",
            invalid_message="OpenAI trả về dữ liệu đáp án không đúng cấu trúc.",
            stage="answer_key",
        )
        if document_type == DocumentType.PDF and chunk.page_offset:
            for entry in result.entries:
                if entry.page_number is not None:
                    entry.page_number += chunk.page_offset
        return result

    def compare_package(
        self,
        prompt: str,
        expected_question_ids: set[str],
        expected_entry_ids: set[str],
    ) -> PackageComparisonResult:
        def validate(result: PackageComparisonResult) -> None:
            question_ids = [
                item.material_question_id
                for item in result.comparisons
                if item.material_question_id
            ]
            entry_ids = [
                item.answer_key_entry_id
                for item in result.comparisons
                if item.answer_key_entry_id
            ]
            if (
                set(question_ids) != expected_question_ids
                or len(question_ids) != len(set(question_ids))
                or set(entry_ids) != expected_entry_ids
                or len(entry_ids) != len(set(entry_ids))
            ):
                raise OpenAIServiceError(
                    "Đối chiếu thiếu, thừa hoặc ghép trùng câu hỏi/đáp án."
                )

        return self._parse_structured(
            system_prompt=COMPARISON_SYSTEM_PROMPT,
            user_content=[{"type": "input_text", "text": prompt}],
            text_format=PackageComparisonResult,
            empty_message="OpenAI không trả về kết quả đối chiếu.",
            invalid_message="OpenAI trả về kết quả đối chiếu không đúng cấu trúc.",
            stage="package_comparison",
            validate=validate,
        )

    def review_analysis(
        self,
        prompt: str,
        expected_issue_ids: set[str],
    ) -> FinalReviewResult:
        def validate(result: FinalReviewResult) -> None:
            returned_ids = [review.issue_id for review in result.reviews]
            if (
                len(returned_ids) != len(set(returned_ids))
                or set(returned_ids) != expected_issue_ids
            ):
                raise OpenAIServiceError(
                    "OpenAI kiểm duyệt thiếu, thừa hoặc trùng mã vấn đề."
                )

        return self._parse_structured(
            system_prompt=REVIEW_SYSTEM_PROMPT,
            user_content=[{"type": "input_text", "text": prompt}],
            text_format=FinalReviewResult,
            empty_message="OpenAI không trả về kết quả kiểm duyệt có cấu trúc.",
            invalid_message="OpenAI trả về kết quả kiểm duyệt không đúng cấu trúc.",
            stage="final_review",
            validate=validate,
        )
