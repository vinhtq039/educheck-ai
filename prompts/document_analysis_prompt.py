from __future__ import annotations

import json
from collections.abc import Mapping

from schemas.lesson_plan import LessonPlanProfile
from schemas.package import AnswerKeyProfile, TeachingContextProfile


CHECK_LABELS = {
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
    teaching_context: TeachingContextProfile | None = None,
    answer_key: AnswerKeyProfile | None = None,
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
    teaching_context_json = json.dumps(
        teaching_context.model_dump(mode="json")
        if teaching_context is not None
        else {"summary": "Không cung cấp tài liệu giảng dạy."},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    answer_key_json = json.dumps(
        {
            "target_scope": answer_key.target_scope.model_dump(mode="json"),
            "entries": [
                {
                    "question_number": entry.question_number,
                    "official_answer": entry.official_answer,
                }
                for entry in answer_key.entries
            ],
            "limitations": answer_key.limitations,
        }
        if answer_key is not None
        else {"entries": [], "limitations": ["Không cung cấp file đáp án."]},
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
- Không kiểm tra hoặc tạo issue về chính tả, ngữ pháp hay cách diễn đạt tiếng Việt.
- Đáp án chính thức do giáo viên cung cấp là nguồn chuẩn trong lần kiểm tra này.
- Không kết luận đáp án sai, không có đáp án đúng hoặc có nhiều đáp án đúng chỉ vì
  lời giải riêng của AI khác đáp án chính thức.
- Nếu không đọc hoặc không ghép chắc chắn được một mục đáp án, ghi vào limitations;
  không biến lỗi trích xuất thành lỗi của học liệu.
- Không báo lỗi chỉ vì sở thích văn phong, cách xuống dòng, độ rộng, nhãn trình bày
  hoặc vì có một cách diễn đạt khác vẫn đúng và dễ hiểu.

Hồ sơ giáo án:
--- BEGIN LESSON PLAN PROFILE ---
{lesson_plan_context}
--- END LESSON PLAN PROFILE ---

Nội dung đã dạy được trích xuất từ tài liệu giảng dạy:
--- BEGIN TEACHING CONTEXT ---
{teaching_context_json}
--- END TEACHING CONTEXT ---

Đáp án chính thức đã trích xuất:
--- BEGIN TRUSTED ANSWER KEY ---
{answer_key_json}
--- END TRUSTED ANSWER KEY ---

Nội dung học liệu:
--- BEGIN LEARNING MATERIAL CONTENT ---
{extracted}
--- END LEARNING MATERIAL CONTENT ---
""".strip()
