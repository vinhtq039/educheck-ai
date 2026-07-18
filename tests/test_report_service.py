from __future__ import annotations

import io
import json

from docx import Document

from schemas.analysis import AnalysisResult, DocumentSummary
from schemas.lesson_plan import LessonPlanProfile
from services.report_service import create_docx_report, create_json_report


def empty_result() -> AnalysisResult:
    return AnalysisResult(
        document_summary=DocumentSummary(
            document_type="docx",
            detected_languages=["vi"],
            summary="Tài liệu ngắn.",
        ),
        issues=[],
        general_recommendations=[],
        limitations=[],
    )


def test_json_report_is_utf8_and_valid() -> None:
    payload = json.loads(create_json_report(empty_result()).decode("utf-8"))
    assert payload["document_summary"]["summary"] == "Tài liệu ngắn."


def test_docx_report_can_be_opened() -> None:
    payload = create_docx_report(empty_result(), "lesson.docx", {})
    document = Document(io.BytesIO(payload))
    assert "BÁO CÁO KIỂM TRA HỌC LIỆU" in document.paragraphs[0].text


def test_two_document_json_report_preserves_lesson_plan_context() -> None:
    lesson_plan = LessonPlanProfile(
        source_document_type="docx",
        subject="Toán",
        topic="Phân số",
        objectives=["Nhận biết phân số."],
        summary="Giáo án về phân số.",
    )
    payload = json.loads(
        create_json_report(
            empty_result(),
            lesson_plan=lesson_plan,
            lesson_plan_file_name="giao-an.docx",
            learning_material_file_name="hoc-lieu.docx",
        ).decode("utf-8")
    )
    assert payload["lesson_plan_file_name"] == "giao-an.docx"
    assert payload["lesson_plan"]["subject"] == "Toán"
    assert "learning_material_analysis" in payload
