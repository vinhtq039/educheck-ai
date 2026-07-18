from __future__ import annotations

from collections.abc import MutableMapping


SESSION_KEYS = (
    "uploaded_file_hash",
    "lesson_plan_file_hash",
    "learning_material_file_hash",
    "analysis_status",
    "analysis_result",
    "lesson_plan_profile",
    "analysis_error",
    "current_file_name",
    "lesson_plan_file_name",
    "learning_material_file_name",
    "analysis_metadata",
    "document_warnings",
    "preview_document",
    "preview_file_bytes",
    "preview_pdf_page",
    "lesson_plan_preview_document",
    "lesson_plan_preview_file_bytes",
    "lesson_plan_preview_pdf_page",
)


def clear_analysis_state(state: MutableMapping, keep_file_identity: bool = False) -> None:
    keys = SESSION_KEYS
    if keep_file_identity:
        keys = tuple(
            key for key in SESSION_KEYS if key in {"analysis_status", "analysis_result", "analysis_error"}
        )
    for key in keys:
        state.pop(key, None)
