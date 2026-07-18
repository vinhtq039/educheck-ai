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

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    load_dotenv()
    reasoning_effort = os.getenv("OPENAI_REASONING_EFFORT", "medium").strip().lower()
    if reasoning_effort not in {"none", "low", "medium", "high", "xhigh", "max"}:
        raise ValueError(
            "OPENAI_REASONING_EFFORT phải là none, low, medium, high, xhigh hoặc max."
        )
    text_verbosity = os.getenv("OPENAI_TEXT_VERBOSITY", "low").strip().lower()
    if text_verbosity not in {"low", "medium", "high"}:
        raise ValueError(
            "OPENAI_TEXT_VERBOSITY phải là low, medium hoặc high."
        )
    return Settings(
        openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-5.6-sol").strip(),
        openai_reasoning_effort=reasoning_effort,
        max_file_size_mb=_positive_int("MAX_FILE_SIZE_MB", 30),
        max_pdf_pages=_positive_int("MAX_PDF_PAGES", 150),
        pdf_pages_per_chunk=_positive_int("PDF_PAGES_PER_CHUNK", 10),
        docx_chars_per_chunk=_positive_int("DOCX_CHARS_PER_CHUNK", 30000),
        ai_max_retries=max(0, int(os.getenv("AI_MAX_RETRIES", "2"))),
        ai_timeout_seconds=_positive_int("AI_TIMEOUT_SECONDS", 180),
        openai_text_verbosity=text_verbosity,
    )
