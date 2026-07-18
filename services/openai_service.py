from __future__ import annotations

import base64
import time
from typing import Any

from pydantic import ValidationError

from config.settings import Settings
from prompts.lesson_plan_prompt import LESSON_PLAN_SYSTEM_PROMPT
from prompts.review_prompt import REVIEW_SYSTEM_PROMPT
from prompts.system_prompt import SYSTEM_PROMPT
from schemas.analysis import AnalysisResult
from schemas.document import DocumentChunk, DocumentType
from schemas.lesson_plan import LessonPlanProfile
from schemas.review import FinalReviewResult


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


class OpenAIService:
    def __init__(self, settings: Settings, client: Any | None = None) -> None:
        if not settings.openai_api_key and client is None:
            raise OpenAIServiceError("Chưa cấu hình OPENAI_API_KEY.")
        self.settings = settings
        if client is not None:
            self.client = client
            return

        from openai import OpenAI

        self.client = OpenAI(
            api_key=settings.openai_api_key,
            timeout=settings.ai_timeout_seconds,
            max_retries=0,
        )

    def _input_content(
        self,
        chunk: DocumentChunk,
        document_type: DocumentType,
        prompt: str,
    ) -> list[dict[str, Any]]:
        content: list[dict[str, Any]] = []
        if document_type == DocumentType.PDF:
            if chunk.pdf_bytes is None:
                raise OpenAIServiceError("Không tìm thấy dữ liệu PDF để phân tích.")
            encoded = base64.b64encode(chunk.pdf_bytes).decode("ascii")
            content.append(
                {
                    "type": "input_file",
                    "filename": f"document-part-{chunk.chunk_index}.pdf",
                    "file_data": f"data:application/pdf;base64,{encoded}",
                    "detail": "high",
                }
            )
        content.append({"type": "input_text", "text": prompt})
        return content

    def analyze_chunk(
        self,
        chunk: DocumentChunk,
        document_type: DocumentType,
        prompt: str,
    ) -> AnalysisResult:
        input_items = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": self._input_content(chunk, document_type, prompt),
            },
        ]

        last_error: Exception | None = None
        for attempt in range(self.settings.ai_max_retries + 1):
            try:
                response = self.client.responses.parse(
                    model=self.settings.openai_model,
                    input=input_items,
                    text_format=AnalysisResult,
                    reasoning={"effort": self.settings.openai_reasoning_effort},
                    text={"verbosity": self.settings.openai_text_verbosity},
                )
                parsed = response.output_parsed
                if parsed is None:
                    raise OpenAIServiceError(
                        "OpenAI không trả về nội dung phân tích có cấu trúc."
                    )
                result = (
                    parsed
                    if isinstance(parsed, AnalysisResult)
                    else AnalysisResult.model_validate(parsed)
                )
                if document_type == DocumentType.PDF and chunk.page_offset:
                    for issue in result.issues:
                        if issue.page_number is not None:
                            issue.page_number += chunk.page_offset
                return result
            except (ValidationError, OpenAIServiceError) as exc:
                last_error = exc
            except Exception as exc:  # SDK exceptions vary between versions
                last_error = exc
                friendly = _friendly_api_error(exc)
                message = str(friendly).lower()
                if "quota" in message or "xác thực" in message:
                    raise friendly from exc
            if attempt < self.settings.ai_max_retries:
                time.sleep(min(2**attempt, 4))

        if isinstance(last_error, ValidationError):
            raise OpenAIServiceError(
                "OpenAI trả về kết quả không đúng cấu trúc sau nhiều lần thử."
            ) from last_error
        if isinstance(last_error, OpenAIServiceError):
            raise last_error
        assert last_error is not None
        raise _friendly_api_error(last_error) from last_error

    def analyze_lesson_plan_chunk(
        self,
        chunk: DocumentChunk,
        document_type: DocumentType,
        prompt: str,
    ) -> LessonPlanProfile:
        input_items = [
            {"role": "system", "content": LESSON_PLAN_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": self._input_content(chunk, document_type, prompt),
            },
        ]

        last_error: Exception | None = None
        for attempt in range(self.settings.ai_max_retries + 1):
            try:
                response = self.client.responses.parse(
                    model=self.settings.openai_model,
                    input=input_items,
                    text_format=LessonPlanProfile,
                    reasoning={"effort": self.settings.openai_reasoning_effort},
                    text={"verbosity": self.settings.openai_text_verbosity},
                )
                parsed = response.output_parsed
                if parsed is None:
                    raise OpenAIServiceError(
                        "OpenAI không trả về hồ sơ giáo án có cấu trúc."
                    )
                return (
                    parsed
                    if isinstance(parsed, LessonPlanProfile)
                    else LessonPlanProfile.model_validate(parsed)
                )
            except (ValidationError, OpenAIServiceError) as exc:
                last_error = exc
            except Exception as exc:
                last_error = exc
                friendly = _friendly_api_error(exc)
                message = str(friendly).lower()
                if "quota" in message or "xác thực" in message:
                    raise friendly from exc
            if attempt < self.settings.ai_max_retries:
                time.sleep(min(2**attempt, 4))

        if isinstance(last_error, ValidationError):
            raise OpenAIServiceError(
                "OpenAI trả về hồ sơ giáo án không đúng cấu trúc sau nhiều lần thử."
            ) from last_error
        if isinstance(last_error, OpenAIServiceError):
            raise last_error
        assert last_error is not None
        raise _friendly_api_error(last_error) from last_error

    def review_analysis(
        self,
        prompt: str,
        expected_issue_ids: set[str],
    ) -> FinalReviewResult:
        input_items = [
            {"role": "system", "content": REVIEW_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [{"type": "input_text", "text": prompt}],
            },
        ]

        last_error: Exception | None = None
        for attempt in range(self.settings.ai_max_retries + 1):
            try:
                response = self.client.responses.parse(
                    model=self.settings.openai_model,
                    input=input_items,
                    text_format=FinalReviewResult,
                    reasoning={"effort": self.settings.openai_reasoning_effort},
                    text={"verbosity": self.settings.openai_text_verbosity},
                )
                parsed = response.output_parsed
                if parsed is None:
                    raise OpenAIServiceError(
                        "OpenAI không trả về kết quả kiểm duyệt có cấu trúc."
                    )
                result = (
                    parsed
                    if isinstance(parsed, FinalReviewResult)
                    else FinalReviewResult.model_validate(parsed)
                )
                returned_ids = [review.issue_id for review in result.reviews]
                if (
                    len(returned_ids) != len(set(returned_ids))
                    or set(returned_ids) != expected_issue_ids
                ):
                    raise OpenAIServiceError(
                        "OpenAI kiểm duyệt thiếu, thừa hoặc trùng mã vấn đề."
                    )
                return result
            except (ValidationError, OpenAIServiceError) as exc:
                last_error = exc
            except Exception as exc:
                last_error = exc
                friendly = _friendly_api_error(exc)
                message = str(friendly).lower()
                if "quota" in message or "xác thực" in message:
                    raise friendly from exc
            if attempt < self.settings.ai_max_retries:
                time.sleep(min(2**attempt, 4))

        if isinstance(last_error, ValidationError):
            raise OpenAIServiceError(
                "OpenAI trả về kết quả kiểm duyệt không đúng cấu trúc."
            ) from last_error
        if isinstance(last_error, OpenAIServiceError):
            raise last_error
        assert last_error is not None
        raise _friendly_api_error(last_error) from last_error
