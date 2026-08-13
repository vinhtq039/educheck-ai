from __future__ import annotations

from streamlit.testing.v1 import AppTest

from schemas.analysis import AnalysisIssue, AnalysisResult, DocumentSummary
from schemas.document import DocumentBlock, DocumentType, ParsedDocument
from schemas.lesson_plan import LessonPlanProfile
from schemas.package import (
    AnswerKeyProfile,
    PackageComparisonResult,
    StudentQuestionSet,
    TeachingContextProfile,
)
from schemas.usage import AIUsageSummary


def test_app_starts_and_analysis_requires_a_file() -> None:
    app = AppTest.from_file("app.py", default_timeout=10).run()
    assert not app.exception
    assert app.title[0].value == "AI kiểm tra bộ học liệu"
    start_button = next(
        button
        for button in app.button
        if button.label == "Kiểm tra nhanh bộ học liệu"
    )
    assert start_button.disabled is True
    assert app.radio[0].label == "Mức kiểm tra"
    assert app.radio[0].value == "Kiểm tra nhanh"
    assert not app.checkbox
    assert len(app.file_uploader) == 4
    assert sum(uploader.accept_multiple_files for uploader in app.file_uploader) == 1
    assert not app.get("doc_string")


def test_clear_result_button_keeps_app_healthy() -> None:
    app = AppTest.from_file("app.py", default_timeout=10).run()
    clear_button = next(button for button in app.button if button.label == "Xóa kết quả")
    clear_button.click().run()
    assert not app.exception


def test_full_mode_exposes_optional_detailed_checks() -> None:
    app = AppTest.from_file("app.py", default_timeout=10).run()
    app.radio[0].set_value("Phân tích toàn diện").run()

    assert not app.exception
    assert len(app.checkbox) == 6
    assert not any("Việt" in checkbox.label for checkbox in app.checkbox)
    assert any(
        button.label == "Phân tích toàn diện bộ học liệu"
        for button in app.button
    )


def test_package_result_view_renders_four_document_roles_and_report() -> None:
    result = AnalysisResult(
        document_summary=DocumentSummary(
            document_type="docx",
            detected_languages=["en"],
            summary="Tóm tắt tài liệu.",
        ),
        issues=[
            AnalysisIssue(
                issue_id="issue-1",
                category="english_spelling",
                severity="warning",
                block_id="block-0001",
                original_text="An English eror",
                explanation="Có lỗi chính tả tiếng Anh.",
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
    app.session_state["teaching_context_profile"] = TeachingContextProfile(
        source_file_names=["slides.docx"],
        covered_content=["Ý chính của đoạn văn."],
        key_terms=[],
        worked_examples=[],
        instructions_and_conventions=[],
        summary="Slide hướng dẫn tìm ý chính.",
        uncertainties=[],
    ).model_dump(mode="json")
    app.session_state["student_question_set"] = StudentQuestionSet(
        source_file_name="material.docx",
        questions=[],
        summary="Một bài tập ngắn.",
        limitations=[],
    ).model_dump(mode="json")
    app.session_state["answer_key_profile"] = AnswerKeyProfile(
        source_file_name="key.docx",
        entries=[],
        summary="Không có mục đáp án nhận diện được.",
        limitations=[],
    ).model_dump(mode="json")
    app.session_state["package_comparison_result"] = PackageComparisonResult(
        summary="Chưa có câu để đối chiếu.",
        comparisons=[],
        recommendations=[],
        limitations=[],
    ).model_dump(mode="json")
    app.session_state["preview_document"] = parsed.model_dump(mode="json")
    app.session_state["preview_file_bytes"] = None
    app.session_state["lesson_plan_preview_document"] = parsed.model_dump(mode="json")
    app.session_state["lesson_plan_preview_file_bytes"] = None
    app.session_state["teaching_preview_documents"] = [
        parsed.model_dump(mode="json")
    ]
    app.session_state["teaching_preview_file_bytes"] = [None]
    app.session_state["answer_key_preview_document"] = parsed.model_dump(mode="json")
    app.session_state["answer_key_preview_file_bytes"] = None
    app.session_state["learning_material_file_name"] = "material.docx"
    app.session_state["lesson_plan_file_name"] = "lesson-plan.docx"
    app.session_state["teaching_file_names"] = ["slides.docx"]
    app.session_state["answer_key_file_name"] = "key.docx"
    app.session_state["analysis_metadata"] = {"analysis_mode": "full"}
    app.session_state["ai_usage_summary"] = AIUsageSummary(
        call_count=2,
        input_tokens=10_000,
        cached_input_tokens=0,
        cache_write_tokens=0,
        output_tokens=2_000,
        reasoning_tokens=500,
        estimated_cost_usd=0.055,
        records=[],
    ).model_dump(mode="json")
    app.run()
    assert not app.exception
    assert any(metric.label == "Tổng" for metric in app.metric)
    assert any(metric.label == "Chi phí ước tính" for metric in app.metric)
    assert any("Nội dung sai" in markdown.value for markdown in app.markdown)
