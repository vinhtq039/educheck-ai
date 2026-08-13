from __future__ import annotations

from services.cleanup_service import clear_analysis_results


def test_clear_analysis_results_preserves_upload_identity_only() -> None:
    state = {
        "uploaded_file_hash": "same-package",
        "analysis_status": "COMPLETED",
        "analysis_result": {"old": True},
        "lesson_plan_profile": {"old": True},
        "preview_document": {"old": True},
        "analysis_error": "old error",
    }

    clear_analysis_results(state)

    assert state == {"uploaded_file_hash": "same-package"}
