from __future__ import annotations

from collections.abc import Callable, Mapping

from config.settings import Settings
from prompts.document_analysis_prompt import build_analysis_prompt
from schemas.analysis import AnalysisResult
from schemas.document import DocumentType, ParsedDocument
from services.chunk_service import chunk_document
from services.openai_service import OpenAIService
from services.result_merge_service import merge_results
from utils.validators import FileValidationError


ProgressCallback = Callable[[str, float], None]


def analyze_document(
    *,
    parsed: ParsedDocument,
    original_bytes: bytes,
    metadata: Mapping[str, str],
    selected_checks: list[str],
    settings: Settings,
    progress: ProgressCallback | None = None,
    ai_service: OpenAIService | None = None,
) -> AnalysisResult:
    if not selected_checks:
        raise FileValidationError("Vui lòng chọn ít nhất một loại kiểm tra.")
    if parsed.document_type == DocumentType.DOCX and not parsed.blocks:
        raise FileValidationError("Không tìm thấy đủ nội dung để phân tích.")

    notify = progress or (lambda _message, _value: None)
    notify("Đang chia tài liệu", 0.25)
    chunks = chunk_document(
        parsed,
        original_bytes,
        settings.pdf_pages_per_chunk,
        settings.docx_chars_per_chunk,
    )
    if not chunks:
        raise FileValidationError("Không tìm thấy đủ nội dung để phân tích.")

    ai = ai_service or OpenAIService(settings)
    results: list[AnalysisResult] = []
    total = len(chunks)
    for index, chunk in enumerate(chunks, start=1):
        notify(f"Đang phân tích phần {index}/{total}", 0.3 + 0.55 * (index - 1) / total)
        prompt = build_analysis_prompt(
            document_type=parsed.document_type.value,
            content=chunk.content,
            metadata=metadata,
            selected_checks=selected_checks,
            chunk_label=f"phần {index}/{total}",
        )
        results.append(ai.analyze_chunk(chunk, parsed.document_type, prompt))

    notify("Đang tổng hợp kết quả", 0.9)
    result = merge_results(results)
    result.limitations = list(dict.fromkeys(parsed.warnings + result.limitations))
    notify("Hoàn tất", 1.0)
    return result
