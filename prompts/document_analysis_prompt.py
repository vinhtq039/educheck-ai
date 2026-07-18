from __future__ import annotations

import json
from collections.abc import Mapping

from schemas.lesson_plan import LessonPlanProfile


CHECK_LABELS = {
    "vi_spelling": "Chính tả tiếng Việt",
    "vi_grammar": "Ngữ pháp và diễn đạt tiếng Việt",
    "en_spelling": "Chính tả tiếng Anh",
    "en_grammar": "Ngữ pháp và diễn đạt tiếng Anh",
    "prompt_quality": "Độ rõ ràng và đầy đủ của đề bài",
    "qa": "Tính đúng đắn của câu hỏi và đáp án",
    "suitability": "Mức độ phù hợp với giáo án",
    "replacement": "Câu hỏi thay thế khi thực sự cần thiết",
}


def build_analysis_prompt(
    *,
    document_type: str,
    content: str,
    metadata: Mapping[str, str],
    lesson_plan: LessonPlanProfile,
    selected_checks: list[str],
    chunk_label: str,
) -> str:
    checks = "\n".join(f"- {CHECK_LABELS[key]}" for key in selected_checks)
    custom_request = metadata.get("custom_request", "").strip() or "(không có)"
    extracted = (
        content
        if content.strip()
        else "(Không có văn bản trích xuất; đọc trực tiếp PDF học liệu.)"
    )
    lesson_plan_context = json.dumps(
        lesson_plan.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return f"""
Nhiệm vụ: phân tích {chunk_label} của HỌC LIỆU {document_type.upper()}.

Thành công khi:
- phát hiện đủ vấn đề thuộc các nhóm đã bật nhưng không báo khác biệt văn phong;
- mọi issue có nguyên văn và vị trí kiểm chứng được trong phần học liệu này;
- vấn đề về độ phù hợp nêu đúng căn cứ từ hồ sơ giáo án;
- kết quả ngắn, không trùng và không suy đoán.

Nhóm kiểm tra:
{checks}

Yêu cầu riêng: {custom_request}

Quy tắc vị trí:
- PDF: page_number là số trang trong PDF của phần hiện tại.
- DOCX: dùng đúng block_id xuất hiện bên dưới.
- Không tạo issue cho nhóm kiểm tra đã tắt.

Hồ sơ giáo án:
--- BEGIN LESSON PLAN PROFILE ---
{lesson_plan_context}
--- END LESSON PLAN PROFILE ---

Nội dung học liệu:
--- BEGIN LEARNING MATERIAL CONTENT ---
{extracted}
--- END LEARNING MATERIAL CONTENT ---
""".strip()
