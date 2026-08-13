from __future__ import annotations

import html
from collections import Counter

import streamlit as st

from config.settings import get_settings
from schemas.analysis import AnalysisResult, IssueCategory, IssueSeverity
from schemas.document import DocumentType, ParsedDocument
from schemas.lesson_plan import LessonPlanProfile
from schemas.package import (
    AnswerKeyProfile,
    ComparisonStatus,
    PackageComparisonResult,
    StudentQuestionSet,
    TeachingContextProfile,
)
from schemas.usage import AIUsageSummary
from services.analysis_service import analyze_document, analyze_lesson_plan
from services.cleanup_service import clear_analysis_results, clear_analysis_state
from services.document_service import parse_document
from services.openai_service import OpenAIService, OpenAIServiceError
from services.package_analysis_service import (
    SourceDocument,
    analyze_teaching_materials,
    build_quick_analysis_result,
    compare_learning_package,
    extract_answer_key,
    solve_student_material,
)
from services.package_result_service import (
    ACTIONABLE_STATUSES,
    package_decision,
    package_statistics,
)
from services.preview_service import render_pdf_page_preview
from services.report_service import (
    create_package_docx_report,
    create_package_json_report,
)
from utils.file_utils import file_hash, format_file_size, safe_report_stem
from utils.validators import FileValidationError


CHECKS = {
    "en_spelling": "Chính tả tiếng Anh",
    "en_grammar": "Ngữ pháp và diễn đạt tiếng Anh",
    "prompt_quality": "Kiểm tra đề bài",
    "qa": "Kiểm tra câu hỏi và đáp án",
    "suitability": "Đối chiếu với giáo án và nội dung đã dạy",
    "replacement": "Đề xuất câu hỏi thay thế",
}

CATEGORY_LABELS = {
    IssueCategory.ENGLISH_SPELLING.value: "Chính tả tiếng Anh",
    IssueCategory.ENGLISH_GRAMMAR.value: "Ngữ pháp tiếng Anh",
    IssueCategory.ENGLISH_EXPRESSION.value: "Diễn đạt tiếng Anh",
    IssueCategory.AMBIGUOUS_QUESTION.value: "Câu hỏi mơ hồ",
    IssueCategory.MISSING_INFORMATION.value: "Thiếu dữ kiện",
    IssueCategory.CONFLICTING_INFORMATION.value: "Dữ kiện mâu thuẫn",
    IssueCategory.INCORRECT_ANSWER.value: "Đáp án có khả năng sai",
    IssueCategory.NO_CORRECT_ANSWER.value: "Không có đáp án đúng",
    IssueCategory.MULTIPLE_CORRECT_ANSWERS.value: "Nhiều đáp án đúng",
    IssueCategory.DUPLICATE_QUESTION.value: "Câu hỏi trùng",
    IssueCategory.DUPLICATE_OPTION.value: "Phương án trùng",
    IssueCategory.QUESTION_ANSWER_MISMATCH.value: "Câu hỏi và đáp án không khớp",
    IssueCategory.OUT_OF_SCOPE.value: "Ngoài phạm vi",
    IssueCategory.GRADE_LEVEL_MISMATCH.value: "Không phù hợp khối lớp",
    IssueCategory.LEARNING_OBJECTIVE_MISMATCH.value: "Không phù hợp mục tiêu",
    IssueCategory.UNCERTAIN_CONTENT.value: "Nội dung cần xác minh",
}
SEVERITY_LABELS = {
    IssueSeverity.CRITICAL.value: "Nghiêm trọng",
    IssueSeverity.WARNING.value: "Cảnh báo",
    IssueSeverity.SUGGESTION.value: "Gợi ý",
}
SEVERITY_HEX = {
    IssueSeverity.CRITICAL.value: "#dc2626",
    IssueSeverity.WARNING.value: "#f59e0b",
    IssueSeverity.SUGGESTION.value: "#2580d9",
}
COMPARISON_LABELS = {
    ComparisonStatus.MATCH.value: "Khớp",
    ComparisonStatus.CONFLICT.value: "Cần xác minh xung đột",
    ComparisonStatus.AI_DISAGREEMENT.value: "AI chưa đồng thuận",
    ComparisonStatus.AMBIGUOUS.value: "Chưa rõ",
    ComparisonStatus.MISSING_KEY.value: "Thiếu đáp án đã xác nhận",
    ComparisonStatus.KEY_EXTRACTION_UNCERTAIN.value: "Chưa đọc được đáp án",
    ComparisonStatus.ORPHAN_KEY.value: "Ngoài phạm vi/chưa ghép",
    ComparisonStatus.VERSION_MISMATCH.value: "Khác phiên bản",
}
COMPARISON_COLORS = {
    ComparisonStatus.MATCH.value: "green",
    ComparisonStatus.CONFLICT.value: "red",
    ComparisonStatus.AI_DISAGREEMENT.value: "gray",
    ComparisonStatus.AMBIGUOUS.value: "orange",
    ComparisonStatus.MISSING_KEY.value: "orange",
    ComparisonStatus.KEY_EXTRACTION_UNCERTAIN.value: "orange",
    ComparisonStatus.ORPHAN_KEY.value: "gray",
    ComparisonStatus.VERSION_MISMATCH.value: "red",
}


