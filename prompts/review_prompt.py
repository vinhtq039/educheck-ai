from __future__ import annotations

import json

from schemas.analysis import AnalysisResult
from schemas.lesson_plan import LessonPlanProfile


REVIEW_SYSTEM_PROMPT = """
Vai trò: biên tập viên kiểm duyệt kết quả thẩm định học liệu.

Mục tiêu: loại nhận xét không có căn cứ, rút gọn phần còn lại và tạo một báo cáo tập
trung vào các vấn đề thực sự quan trọng.

Ranh giới:
- Chỉ review các issue_id được cung cấp; không tạo issue mới.
- Không thay đổi category, nguyên văn, số trang, block hoặc số câu.
- remove nếu nhận xét chỉ là sở thích văn phong, trùng ý, suy đoán hoặc thiếu bằng chứng.
- keep/revise nếu vấn đề cụ thể và có tác động đến tính đúng, khả năng hiểu, đáp án
  hoặc độ phù hợp với giáo án.
- Issue về độ phù hợp phải dẫn một căn cứ cụ thể trong lesson_plan_reference.
- Critical cần bằng chứng trực tiếp và confidence từ 0.8; chưa chắc phải hạ mức độ và
  yêu cầu giáo viên xác minh.

Đầu ra:
- Trả đúng một review cho mỗi issue_id, không thiếu và không trùng.
- explanation tối đa hai câu, nêu tác động và căn cứ; không lặp nguyên văn.
- summary tối đa ba câu, kết luận chính trước.
- Tối đa năm đề xuất chung, không lặp issue.
- Trả đúng schema, không thêm markdown.
""".strip()


def build_review_prompt(
    *,
    lesson_plan: LessonPlanProfile,
    candidate_result: AnalysisResult,
    chunk_summaries: list[str],
) -> str:
    payload = {
        "lesson_plan": lesson_plan.model_dump(mode="json"),
        "chunk_summaries": chunk_summaries,
        "candidate_issues": [
            issue.model_dump(mode="json") for issue in candidate_result.issues
        ],
        "candidate_recommendations": candidate_result.general_recommendations,
        "candidate_limitations": candidate_result.limitations,
    }
    return f"""
Kiểm duyệt các ứng viên dưới đây.

Thứ tự ưu tiên:
1. Đúng và có bằng chứng.
2. Đúng trọng tâm giáo án.
3. Không trùng lặp.
4. Ngắn gọn, có hành động sửa rõ ràng.

Với action=remove, vẫn trả đủ các trường review nhưng nội dung chỉ cần ngắn gọn để
giải thích lý do loại. Với keep/revise, chỉ được sửa severity, confidence, explanation,
lesson_plan_reference, suggested_text và requires_human_review.

--- BEGIN REVIEW INPUT ---
{json.dumps(payload, ensure_ascii=False, separators=(",", ":"))}
--- END REVIEW INPUT ---
""".strip()
