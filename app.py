from __future__ import annotations

from collections import Counter
from datetime import datetime

import streamlit as st

from config.settings import get_settings
from schemas.analysis import AnalysisResult, IssueCategory, IssueSeverity
from services.analysis_service import analyze_document
from services.cleanup_service import clear_analysis_state
from services.document_service import parse_document
from services.openai_service import OpenAIServiceError
from services.report_service import create_docx_report, create_json_report
from utils.file_utils import file_hash, format_file_size, safe_report_stem
from utils.validators import FileValidationError


CHECKS = {
    "vi_spelling": "Chính tả tiếng Việt",
    "vi_grammar": "Ngữ pháp và diễn đạt tiếng Việt",
    "en_spelling": "Chính tả tiếng Anh",
    "en_grammar": "Ngữ pháp và diễn đạt tiếng Anh",
    "prompt_quality": "Kiểm tra đề bài",
    "qa": "Kiểm tra câu hỏi và đáp án",
    "suitability": "Kiểm tra mức độ phù hợp",
    "replacement": "Đề xuất câu hỏi thay thế",
}

CATEGORY_LABELS = {
    category.value: category.value.replace("_", " ").title()
    for category in IssueCategory
}
SEVERITY_LABELS = {
    IssueSeverity.CRITICAL.value: "Nghiêm trọng",
    IssueSeverity.WARNING.value: "Cảnh báo",
    IssueSeverity.SUGGESTION.value: "Gợi ý",
}


