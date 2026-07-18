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


def create_json_report(result: AnalysisResult) -> bytes:
    return json.dumps(
        result.model_dump(mode="json"),
        ensure_ascii=False,
        indent=2,
    ).encode("utf-8")


def create_docx_report(
    result: AnalysisResult,
    file_name: str,
    metadata: Mapping[str, str],
    analyzed_at: datetime | None = None,
) -> bytes:
    document = Document()
    styles = document.styles
    styles["Normal"].font.name = "Arial"
    styles["Normal"].font.size = Pt(10.5)

    title = document.add_heading("BÁO CÁO KIỂM TRA HỌC LIỆU", level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    analyzed_at = analyzed_at or datetime.now().astimezone()
    document.add_paragraph(f"Tài liệu: {file_name}")
    document.add_paragraph(f"Thời điểm phân tích: {analyzed_at:%d/%m/%Y %H:%M}")
    for key, label in (
        ("subject", "Môn học"),
        ("grade", "Khối lớp"),
        ("topic", "Chủ đề"),
        ("objectives", "Mục tiêu bài học"),
    ):
        if metadata.get(key):
            document.add_paragraph(f"{label}: {metadata[key]}")

    summary = result.document_summary
    document.add_heading("1. Tóm tắt", level=1)
    document.add_paragraph(summary.summary)
    document.add_paragraph(
        f"Loại tài liệu: {summary.document_type} | "
        f"Ngôn ngữ: {', '.join(summary.detected_languages) or 'Không xác định'}"
    )
    if summary.total_questions is not None:
        document.add_paragraph(f"Tổng số câu hỏi: {summary.total_questions}")

    document.add_heading("2. Thống kê vấn đề", level=1)
    severity_counts = Counter(issue.severity.value for issue in result.issues)
    document.add_paragraph(
        f"Tổng cộng: {len(result.issues)} | "
        f"Nghiêm trọng: {severity_counts['critical']} | "
        f"Cảnh báo: {severity_counts['warning']} | "
        f"Gợi ý: {severity_counts['suggestion']}"
    )

    document.add_heading("3. Danh sách vấn đề", level=1)
    if not result.issues:
        document.add_paragraph("Không phát hiện vấn đề trong phạm vi đã chọn.")
    for index, issue in enumerate(result.issues, start=1):
        location = (
            f"Trang {issue.page_number}"
            if issue.page_number
            else issue.block_id or issue.section_title or "Không xác định"
        )
        document.add_heading(
            f"{index}. {issue.category.value} — {issue.severity.value}", level=2
        )
        document.add_paragraph(
            f"Vị trí: {location}"
            + (f" | Câu: {issue.question_number}" if issue.question_number else "")
            + f" | Độ tin cậy: {issue.confidence:.0%}"
        )
        document.add_paragraph(f"Nội dung gốc: {issue.original_text}")
        document.add_paragraph(f"Giải thích: {issue.explanation}")
        if issue.suggested_text:
            document.add_paragraph(f"Đề xuất sửa: {issue.suggested_text}")
        if issue.replacement_question:
            document.add_paragraph(f"Câu hỏi thay thế: {issue.replacement_question}")
        if issue.suggested_answer:
            document.add_paragraph(f"Đáp án gợi ý: {issue.suggested_answer}")
        if issue.requires_human_review:
            document.add_paragraph("Lưu ý: Cần người dùng xác minh.")

    document.add_heading("4. Đề xuất chung", level=1)
    for recommendation in result.general_recommendations:
        document.add_paragraph(recommendation, style="List Bullet")
    if not result.general_recommendations:
        document.add_paragraph("Không có đề xuất chung.")

    document.add_heading("5. Giới hạn", level=1)
    for limitation in result.limitations:
        document.add_paragraph(limitation, style="List Bullet")
    document.add_paragraph(
        "Kết quả AI chỉ mang tính hỗ trợ và không thay thế thẩm định của giáo viên."
    )

    stream = io.BytesIO()
    document.save(stream)
    return stream.getvalue()

