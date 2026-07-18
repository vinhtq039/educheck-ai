from __future__ import annotations

from streamlit.testing.v1 import AppTest

from schemas.analysis import AnalysisIssue, AnalysisResult, DocumentSummary
from schemas.document import DocumentBlock, DocumentType, ParsedDocument
from schemas.lesson_plan import LessonPlanProfile


def test_app_starts_and_analysis_requires_a_file() -> None:
    app = AppTest.from_file("app.py", default_timeout=10).run()
    assert not app.exception
    assert app.title[0].value == "AI kiểm tra học liệu"
    start_button = next(
        button
        for button in app.button
        if button.label == "Phân tích giáo án và học liệu"
    )
    assert start_button.disabled is True
    assert len(app.file_uploader) == 2


def test_clear_result_button_keeps_app_healthy() -> None:
    app = AppTest.from_file("app.py", default_timeout=10).run()
    clear_button = next(button for button in app.button if button.label == "Xóa kết quả")
    clear_button.click().run()
    assert not app.exception


def test_two_column_result_view_renders_docx_preview_and_report() -> None:
    result = AnalysisResult(
        document_summary=DocumentSummary(
            document_type="docx",
            detected_languages=["vi"],
            summary="Tóm tắt tài liệu.",
        ),
        issues=[
            AnalysisIssue(
                issue_id="issue-1",
                category="vietnamese_spelling",
                severity="warning",
                block_id="block-0001",
                original_text="Nội dung sai",
                explanation="Có lỗi chính tả.",
                confidence=0.9,
            )
        ],
        general_recommendations=[],
        limitations=[],
    )
    parsed = ParsedDocument(
        document_type=DocumentType.DOCX,
        blocks=[
            DocumentBlock(
                block_id="block-0001",
                block_type="paragraph",
                text="Nội dung sai",
                order=1,
            )
        ],
    )
    app = AppTest.from_file("app.py", default_timeout=10).run()
    app.session_state["analysis_result"] = result.model_dump(mode="json")
    app.session_state["lesson_plan_profile"] = LessonPlanProfile(
        source_document_type="docx",
        subject="Ngữ văn",
        grade_level="6",
        topic="Đọc hiểu",
        objectives=["Nhận biết ý chính."],
        summary="Giáo án đọc hiểu.",
    ).model_dump(mode="json")
    app.session_state["preview_document"] = parsed.model_dump(mode="json")
    app.session_state["preview_file_bytes"] = None
    app.session_state["lesson_plan_preview_document"] = parsed.model_dump(mode="json")
    app.session_state["lesson_plan_preview_file_bytes"] = None
    app.session_state["learning_material_file_name"] = "material.docx"
    app.session_state["lesson_plan_file_name"] = "lesson-plan.docx"
    app.session_state["analysis_metadata"] = {}
    app.run()
    assert not app.exception
    assert any(metric.label == "Tổng vấn đề" for metric in app.metric)
    assert any("Nội dung sai" in markdown.value for markdown in app.markdown)