def init_state() -> None:
    defaults = {
        "analysis_status": "IDLE",
        "analysis_result": None,
        "analysis_error": None,
        "uploader_version": 0,
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def reset_for_new_hash(new_hash: str, file_name: str) -> None:
    if st.session_state.get("uploaded_file_hash") != new_hash:
        clear_analysis_state(st.session_state)
        st.session_state.uploaded_file_hash = new_hash
        st.session_state.current_file_name = file_name
        st.session_state.analysis_status = "IDLE"


def render_result(
    result: AnalysisResult, file_name: str, metadata: dict[str, str]
) -> None:
    st.divider()
    st.subheader("Kết quả phân tích")
    counts = Counter(issue.severity.value for issue in result.issues)
    columns = st.columns(4)
    columns[0].metric("Tổng vấn đề", len(result.issues))
    columns[1].metric("Nghiêm trọng", counts["critical"])
    columns[2].metric("Cảnh báo", counts["warning"])
    columns[3].metric("Gợi ý", counts["suggestion"])

    summary = result.document_summary
    st.write(summary.summary)
    details = [
        f"**Loại:** {summary.document_type.upper()}",
        f"**Ngôn ngữ:** {', '.join(summary.detected_languages) or 'Không xác định'}",
    ]
    if summary.total_questions is not None:
        details.append(f"**Số câu hỏi:** {summary.total_questions}")
    st.markdown(" · ".join(details))

    with st.expander("Bộ lọc kết quả", expanded=True):
        col1, col2, col3 = st.columns(3)
        severities = col1.multiselect(
            "Mức độ",
            list(SEVERITY_LABELS),
            format_func=lambda value: SEVERITY_LABELS[value],
        )
        categories = col2.multiselect(
            "Nhóm lỗi",
            sorted({issue.category.value for issue in result.issues}),
            format_func=lambda value: CATEGORY_LABELS[value],
        )
        pages = sorted(
            {issue.page_number for issue in result.issues if issue.page_number is not None}
        )
        selected_pages = col3.multiselect("Trang", pages)
        keyword = st.text_input("Từ khóa", placeholder="Tìm trong nội dung và giải thích")
        human_only = st.checkbox("Chỉ hiện vấn đề cần người dùng kiểm tra lại")

    filtered = []
    for issue in result.issues:
        haystack = " ".join(
            filter(
                None,
                [
                    issue.original_text,
                    issue.explanation,
                    issue.suggested_text,
                    issue.replacement_question,
                ],
            )
        ).casefold()
        if severities and issue.severity.value not in severities:
            continue
        if categories and issue.category.value not in categories:
            continue
        if selected_pages and issue.page_number not in selected_pages:
            continue
        if keyword and keyword.casefold() not in haystack:
            continue
        if human_only and not issue.requires_human_review:
            continue
        filtered.append(issue)

    st.caption(f"Hiển thị {len(filtered)}/{len(result.issues)} vấn đề")
    for issue in filtered:
        location = (
            f"Trang {issue.page_number}"
            if issue.page_number
            else issue.block_id or issue.section_title or "Chưa xác định vị trí"
        )
        title = (
            f"{SEVERITY_LABELS[issue.severity.value]} · "
            f"{CATEGORY_LABELS[issue.category.value]} · {location}"
        )
        with st.expander(title):
            if issue.question_number:
                st.caption(f"Câu {issue.question_number}")
            st.progress(issue.confidence, text=f"Độ tin cậy: {issue.confidence:.0%}")
            st.markdown("**Nội dung gốc**")
            st.code(issue.original_text, language=None, wrap_lines=True)
            st.markdown(f"**Giải thích:** {issue.explanation}")
            if issue.suggested_text:
                st.markdown(f"**Đề xuất sửa:** {issue.suggested_text}")
            if issue.replacement_question:
                st.markdown(f"**Câu hỏi thay thế:** {issue.replacement_question}")
            if issue.suggested_answer:
                st.markdown(f"**Đáp án gợi ý:** {issue.suggested_answer}")
            if issue.requires_human_review:
                st.warning("Vấn đề này cần người dùng xác minh.")

    if result.general_recommendations:
        with st.expander("Đề xuất chung"):
            for item in result.general_recommendations:
                st.markdown(f"- {item}")
    if result.limitations:
        with st.expander("Giới hạn của kết quả"):
            for item in result.limitations:
                st.markdown(f"- {item}")

    stem = safe_report_stem(file_name)
    left, right = st.columns(2)
    left.download_button(
        "Tải báo cáo DOCX",
        create_docx_report(result, file_name, metadata),
        file_name=f"{stem}-analysis-report.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        use_container_width=True,
    )
    right.download_button(
        "Tải kết quả JSON",
        create_json_report(result),
        file_name=f"{stem}-analysis-result.json",
        mime="application/json",
        use_container_width=True,
    )


def main() -> None:
    st.set_page_config(
        page_title="AI kiểm tra học liệu",
        page_icon="📘",
        layout="wide",
    )
    init_state()
    settings = get_settings()

    st.title("AI kiểm tra học liệu")
    st.caption(
        "Kiểm tra lỗi ngôn ngữ, đề bài, câu hỏi và đáp án trong tài liệu Word/PDF."
    )
    uploaded = st.file_uploader(
        "Tải tài liệu Word hoặc PDF",
        type=["pdf", "docx"],
        accept_multiple_files=False,
        key=f"uploader_{st.session_state.uploader_version}",
    )

    file_bytes: bytes | None = None
    if uploaded is not None:
        file_bytes = uploaded.getvalue()
        reset_for_new_hash(file_hash(file_bytes), uploaded.name)
        st.info(f"**{uploaded.name}** · {format_file_size(len(file_bytes))}")

    st.subheader("Thông tin bổ sung")
    col1, col2 = st.columns(2)
    subject = col1.text_input("Môn học")
    grade = col2.text_input("Khối lớp")
    topic = st.text_input("Chủ đề bài học")
    objectives = st.text_area("Mục tiêu bài học")
    custom_request = st.text_area("Yêu cầu kiểm tra riêng")
    metadata = {
        "subject": subject,
        "grade": grade,
        "topic": topic,
        "objectives": objectives,
        "custom_request": custom_request,
    }

    st.subheader("Các loại kiểm tra")
    check_columns = st.columns(2)
    selected_checks = [
        key
        for index, (key, label) in enumerate(CHECKS.items())
        if check_columns[index % 2].checkbox(label, value=True, key=f"check_{key}")
    ]

    action_col, clear_col, new_col = st.columns([2, 1, 1])
    start = action_col.button(
        "Bắt đầu phân tích",
        type="primary",
        disabled=uploaded is None,
        use_container_width=True,
    )
    if clear_col.button("Xóa kết quả", use_container_width=True):
        st.session_state.analysis_result = None
        st.session_state.analysis_error = None
        st.session_state.analysis_status = "IDLE"
        st.rerun()
    if new_col.button("Phân tích tài liệu khác", use_container_width=True):
        clear_analysis_state(st.session_state)
        st.session_state.uploader_version += 1
        st.rerun()

    if start and uploaded is not None and file_bytes is not None:
        status = st.status("Đang kiểm tra tài liệu", expanded=True)
        progress_bar = st.progress(0.05)

        def update_progress(message: str, value: float) -> None:
            status.update(label=message, state="running")
            progress_bar.progress(value)

        try:
            st.session_state.analysis_status = "VALIDATING"
            parsed = parse_document(file_bytes, uploaded.name, settings)
            for warning in parsed.warnings:
                st.warning(warning)
            st.session_state.analysis_status = "EXTRACTING"
            progress_bar.progress(0.2)
            st.session_state.analysis_status = "ANALYZING"
            result = analyze_document(
                parsed=parsed,
                original_bytes=file_bytes,
                metadata=metadata,
                selected_checks=selected_checks,
                settings=settings,
                progress=update_progress,
            )
            st.session_state.analysis_status = "COMPLETED"
            st.session_state.analysis_result = result.model_dump(mode="json")
            st.session_state.analysis_metadata = metadata
            st.session_state.document_warnings = parsed.warnings
            st.session_state.analysis_error = None
            status.update(label="Hoàn tất", state="complete", expanded=False)
        except (FileValidationError, OpenAIServiceError, ValueError) as exc:
            st.session_state.analysis_status = "FAILED"
            st.session_state.analysis_error = str(exc)
            status.update(label="Phân tích thất bại", state="error")
        except Exception:
            st.session_state.analysis_status = "FAILED"
            st.session_state.analysis_error = (
                "Đã xảy ra lỗi không mong muốn khi xử lý tài liệu. Vui lòng thử lại."
            )
            status.update(label="Phân tích thất bại", state="error")

    if st.session_state.get("analysis_error"):
        st.error(st.session_state.analysis_error)
    if st.session_state.get("analysis_result"):
        render_result(
            AnalysisResult.model_validate(st.session_state.analysis_result),
            st.session_state.get("current_file_name", "document"),
            st.session_state.get("analysis_metadata", {}),
        )


if __name__ == "__main__":
    main()
