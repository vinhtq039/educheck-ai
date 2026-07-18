from __future__ import annotations

from collections.abc import Callable, Mapping

from config.settings import Settings
from prompts.document_analysis_prompt import build_analysis_prompt
from prompts.lesson_plan_prompt import build_lesson_plan_prompt
from prompts.review_prompt import build_review_prompt
from schemas.analysis import AnalysisResult
from schemas.document import DocumentType, ParsedDocument
from schemas.lesson_plan import LessonPlanProfile
from services.chunk_service import chunk_document
from services.openai_service import OpenAIService
from services.result_merge_service import merge_results
from services.review_service import apply_review, validate_result_locations
from utils.validators import FileValidationError


ProgressCallback = Callable[[str, float], None]


def _unique_strings(values: list[str], limit: int | None = None) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = " ".join(value.casefold().split())
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(value.strip())
        if limit is not None and len(result) == limit:
            break
    return result


def _compact_summary(values: list[str], limit: int = 800) -> str:
    summary = " ".join(_unique_strings(values))
    if len(summary) <= limit:
        return summary
    shortened = summary[:limit].rsplit(" ", 1)[0].rstrip(" ,;:")
    return f"{shortened}."


def merge_lesson_plan_profiles(
    profiles: list[LessonPlanProfile],
    document_type: DocumentType,
) -> LessonPlanProfile:
    if not profiles:
        raise ValueError("Không có kết quả giáo án để tổng hợp.")

    def first_value(field: str) -> str | None:
        return next(
            (
                value
                for profile in profiles
                if (value := getattr(profile, field)) is not None and value.strip()
            ),
            None,
        )

    def merged_list(field: str) -> list[str]:
        return _unique_strings(
            [
                item
                for profile in profiles
                for item in getattr(profile, field)
            ],
            limit=20,
        )

    return LessonPlanProfile(
        source_document_type=document_type.value,
        subject=first_value("subject"),
        grade_level=first_value("grade_level"),
        topic=first_value("topic"),
        objectives=merged_list("objectives"),
        knowledge_scope=merged_list("knowledge_scope"),
        skills_and_competencies=merged_list("skills_and_competencies"),
        learning_activities=merged_list("learning_activities"),
        assessment_criteria=merged_list("assessment_criteria"),
        required_materials=merged_list("required_materials"),
        key_terms=merged_list("key_terms"),
        summary=_compact_summary(
            [profile.summary for profile in profiles if profile.summary.strip()]
        ),
        uncertainties=merged_list("uncertainties"),
    )


def analyze_lesson_plan(
    *,
    parsed: ParsedDocument,
    original_bytes: bytes,
    settings: Settings,
    progress: ProgressCallback | None = None,
    ai_service: OpenAIService | None = None,
) -> LessonPlanProfile:
    if parsed.document_type == DocumentType.DOCX and not parsed.blocks:
        raise FileValidationError(
            "Không tìm thấy đủ nội dung trong giáo án để phân tích."
        )

    notify = progress or (lambda _message, _value: None)
    notify("Đang chia giáo án", 0.1)
    chunks = chunk_document(
        parsed,
        original_bytes,
        settings.pdf_pages_per_chunk,
        settings.docx_chars_per_chunk,
    )
    if not chunks:
        raise FileValidationError(
            "Không tìm thấy đủ nội dung trong giáo án để phân tích."
        )

    ai = ai_service or OpenAIService(settings)
    profiles: list[LessonPlanProfile] = []
    total = len(chunks)
    for index, chunk in enumerate(chunks, start=1):
        notify(
            f"Đang đọc giáo án phần {index}/{total}",
            0.15 + 0.75 * (index - 1) / total,
        )
        prompt = build_lesson_plan_prompt(
            document_type=parsed.document_type.value,
            content=chunk.content,
            chunk_label=f"phần {index}/{total}",
        )
        profiles.append(
            ai.analyze_lesson_plan_chunk(chunk, parsed.document_type, prompt)
        )

    notify("Đang tổng hợp hồ sơ giáo án", 0.95)
    profile = merge_lesson_plan_profiles(profiles, parsed.document_type)
    notify("Đã phân tích xong giáo án", 1.0)
    return profile


def analyze_document(
    *,
    parsed: ParsedDocument,
    original_bytes: bytes,
    metadata: Mapping[str, str],
    lesson_plan: LessonPlanProfile,
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
    notify("Đang chia học liệu", 0.25)
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
        notify(
            f"Đang phân tích học liệu phần {index}/{total}",
            0.3 + 0.45 * (index - 1) / total,
        )
        prompt = build_analysis_prompt(
            document_type=parsed.document_type.value,
            content=chunk.content,
            metadata=metadata,
            lesson_plan=lesson_plan,
            selected_checks=selected_checks,
            chunk_label=f"phần {index}/{total}",
        )
        chunk_result = ai.analyze_chunk(chunk, parsed.document_type, prompt)
        for issue_number, issue in enumerate(chunk_result.issues, start=1):
            issue.issue_id = f"part-{index:03d}-issue-{issue_number:03d}"
        results.append(chunk_result)

    notify("Đang gộp và kiểm tra vị trí", 0.8)
    candidate = merge_results(results)
    candidate.limitations = _unique_strings(
        parsed.warnings + candidate.limitations,
        limit=8,
    )
    candidate = validate_result_locations(candidate, parsed)

    notify("Đang kiểm duyệt độ chính xác và độ cô đọng", 0.88)
    review_prompt = build_review_prompt(
        lesson_plan=lesson_plan,
        candidate_result=candidate,
        chunk_summaries=[
            chunk_result.document_summary.summary
            for chunk_result in results
        ],
    )
    review = ai.review_analysis(
        review_prompt,
        {issue.issue_id for issue in candidate.issues},
    )
    result = apply_review(candidate, review)
    notify("Hoàn tất", 1.0)
    return result
