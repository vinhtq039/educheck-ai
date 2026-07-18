from __future__ import annotations

import io
import json
from collections import Counter
from datetime import datetime
from typing import Mapping

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt

from schemas.analysis import AnalysisResult
from schemas.lesson_plan import AnalysisPackage, LessonPlanProfile


def create_json_report(
    result: AnalysisResult,
    *,
    lesson_plan: LessonPlanProfile | None = None,
    lesson_plan_file_name: str | None = None,
    learning_material_file_name: str | None = None,
) -> bytes:
    payload = (
        AnalysisPackage(
            lesson_plan_file_name=lesson_plan_file_name or "lesson-plan",
            learning_material_file_name=learning_material_file_name or "learning-material",
            lesson_plan=lesson_plan,
            learning_material_analysis=result,
        ).model_dump(mode="json")
        if lesson_plan is not None
        else result.model_dump(mode="json")
    )
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


def _add_bullets(document: Document, title: str, values: list[str]) -> None:
    if not values:
        return
    if title:
        document.add_paragraph(title)
    for value in values:
        document.add_paragraph(value, style="List Bullet")


def create_docx_report(
    result: AnalysisResult,
    file_name: str,
    metadata: Mapping[str, str],
    analyzed_at: datetime | None = None,
    *,
    lesson_plan: LessonPlanProfile | None = None,
    lesson_plan_file_name: str | None = None,
) -> bytes:
    document = Document()
    styles = document.styles
    styles["Normal"].font.name = "Arial"
    styles["Normal"].font.size = Pt(10.5)

    title = document.add_heading("BÁO CÁO KIỂM TRA HỌC LIỆU", level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    analyzed_at = analyzed_at or datetime.now().astimezone()
    document.add_paragraph(f"Học liệu: {file_name}")
    if lesson_plan_file_name:
        document.add_paragraph(f"Giáo án đối chiếu: {lesson_plan_file_name}")
    document.add_paragraph(f"Thời điểm phân tích: {analyzed_at:%d/%m/%Y %H:%M}")
    if metadata.get("custom_request"):
        document.add_paragraph(f"Yêu cầu riêng: {metadata['custom_request']}")

    section = 1
    if lesson_plan is not None:
        document.add_heading(f"{section}. Căn cứ từ giáo án", level=1)
        section += 1
        document.add_paragraph(lesson_plan.summary)
        for label, value in (
            ("Môn học", lesson_plan.subject),
            ("Khối/lớp", lesson_plan.grade_level),
            ("Chủ đề", lesson_plan.topic),
        ):
            if value:
                document.add_paragraph(f"{label}: {value}")
        _add_bullets(document, "Mục tiêu bài học:", lesson_plan.objectives)
        _add_bullets(document, "Phạm vi kiến thức:", lesson_plan.knowledge_scope)
        _add_bullets(document, "Tiêu chí đánh giá:", lesson_plan.assessment_criteria)
        _add_bullets(
            document,
            "Thông tin giáo án cần xác minh:",
            lesson_plan.uncertainties,
        )

    summary = result.document_summary
    document.add_heading(f"{section}. Tóm tắt học liệu", level=1)
    section += 1
    document.add_paragraph(summary.summary)
    document.add_paragraph(
        f"Loại tài liệu: {summary.document_type} | "
        f"Ngôn ngữ: {', '.join(summary.detected_languages) or 'Không xác định'}"
    )
    if summary.total_questions is not None:
        document.add_paragraph(f"Tổng số câu hỏi: {summary.total_questions}")

    document.add_heading(f"{section}. Thống kê vấn đề", level=1)
    section += 1
    severity_counts = Counter(issue.severity.value for issue in result.issues)
    document.add_paragraph(
        f"Tổng cộng: {len(result.issues)} | "
        f"Nghiêm trọng: {severity_counts['critical']} | "
        f"Cảnh báo: {severity_counts['warning']} | "
        f"Gợi ý: {severity_counts['suggestion']}"
    )

    document.add_heading(f"{section}. Danh sách vấn đề trong học liệu", level=1)
    section += 1
    if not result.issues:
        document.add_paragraph("Không phát hiện vấn đề trong phạm vi đã chọn.")
    for index, issue in enumerate(result.issues, start=1):
        location = (
            f"Trang {issue.page_number}"
            if issue.page_number
            else issue.block_id or issue.section_title or "Không xác định"
        )
        document.add_heading(
            f"{index}. {issue.category.value} — {issue.severity.value}",
            level=2,
        )
        document.add_paragraph(
            f"Vị trí: {location}"
            + (f" | Câu: {issue.question_number}" if issue.question_number else "")
            + f" | Độ tin cậy: {issue.confidence:.0%}"
        )
        document.add_paragraph(f"Nội dung gốc: {issue.original_text}")
        document.add_paragraph(f"Giải thích: {issue.explanation}")
        if issue.lesson_plan_reference:
            document.add_paragraph(
                f"Căn cứ từ giáo án: {issue.lesson_plan_reference}"
            )
        if issue.suggested_text:
            document.add_paragraph(f"Đề xuất sửa: {issue.suggested_text}")
        if issue.replacement_question:
            document.add_paragraph(f"Câu hỏi thay thế: {issue.replacement_question}")
        if issue.suggested_answer:
            document.add_paragraph(f"Đáp án gợi ý: {issue.suggested_answer}")
        if issue.requires_human_review:
            document.add_paragraph("Lưu ý: Cần người dùng xác minh.")

    document.add_heading(f"{section}. Đề xuất chung", level=1)
    section += 1
    _add_bullets(document, "", result.general_recommendations)
    if not result.general_recommendations:
        document.add_paragraph("Không có đề xuất chung.")

    document.add_heading(f"{section}. Giới hạn", level=1)
    _add_bullets(document, "", result.limitations)
    document.add_paragraph(
        "Kết quả AI chỉ mang tính hỗ trợ và không thay thế thẩm định của giáo viên."
    )

    stream = io.BytesIO()
    document.save(stream)
    return stream.getvalue()
