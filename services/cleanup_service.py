from __future__ import annotations

from collections.abc import MutableMapping


RESULT_KEYS = (
    "analysis_status",
    "analysis_result",
    "lesson_plan_profile",
    "teaching_context_profile",
    "student_question_set",
    "answer_key_profile",
    "package_comparison_result",
    "analysis_error",
    "ai_usage_summary",
    "current_file_name",
    "lesson_plan_file_name",
    "learning_material_file_name",
    "teaching_file_names",
    "answer_key_file_name",
    "analysis_metadata",
    "document_warnings",
    "preview_document",
    "preview_file_bytes",
    "preview_pdf_page",
    "lesson_plan_preview_document",
    "lesson_plan_preview_file_bytes",
    "lesson_plan_preview_pdf_page",
    "teaching_preview_documents",
    "teaching_preview_file_bytes",
    "answer_key_preview_document",
    "answer_key_preview_file_bytes",
    "answer_key_preview_pdf_page",
)

SESSION_KEYS = (
    "uploaded_file_hash",
    "lesson_plan_file_hash",
    "learning_material_file_hash",
    *RESULT_KEYS,
)


def clear_analysis_results(state: MutableMapping) -> None:
    """Remove every output from a previous run while preserving selected uploads."""

    for key in RESULT_KEYS:
        state.pop(key, None)


def clear_analysis_state(state: MutableMapping, keep_file_identity: bool = False) -> None:
    keys = SESSION_KEYS
    if keep_file_identity:
        keys = RESULT_KEYS
    for key in keys:
        state.pop(key, None)
