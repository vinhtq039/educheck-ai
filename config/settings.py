from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv


def _positive_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} phải là số nguyên.") from exc
    if value <= 0:
        raise ValueError(f"{name} phải lớn hơn 0.")
    return value


@dataclass(frozen=True, slots=True)
class Settings:
    openai_api_key: str
    openai_model: str
    openai_reasoning_effort: str
    max_file_size_mb: int
    max_pdf_pages: int
    pdf_pages_per_chunk: int
    docx_chars_per_chunk: int
    ai_max_retries: int
    ai_timeout_seconds: int
    openai_text_verbosity: str = "low"
    max_teaching_files: int = 6
    max_package_size_mb: int = 100
    comparison_batch_size: int = 40
    solving_batch_size: int = 12
    retrieval_top_k: int = 4
    retrieval_max_chars_per_question: int = 5000
    max_extracted_questions: int = 200
    max_output_tokens: int = 8000
    openai_solving_model: str = "gpt-5-mini"
    openai_escalation_model: str = "gpt-5-mini"
    openai_solving_reasoning_effort: str = "low"
    openai_escalation_reasoning_effort: str = "low"

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024

    @property
    def max_package_size_bytes(self) -> int:
        return self.max_package_size_mb * 1024 * 1024


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    load_dotenv()
    allowed_efforts = {"none", "minimal", "low", "medium", "high", "xhigh", "max"}

    def reasoning_setting(name: str, default: str) -> str:
        value = os.getenv(name, default).strip().lower()
        if value not in allowed_efforts:
            raise ValueError(
                f"{name} phải là none, minimal, low, medium, high, xhigh hoặc max."
            )
        return value

    reasoning_effort = reasoning_setting("OPENAI_REASONING_EFFORT", "minimal")
    solving_reasoning_effort = reasoning_setting(
        "OPENAI_SOLVING_REASONING_EFFORT",
        "low",
    )
    escalation_reasoning_effort = reasoning_setting(
        "OPENAI_ESCALATION_REASONING_EFFORT",
        "low",
    )
    text_verbosity = os.getenv("OPENAI_TEXT_VERBOSITY", "low").strip().lower()
    if text_verbosity not in {"low", "medium", "high"}:
        raise ValueError(
            "OPENAI_TEXT_VERBOSITY phải là low, medium hoặc high."
        )
    return Settings(
        openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-5-nano").strip(),
        openai_reasoning_effort=reasoning_effort,
        max_file_size_mb=_positive_int("MAX_FILE_SIZE_MB", 30),
        max_pdf_pages=_positive_int("MAX_PDF_PAGES", 150),
        pdf_pages_per_chunk=_positive_int("PDF_PAGES_PER_CHUNK", 10),
        docx_chars_per_chunk=_positive_int("DOCX_CHARS_PER_CHUNK", 30000),
        ai_max_retries=max(0, int(os.getenv("AI_MAX_RETRIES", "2"))),
        ai_timeout_seconds=_positive_int("AI_TIMEOUT_SECONDS", 180),
        openai_text_verbosity=text_verbosity,
        max_teaching_files=_positive_int("MAX_TEACHING_FILES", 6),
        max_package_size_mb=_positive_int("MAX_PACKAGE_SIZE_MB", 100),
        comparison_batch_size=_positive_int("COMPARISON_BATCH_SIZE", 40),
        solving_batch_size=_positive_int("SOLVING_BATCH_SIZE", 12),
        retrieval_top_k=_positive_int("RETRIEVAL_TOP_K", 4),
        retrieval_max_chars_per_question=_positive_int(
            "RETRIEVAL_MAX_CHARS_PER_QUESTION",
            5000,
        ),
        max_extracted_questions=_positive_int("MAX_EXTRACTED_QUESTIONS", 200),
        max_output_tokens=_positive_int("MAX_OUTPUT_TOKENS", 8000),
        openai_solving_model=os.getenv(
            "OPENAI_SOLVING_MODEL",
            "gpt-5-mini",
        ).strip(),
        openai_escalation_model=os.getenv(
            "OPENAI_ESCALATION_MODEL",
            "gpt-5-mini",
        ).strip(),
        openai_solving_reasoning_effort=solving_reasoning_effort,
        openai_escalation_reasoning_effort=escalation_reasoning_effort,
    )