def init_state() -> None:
    defaults = {
        "analysis_status": "IDLE",
        "analysis_result": None,
        "lesson_plan_profile": None,
        "teaching_context_profile": None,
        "student_question_set": None,
        "answer_key_profile": None,
        "package_comparison_result": None,
        "analysis_error": None,
        "ai_usage_summary": None,
        "uploader_version": 0,
        "lesson_profile_cache": {},
        "teaching_context_cache": {},
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def _uploaded_identity(files: list[tuple[str, bytes]]) -> str:
    payload = b""
    for role, (name, data) in enumerate(files):
        payload += str(role).encode() + b"\0" + name.encode("utf-8") + b"\0" + data
    return file_hash(payload)


def _cache_put(cache: dict, key: str, value: dict, limit: int = 8) -> None:
    cache[key] = value
    while len(cache) > limit:
        cache.pop(next(iter(cache)))


def reset_for_new_inputs(identity: str) -> None:
    if st.session_state.get("uploaded_file_hash") == identity:
        return
    clear_analysis_state(st.session_state)
    st.session_state.uploaded_file_hash = identity
    st.session_state.analysis_status = "IDLE"


def set_state_page(key: str, page_number: int) -> None:
    st.session_state[key] = page_number


def _numbered_issues(result: AnalysisResult | None):
    return list(enumerate(result.issues, start=1)) if result is not None else []


def render_pdf_preview(
    parsed: ParsedDocument,
    file_bytes: bytes,
    result: AnalysisResult | None,
    *,
    select_key: str,
) -> None:
    assert parsed.page_count is not None
    numbered = _numbered_issues(result)
    issue_counts = Counter(
        issue.page_number for _number, issue in numbered if issue.page_number is not None
    )
    first_issue_page = next(
        (
            issue.page_number
            for _number, issue in numbered
            if issue.page_number is not None
        ),
        1,
    )
    pages = list(range(1, parsed.page_count + 1))
    selected_page = st.selectbox(
        "Trang tài liệu",
        pages,
        index=max(0, min((first_issue_page or 1) - 1, len(pages) - 1)),
        format_func=lambda page: (
            f"Trang {page}"
            + (f" • {issue_counts[page]} vấn đề" if issue_counts[page] else "")
        ),
        key=select_key,
    )
    page_issues = [
        (number, issue)
        for number, issue in numbered
        if issue.page_number == selected_page
    ]
    parsed_page = next(page for page in parsed.pages if page.page_number == selected_page)
    preview = render_pdf_page_preview(file_bytes, parsed_page, page_issues)
    st.image(
        preview.image_bytes,
        caption=f"Trang {selected_page}/{parsed.page_count}",
        use_container_width=True,
    )
    for number, issue in page_issues:
        color = SEVERITY_HEX[issue.severity.value]
        st.markdown(
            f"<span style='color:{color};font-size:1.1rem'>●</span> "
            f"**#{number}** · {CATEGORY_LABELS[issue.category.value]}",
            unsafe_allow_html=True,
        )
    if preview.unmatched_issue_numbers:
        st.caption(
            "Một số vấn đề chỉ xác định được trang nên hệ thống đánh dấu viền trang."
        )


def render_docx_preview(
    parsed: ParsedDocument,
    result: AnalysisResult | None,
) -> None:
    numbered = _numbered_issues(result)
    located_numbers: set[int] = set()
    with st.container(height=690, border=True):
        for block in parsed.blocks:
            matches = [
                (number, issue)
                for number, issue in numbered
                if issue.block_id == block.block_id
                or (
                    not issue.block_id
                    and issue.section_title
                    and block.block_type == "heading"
                    and issue.section_title == block.section_title
                )
            ]
            located_numbers.update(number for number, _issue in matches)
            if matches:
                top_issue = min(
                    (issue for _number, issue in matches),
                    key=lambda issue: {
                        IssueSeverity.CRITICAL: 0,
                        IssueSeverity.WARNING: 1,
                        IssueSeverity.SUGGESTION: 2,
                    }[issue.severity],
                )
                color = SEVERITY_HEX[top_issue.severity.value]
                background = f"{color}18"
                labels = " ".join(
                    f"<strong>#{number}</strong>" for number, _issue in matches
                )
            else:
                color = "#d1d5db"
                background = "transparent"
                labels = ""
            text = html.escape(block.text).replace("\n", "<br>")
            block_label = html.escape(block.section_title or block.block_type.capitalize())
            st.markdown(
                f"""
                <div style="border-left:5px solid {color};background:{background};
                            padding:0.65rem 0.8rem;margin:0.35rem 0;border-radius:0 8px 8px 0">
                  <div style="font-size:0.75rem;color:#6b7280;margin-bottom:0.25rem">
                    {html.escape(block.block_id)} · {block_label} {labels}
                  </div>
                  <div style="white-space:normal">{text}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
    unlocated = {number for number, _issue in numbered} - located_numbers
    if unlocated:
        st.caption(
            "Chưa xác định chính xác block cho: "
            + ", ".join(f"#{number}" for number in sorted(unlocated))
        )


def render_document_preview(
    parsed: ParsedDocument | None,
    file_bytes: bytes | None,
    result: AnalysisResult | None,
    *,
    select_key: str,
) -> None:
    if parsed is None:
        st.info("Không còn dữ liệu xem trước trong phiên này.")
        return
    if parsed.document_type == DocumentType.PDF:
        if file_bytes is None:
            st.info("Không còn dữ liệu PDF xem trước.")
            return
        render_pdf_preview(parsed, file_bytes, result, select_key=select_key)
    else:
        render_docx_preview(parsed, result)


def render_lesson_context(
    lesson_plan: LessonPlanProfile,
    teaching_context: TeachingContextProfile,
) -> None:
    with st.expander("Căn cứ giáo án và nội dung đã dạy", expanded=False):
        st.markdown(
            f"**Môn:** {lesson_plan.subject or 'Chưa xác định'} · "
            f"**Khối/lớp:** {lesson_plan.grade_level or 'Chưa xác định'} · "
            f"**Chủ đề:** {lesson_plan.topic or 'Chưa xác định'}"
        )
        st.write(lesson_plan.summary)
        if lesson_plan.objectives:
            st.markdown("**Mục tiêu**")
            for item in lesson_plan.objectives:
                st.markdown(f"- {item}")
        st.markdown("**Nội dung thực tế từ tài liệu giảng dạy**")
        st.write(teaching_context.summary)
        for item in teaching_context.covered_content:
            st.markdown(f"- {item}")


def render_usage_panel(usage: AIUsageSummary | None) -> None:
    st.markdown("### Chi phí AI của lượt này")
    if usage is None:
        st.caption("Chưa có dữ liệu token cho lượt phân tích này.")
        return
    columns = st.columns(4)
    columns[0].metric("Chi phí ước tính", f"${usage.estimated_cost_usd:.4f}")
    columns[1].metric("Lượt gọi API", usage.call_count)
    columns[2].metric("Input token", f"{usage.input_tokens:,}")
    columns[3].metric("Output token", f"{usage.output_tokens:,}")
    st.caption(
        "Ước tính theo giá Standard API; hóa đơn thực tế có thể khác nếu tài khoản "
        "dùng Priority, Batch, Flex hoặc chính sách giá riêng."
    )
    if usage.records:
        stage_labels = {
            "lesson_plan": "Giáo án",
            "teaching_context": "Tài liệu dạy",
            "question_extraction": "Tách câu hỏi",
            "student_solving": "Tự giải bài tập",
            "document_analysis": "Kiểm tra chi tiết",
            "answer_key": "Trích xuất đáp án",
            "package_comparison": "AI xác minh",
            "final_review": "Kiểm duyệt",
        }
        with st.expander("Chi tiết token và model theo công đoạn"):
            st.dataframe(
                [
                    {
                        "Công đoạn": stage_labels.get(item.stage, item.stage),
                        "Model": item.model,
                        "Suy luận": item.reasoning_effort,
                        "Lần thử": item.attempt,
                        "Input": item.input_tokens,
                        "Cached": item.cached_input_tokens,
                        "Output": item.output_tokens,
                        "Reasoning": item.reasoning_tokens,
                        "Chi phí USD": round(item.estimated_cost_usd, 6),
                    }
                    for item in usage.records
                ],
                hide_index=True,
                use_container_width=True,
            )


def render_comparison_panel(
    comparison: PackageComparisonResult,
    questions: StudentQuestionSet,
    answer_key: AnswerKeyProfile,
) -> None:
    st.markdown("### Kết luận kiểm tra")
    stats = package_statistics(questions, answer_key, comparison)
    decision, decision_detail = package_decision(stats)
    if decision == "Có thể sử dụng":
        st.success(f"**{decision}** — {decision_detail}")
    elif decision == "Cần giáo viên xác minh":
        st.warning(f"**{decision}** — {decision_detail}")
    else:
        st.info(f"**{decision}** — {decision_detail}")

    cols = st.columns(5)
    cols[0].metric("Câu trong bài tập", stats.question_count)
    cols[1].metric("Khớp", stats.match_count)
    cols[2].metric("AI trả lời khác", stats.ai_disagreement_count)
    cols[3].metric("Cần xác minh", stats.actionable_count)
    cols[4].metric("Ngoài phạm vi", stats.outside_scope_count)
    st.caption(comparison.summary)
    if stats.ai_disagreement_count:
        st.info(
            "AI trả lời khác đáp án giáo viên không được tính là lỗi của học liệu. "
            "Bật “Hiện toàn bộ chi tiết đối chiếu” nếu muốn tham khảo."
        )

    question_by_id = {item.question_id: item for item in questions.questions}
    answer_by_id = {item.entry_id: item for item in answer_key.entries}
    show_all = st.checkbox(
        "Hiện toàn bộ chi tiết đối chiếu",
        value=False,
        key="comparison_show_all",
    )

    actionable = [
        item for item in comparison.comparisons if item.status in ACTIONABLE_STATUSES
    ]
    displayed = comparison.comparisons if show_all else actionable[:5]
    if not displayed:
        st.success("Không có mục đối chiếu nào cần xử lý.")
        return
    if not show_all and len(actionable) > 5:
        st.caption(
            f"Đang hiện 5/{len(actionable)} mục ưu tiên. "
            "Bật “Hiện toàn bộ chi tiết đối chiếu” để xem tất cả."
        )
    for index, item in enumerate(displayed, start=1):
        label = COMPARISON_LABELS[item.status.value]
        color = COMPARISON_COLORS[item.status.value]
        with st.expander(f"Câu {item.question_number} · {label}"):
            st.markdown(
                f"<span style='color:{color}'>●</span> **{label}** · "
                f"Độ tin cậy {item.confidence:.0%}",
                unsafe_allow_html=True,
            )
            st.markdown(f"**AI tự giải:** {item.independent_answer or 'Không xác định'}")
            st.markdown(f"**Đáp án chính thức:** {item.official_answer or 'Không có'}")
            st.markdown(f"**Nhận xét:** {item.explanation}")
            if item.lesson_plan_reference:
                st.markdown(f"**Căn cứ giáo án:** {item.lesson_plan_reference}")
            if item.teaching_material_reference:
                st.markdown(
                    f"**Căn cứ tài liệu dạy:** {item.teaching_material_reference}"
                )
            buttons = st.columns(2)
            question = question_by_id.get(item.material_question_id or "")
            if question and question.page_number:
                buttons[0].button(
                    f"Xem bài tập trang {question.page_number}",
                    key=f"comparison_material_page_{index}",
                    on_click=set_state_page,
                    args=("preview_pdf_page", question.page_number),
                    use_container_width=True,
                )
            answer = answer_by_id.get(item.answer_key_entry_id or "")
            if answer and answer.page_number:
                buttons[1].button(
                    f"Xem đáp án trang {answer.page_number}",
                    key=f"comparison_answer_page_{index}",
                    on_click=set_state_page,
                    args=("answer_key_preview_pdf_page", answer.page_number),
                    use_container_width=True,
                )
            if item.requires_human_review:
                st.warning("Kết quả này cần giáo viên xác minh.")
    if answer_key.ignored_scope_notes:
        with st.expander("Các phần đáp án đã bỏ qua vì ngoài phạm vi"):
            for note in answer_key.ignored_scope_notes:
                st.markdown(f"- {note}")


def render_issue_panel(result: AnalysisResult) -> None:
    st.markdown("### Vấn đề trong bản thân học liệu")
    counts = Counter(issue.severity.value for issue in result.issues)
    cols = st.columns(4)
    cols[0].metric("Tổng", len(result.issues))
    cols[1].metric("Nghiêm trọng", counts["critical"])
    cols[2].metric("Cảnh báo", counts["warning"])
    cols[3].metric("Gợi ý", counts["suggestion"])
    st.write(result.document_summary.summary)

    with st.expander("Bộ lọc lỗi", expanded=False):
        col1, col2 = st.columns(2)
        severities = col1.multiselect(
            "Mức độ",
            list(SEVERITY_LABELS),
            format_func=lambda value: SEVERITY_LABELS[value],
        )
        categories = col2.multiselect(
            "Nhóm lỗi",
            sorted({issue.category.value for issue in result.issues}),
            format_func=lambda value: CATEGORY_LABELS.get(value, value),
        )
        keyword = st.text_input("Từ khóa lỗi")

    filtered = []
    for number, issue in _numbered_issues(result):
        haystack = f"{issue.original_text} {issue.explanation}".casefold()
        if severities and issue.severity.value not in severities:
            continue
        if categories and issue.category.value not in categories:
            continue
        if keyword and keyword.casefold() not in haystack:
            continue
        filtered.append((number, issue))

    for number, issue in filtered:
        location = (
            f"Trang {issue.page_number}"
            if issue.page_number
            else issue.block_id or issue.section_title or "Chưa xác định"
        )
        with st.expander(
            f"#{number} · {SEVERITY_LABELS[issue.severity.value]} · "
            f"{CATEGORY_LABELS.get(issue.category.value, issue.category.value)} · {location}"
        ):
            if issue.page_number:
                st.button(
                    f"Xem trang {issue.page_number} bên trái",
                    key=f"show_issue_page_{number}",
                    on_click=set_state_page,
                    args=("preview_pdf_page", issue.page_number),
                    use_container_width=True,
                )
            st.code(issue.original_text, language=None, wrap_lines=True)
            st.markdown(f"**Giải thích:** {issue.explanation}")
            if issue.lesson_plan_reference:
                st.markdown(f"**Căn cứ:** {issue.lesson_plan_reference}")
            if issue.suggested_text:
                st.markdown(f"**Đề xuất sửa:** {issue.suggested_text}")
            if issue.replacement_question:
                st.markdown(f"**Câu thay thế:** {issue.replacement_question}")
            if issue.suggested_answer:
                st.markdown(f"**Đáp án gợi ý:** {issue.suggested_answer}")
            if issue.requires_human_review:
                st.warning("Vấn đề này cần giáo viên xác minh.")


def render_result(
    *,
    result: AnalysisResult,
    lesson_plan: LessonPlanProfile,
    teaching_context: TeachingContextProfile,
    questions: StudentQuestionSet,
    answer_key: AnswerKeyProfile,
    comparison: PackageComparisonResult,
    metadata: dict[str, str],
    usage: AIUsageSummary | None,
) -> None:
    st.divider()
    st.subheader("Kết quả phân tích bộ học liệu")
    document_column, report_column = st.columns([1.15, 1], gap="large")

    material_parsed = ParsedDocument.model_validate(st.session_state.preview_document)
    lesson_parsed = ParsedDocument.model_validate(
        st.session_state.lesson_plan_preview_document
    )
    answer_parsed = ParsedDocument.model_validate(
        st.session_state.answer_key_preview_document
    )
    teaching_parsed = [
        ParsedDocument.model_validate(item)
        for item in st.session_state.teaching_preview_documents
    ]

    with document_column:
        with st.container(height=1000, border=True):
            material_tab_label = (
                "Bài tập đã đánh dấu"
                if metadata.get("analysis_mode") == "full"
                else "Bài tập"
            )
            tabs = st.tabs(
                [material_tab_label, "Đáp án", "Tài liệu dạy", "Giáo án"]
            )
            with tabs[0]:
                st.caption(st.session_state.learning_material_file_name)
                render_document_preview(
                    material_parsed,
                    st.session_state.preview_file_bytes,
                    result,
                    select_key="preview_pdf_page",
                )
            with tabs[1]:
                st.caption(st.session_state.answer_key_file_name)
                render_document_preview(
                    answer_parsed,
                    st.session_state.answer_key_preview_file_bytes,
                    None,
                    select_key="answer_key_preview_pdf_page",
                )
            with tabs[2]:
                teaching_tabs = st.tabs(st.session_state.teaching_file_names)
                for index, teaching_tab in enumerate(teaching_tabs):
                    with teaching_tab:
                        render_document_preview(
                            teaching_parsed[index],
                            st.session_state.teaching_preview_file_bytes[index],
                            None,
                            select_key=f"teaching_preview_pdf_page_{index}",
                        )
            with tabs[3]:
                st.caption(st.session_state.lesson_plan_file_name)
                render_document_preview(
                    lesson_parsed,
                    st.session_state.lesson_plan_preview_file_bytes,
                    None,
                    select_key="lesson_plan_preview_pdf_page",
                )

    with report_column:
        with st.container(height=1000, border=True):
            render_usage_panel(usage)
            st.divider()
            render_lesson_context(lesson_plan, teaching_context)
            render_comparison_panel(comparison, questions, answer_key)
            if metadata.get("analysis_mode") == "full":
                st.divider()
                render_issue_panel(result)
            else:
                with st.expander("Kiểm tra chi tiết tiếng Anh và chất lượng đề"):
                    st.info(
                        "Chưa chạy trong chế độ Kiểm tra nhanh. "
                        "Chọn “Phân tích toàn diện” nếu cần rà soát tiếng Anh và chất lượng đề."
                    )
            st.divider()
            stem = safe_report_stem(st.session_state.learning_material_file_name)
            left, right = st.columns(2)
            left.download_button(
                "Tải báo cáo DOCX",
                create_package_docx_report(
                    result=result,
                    lesson_plan=lesson_plan,
                    teaching_context=teaching_context,
                    questions=questions,
                    answer_key=answer_key,
                    comparison=comparison,
                    lesson_plan_file_name=st.session_state.lesson_plan_file_name,
                    teaching_file_names=st.session_state.teaching_file_names,
                    learning_material_file_name=st.session_state.learning_material_file_name,
                    answer_key_file_name=st.session_state.answer_key_file_name,
                    metadata=metadata,
                    usage=usage,
                ),
                file_name=f"{stem}-package-report.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                use_container_width=True,
            )
            right.download_button(
                "Tải kết quả JSON",
                create_package_json_report(
                    result=result,
                    lesson_plan=lesson_plan,
                    teaching_context=teaching_context,
                    questions=questions,
                    answer_key=answer_key,
                    comparison=comparison,
                    lesson_plan_file_name=st.session_state.lesson_plan_file_name,
                    teaching_file_names=st.session_state.teaching_file_names,
                    learning_material_file_name=st.session_state.learning_material_file_name,
                    answer_key_file_name=st.session_state.answer_key_file_name,
                    metadata=metadata,
                    usage=usage,
                ),
                file_name=f"{stem}-package-result.json",
                mime="application/json",
                use_container_width=True,
            )


def main() -> None:
    st.set_page_config(
        page_title="AI kiểm tra bộ học liệu",
        page_icon="📘",
        layout="wide",
    )
    init_state()
    settings = get_settings()

    st.title("AI kiểm tra bộ học liệu")
    st.caption(
        "Phân tích giáo án và nội dung đã dạy, tự giải bài tập độc lập, "
        "sau đó mới đối chiếu với đáp án chính thức."
    )
    st.markdown(
        "**Quy trình:** ① Giáo án → ② Tài liệu dạy → "
        "③ AI tự giải bài tập → ④ Trích xuất đáp án → ⑤ Đối chiếu"
    )
    st.caption(
        f"Định tuyến tiết kiệm: {settings.openai_model} đọc/trích xuất; "
        f"{settings.openai_solving_model} tự giải; "
        f"{settings.openai_escalation_model} xác minh trường hợp chưa kết luận."
    )

    row1_left, row1_right = st.columns(2, gap="large")
    with row1_left:
        st.markdown("### 1. Giáo án")
        lesson_upload = st.file_uploader(
            "Tải giáo án Word hoặc PDF",
            type=["docx", "pdf"],
            key=f"lesson_uploader_{st.session_state.uploader_version}",
            max_upload_size=settings.max_file_size_mb,
        )
    with row1_right:
        st.markdown("### 2. Tài liệu giảng dạy")
        teaching_uploads = st.file_uploader(
            "Tải slideshow, handout hoặc tài liệu tham chiếu",
            type=["docx", "pdf"],
            accept_multiple_files=True,
            key=f"teaching_uploader_{st.session_state.uploader_version}",
            max_upload_size=settings.max_file_size_mb,
        )
        st.caption(
            f"Tối đa {settings.max_teaching_files} file tài liệu giảng dạy."
        )

    row2_left, row2_right = st.columns(2, gap="large")
    with row2_left:
        st.markdown("### 3. Bài tập cần kiểm tra")
        material_upload = st.file_uploader(
            "Tải homework, worksheet hoặc bài kiểm tra",
            type=["docx", "pdf"],
            key=f"material_uploader_{st.session_state.uploader_version}",
            max_upload_size=settings.max_file_size_mb,
        )
    with row2_right:
        st.markdown("### 4. Đáp án")
        answer_upload = st.file_uploader(
            "Tải đáp án hoặc hướng dẫn chấm",
            type=["docx", "pdf"],
            key=f"answer_uploader_{st.session_state.uploader_version}",
            max_upload_size=settings.max_file_size_mb,
        )

    uploaded_groups = []
    if lesson_upload:
        uploaded_groups.append((lesson_upload.name, lesson_upload.getvalue()))
    for uploaded in teaching_uploads or []:
        uploaded_groups.append((uploaded.name, uploaded.getvalue()))
    if material_upload:
        uploaded_groups.append((material_upload.name, material_upload.getvalue()))
    if answer_upload:
        uploaded_groups.append((answer_upload.name, answer_upload.getvalue()))
    reset_for_new_inputs(_uploaded_identity(uploaded_groups))

    package_validation_error = None
    if teaching_uploads and len(teaching_uploads) > settings.max_teaching_files:
        package_validation_error = (
            f"Chỉ được tải tối đa {settings.max_teaching_files} "
            "file tài liệu giảng dạy."
        )
    total_package_bytes = sum(len(data) for _name, data in uploaded_groups)
    if total_package_bytes > settings.max_package_size_bytes:
        package_validation_error = (
            f"Tổng dung lượng bộ học liệu vượt quá "
            f"{settings.max_package_size_mb} MB."
        )

    ready = bool(
        lesson_upload
        and teaching_uploads
        and material_upload
        and answer_upload
        and not package_validation_error
    )
    readiness = st.columns(4)
    if lesson_upload:
        readiness[0].success("✓ Giáo án")
    else:
        readiness[0].info("Thiếu giáo án")
    if teaching_uploads:
        readiness[1].success(f"✓ {len(teaching_uploads)} tài liệu dạy")
    else:
        readiness[1].info("Thiếu tài liệu dạy")
    if material_upload:
        readiness[2].success("✓ Bài tập")
    else:
        readiness[2].info("Thiếu bài tập")
    if answer_upload:
        readiness[3].success("✓ Đáp án")
    else:
        readiness[3].info("Thiếu đáp án")
    if package_validation_error:
        st.error(package_validation_error)

    if uploaded_groups:
        with st.expander("Các file trong bộ học liệu"):
            for name, data in uploaded_groups:
                st.markdown(f"- **{name}** · {format_file_size(len(data))}")

    with st.expander("Yêu cầu kiểm tra bổ sung"):
        custom_request = st.text_area(
            "Yêu cầu riêng",
            placeholder="Ví dụ: chú ý câu hỏi KET Reading and Writing Part 3.",
        )
    analysis_mode_label = st.radio(
        "Mức kiểm tra",
        ("Kiểm tra nhanh", "Phân tích toàn diện"),
        horizontal=True,
        help=(
            "Kiểm tra nhanh tập trung vào phạm vi, câu hỏi và đáp án. "
            "Phân tích toàn diện kiểm tra thêm tiếng Anh và chất lượng đề; "
            "không kiểm tra chính tả, ngữ pháp hoặc diễn đạt tiếng Việt."
        ),
    )
    analysis_mode = "quick" if analysis_mode_label == "Kiểm tra nhanh" else "full"
    metadata = {
        "subject": "",
        "grade": "",
        "topic": "",
        "objectives": "",
        "custom_request": custom_request,
        "analysis_mode": analysis_mode,
    }

    selected_checks: list[str] = []
    if analysis_mode == "full":
        st.subheader("Các loại kiểm tra chi tiết")
        check_columns = st.columns(2)
        selected_checks = [
            key
            for index, (key, label) in enumerate(CHECKS.items())
            if check_columns[index % 2].checkbox(label, value=True, key=f"check_{key}")
        ]
    else:
        st.caption(
            "Tập trung kiểm tra đúng phạm vi, tự giải độc lập và đối chiếu đáp án. "
            "Các phần ngoài phạm vi không bị tính là lỗi."
        )

    action_col, clear_col, new_col = st.columns([2, 1, 1])
    start = action_col.button(
        (
            "Kiểm tra nhanh bộ học liệu"
            if analysis_mode == "quick"
            else "Phân tích toàn diện bộ học liệu"
        ),
        type="primary",
        disabled=not ready,
        use_container_width=True,
    )
    if clear_col.button("Xóa kết quả", use_container_width=True):
        clear_analysis_results(st.session_state)
        st.session_state.analysis_status = "IDLE"
        st.rerun()
    if new_col.button("Chọn bộ khác", use_container_width=True):
        clear_analysis_state(st.session_state)
        st.session_state.uploader_version += 1
        st.rerun()

    if start and ready:
        assert lesson_upload and material_upload and answer_upload and teaching_uploads
        clear_analysis_results(st.session_state)
        st.session_state.analysis_status = "VALIDATING"
        status = st.status("Đang phân tích bộ học liệu", expanded=True)
        progress_bar = st.progress(0.02)

        def mapped_progress(
            prefix: str,
            start_value: float,
            width: float,
        ):
            def update(message: str, value: float) -> None:
                status.update(label=f"{prefix} · {message}", state="running")
                progress_bar.progress(min(1.0, start_value + width * value))

            return update

        try:
            status.update(label="Đang kiểm tra và đọc các file", state="running")
            lesson_data = lesson_upload.getvalue()
            material_data = material_upload.getvalue()
            answer_data = answer_upload.getvalue()
            teaching_data = [item.getvalue() for item in teaching_uploads]

            lesson_parsed = parse_document(lesson_data, lesson_upload.name, settings)
            teaching_parsed = [
                parse_document(data, uploaded.name, settings)
                for uploaded, data in zip(teaching_uploads, teaching_data)
            ]
            material_parsed = parse_document(
                material_data,
                material_upload.name,
                settings,
            )
            answer_parsed = parse_document(answer_data, answer_upload.name, settings)
            ai = OpenAIService(settings)

            lesson_cache_key = file_hash(
                (
                    f"{settings.openai_model}|"
                    f"{settings.openai_reasoning_effort}|"
                    f"{file_hash(lesson_data)}"
                ).encode("utf-8")
            )
            lesson_cache = st.session_state.lesson_profile_cache
            cached_lesson = lesson_cache.get(lesson_cache_key)
            if cached_lesson:
                lesson_plan = LessonPlanProfile.model_validate(cached_lesson)
                mapped_progress("1/6 Giáo án", 0.03, 0.14)(
                    "Dùng kết quả đã phân tích trong phiên này", 1.0
                )
            else:
                lesson_plan = analyze_lesson_plan(
                    parsed=lesson_parsed,
                    original_bytes=lesson_data,
                    settings=settings,
                    progress=mapped_progress("1/6 Giáo án", 0.03, 0.14),
                    ai_service=ai,
                )
                _cache_put(
                    lesson_cache,
                    lesson_cache_key,
                    lesson_plan.model_dump(mode="json"),
                )
            teaching_documents = [
                SourceDocument(uploaded.name, data, parsed)
                for uploaded, data, parsed in zip(
                    teaching_uploads,
                    teaching_data,
                    teaching_parsed,
                )
            ]
            teaching_cache_key = _uploaded_identity(
                [
                    (
                        "model-profile",
                        (
                            f"{settings.openai_model}|"
                            f"{settings.openai_reasoning_effort}"
                        ).encode("utf-8"),
                    ),
                    (f"lesson:{lesson_upload.name}", lesson_data),
                ]
                + [
                    (uploaded.name, data)
                    for uploaded, data in zip(teaching_uploads, teaching_data)
                ]
            )
            teaching_cache = st.session_state.teaching_context_cache
            cached_teaching = teaching_cache.get(teaching_cache_key)
            if cached_teaching:
                teaching_context = TeachingContextProfile.model_validate(
                    cached_teaching
                )
                mapped_progress("2/6 Tài liệu dạy", 0.18, 0.15)(
                    "Dùng kết quả đã phân tích trong phiên này", 1.0
                )
            else:
                teaching_context = analyze_teaching_materials(
                    documents=teaching_documents,
                    lesson_plan=lesson_plan,
                    settings=settings,
                    ai_service=ai,
                    progress=mapped_progress("2/6 Tài liệu dạy", 0.18, 0.15),
                )
                _cache_put(
                    teaching_cache,
                    teaching_cache_key,
                    teaching_context.model_dump(mode="json"),
                )
            material_document = SourceDocument(
                material_upload.name,
                material_data,
                material_parsed,
            )
            questions = solve_student_material(
                document=material_document,
                lesson_plan=lesson_plan,
                teaching_context=teaching_context,
                teaching_documents=teaching_documents,
                settings=settings,
                ai_service=ai,
                scope_request=custom_request,
                progress=mapped_progress("3/6 Tự giải bài tập", 0.34, 0.15),
            )
            answer_key = extract_answer_key(
                document=SourceDocument(
                    answer_upload.name,
                    answer_data,
                    answer_parsed,
                ),
                target_scope=questions.scope,
                settings=settings,
                ai_service=ai,
                progress=mapped_progress("4/6 Đáp án", 0.5, 0.14),
            )
            if analysis_mode == "full":
                result = analyze_document(
                    parsed=material_parsed,
                    original_bytes=material_data,
                    metadata=metadata,
                    lesson_plan=lesson_plan,
                    teaching_context=teaching_context,
                    selected_checks=selected_checks,
                    settings=settings,
                    progress=mapped_progress("5/6 Kiểm tra bài tập", 0.65, 0.18),
                    ai_service=ai,
                    answer_key=answer_key,
                )
            else:
                result = build_quick_analysis_result(material_parsed, questions)
                mapped_progress("5/6 Kiểm tra nhanh", 0.65, 0.18)(
                    "Đã bỏ qua rà soát tiếng Anh chuyên sâu", 1.0
                )
            comparison = compare_learning_package(
                lesson_plan=lesson_plan,
                teaching_context=teaching_context,
                questions=questions,
                answer_key=answer_key,
                ai_service=ai,
                progress=mapped_progress("6/6 Đối chiếu", 0.84, 0.14),
                batch_size=settings.comparison_batch_size,
            )
            usage_summary = ai.usage_summary()
            metadata["estimated_cost_usd"] = (
                f"{usage_summary.estimated_cost_usd:.8f}"
            )
            metadata["model_strategy"] = (
                f"{settings.openai_model} đọc/trích xuất; "
                f"{settings.openai_solving_model} tự giải; "
                f"{settings.openai_escalation_model} xác minh trường hợp chưa kết luận"
            )

            st.session_state.analysis_result = result.model_dump(mode="json")
            st.session_state.lesson_plan_profile = lesson_plan.model_dump(mode="json")
            st.session_state.teaching_context_profile = teaching_context.model_dump(
                mode="json"
            )
            st.session_state.student_question_set = questions.model_dump(mode="json")
            st.session_state.answer_key_profile = answer_key.model_dump(mode="json")
            st.session_state.package_comparison_result = comparison.model_dump(
                mode="json"
            )
            st.session_state.analysis_metadata = metadata
            st.session_state.ai_usage_summary = usage_summary.model_dump(mode="json")

            st.session_state.lesson_plan_file_name = lesson_upload.name
            st.session_state.teaching_file_names = [
                item.name for item in teaching_uploads
            ]
            st.session_state.learning_material_file_name = material_upload.name
            st.session_state.answer_key_file_name = answer_upload.name
            st.session_state.preview_document = material_parsed.model_dump(mode="json")
            st.session_state.preview_file_bytes = material_data
            st.session_state.lesson_plan_preview_document = lesson_parsed.model_dump(
                mode="json"
            )
            st.session_state.lesson_plan_preview_file_bytes = lesson_data
            st.session_state.teaching_preview_documents = [
                item.model_dump(mode="json") for item in teaching_parsed
            ]
            st.session_state.teaching_preview_file_bytes = teaching_data
            st.session_state.answer_key_preview_document = answer_parsed.model_dump(
                mode="json"
            )
            st.session_state.answer_key_preview_file_bytes = answer_data
            st.session_state.analysis_status = "COMPLETED"
            st.session_state.analysis_error = None
            progress_bar.progress(1.0)
            status.update(
                label="Hoàn tất phân tích bộ học liệu",
                state="complete",
                expanded=False,
            )
        except (FileValidationError, OpenAIServiceError, ValueError) as exc:
            st.session_state.analysis_status = "FAILED"
            st.session_state.analysis_error = str(exc)
            status.update(label="Phân tích thất bại", state="error")
        except Exception:
            st.session_state.analysis_status = "FAILED"
            st.session_state.analysis_error = (
                "Đã xảy ra lỗi không mong muốn khi xử lý bộ học liệu. Vui lòng thử lại."
            )
            status.update(label="Phân tích thất bại", state="error")

    if st.session_state.get("analysis_error"):
        st.error(st.session_state.analysis_error)
    required_result_keys = (
        "analysis_result",
        "lesson_plan_profile",
        "teaching_context_profile",
        "student_question_set",
        "answer_key_profile",
        "package_comparison_result",
        "preview_document",
        "lesson_plan_preview_document",
        "teaching_preview_documents",
        "answer_key_preview_document",
    )
    if all(st.session_state.get(key) is not None for key in required_result_keys):
        render_result(
            result=AnalysisResult.model_validate(st.session_state.analysis_result),
            lesson_plan=LessonPlanProfile.model_validate(
                st.session_state.lesson_plan_profile
            ),
            teaching_context=TeachingContextProfile.model_validate(
                st.session_state.teaching_context_profile
            ),
            questions=StudentQuestionSet.model_validate(
                st.session_state.student_question_set
            ),
            answer_key=AnswerKeyProfile.model_validate(
                st.session_state.answer_key_profile
            ),
            comparison=PackageComparisonResult.model_validate(
                st.session_state.package_comparison_result
            ),
            metadata=st.session_state.get("analysis_metadata", {}),
            usage=(
                AIUsageSummary.model_validate(st.session_state.ai_usage_summary)
                if st.session_state.get("ai_usage_summary")
                else None
            ),
        )


if __name__ == "__main__":
    main()
