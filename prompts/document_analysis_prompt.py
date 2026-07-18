from __future__ import annotations

from collections.abc import Mapping


CHECK_LABELS = {
    "vi_spelling": "Chính tả tiếng Việt",
    "vi_grammar": "Ngữ pháp và diễn đạt tiếng Việt",
    "en_spelling": "Chính tả tiếng Anh",
    "en_grammar": "Ngữ pháp và diễn đạt tiếng Anh",
    "prompt_quality": "Độ rõ ràng và đầy đủ của đề bài",
    "qa": "Tính đúng đắn của câu hỏi và đáp án",
    "suitability": "Mức độ phù hợp học liệu",
    "replacement": "Đề xuất câu hỏi thay thế",
}


def build_analysis_prompt(
    *,
    document_type: str,
    content: str,
    metadata: Mapping[str, str],
    selected_checks: list[str],
    chunk_label: str,
) -> str:
    checks = "\n".join(f"- {CHECK_LABELS[key]}" for key in selected_checks)
    context = "\n".join(
        f"- {label}: {metadata.get(key) or '(không cung cấp)'}"
        for key, label in (
            ("subject", "Môn học"),
            ("grade", "Khối lớp"),
            ("topic", "Chủ đề"),
            ("objectives", "Mục tiêu bài học"),
            ("custom_request", "Yêu cầu riêng"),
        )
    )
    extracted = content if content.strip() else "(Không có văn bản trích xuất; đọc trực tiếp PDF.)"
    return f"""
Phân tích {chunk_label} của tài liệu {document_type.upper()}.

Ngữ cảnh:
{context}

Các nhóm kiểm tra được bật:
{checks}

Yêu cầu định vị:
- PDF: page_number là số trang trong chính PDF đầu vào hiện tại.
- DOCX: dùng đúng block_id xuất hiện trong nội dung.
- Không tạo issue thuộc nhóm kiểm tra đã tắt.

Nội dung trích xuất hỗ trợ định vị:
--- BEGIN DOCUMENT CONTENT ---
{extracted}
--- END DOCUMENT CONTENT ---
""".strip()

