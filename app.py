from __future__ import annotations

import html
from collections import Counter

import streamlit as st

from config.settings import get_settings
from schemas.analysis import AnalysisResult, IssueCategory, IssueSeverity
from schemas.document import DocumentType, ParsedDocument
from schemas.lesson_plan import LessonPlanProfile
from services.analysis_service import analyze_document, analyze_lesson_plan
from services.cleanup_service import clear_analysis_state
from services.document_service import parse_document
from services.openai_service import OpenAIService, OpenAIServiceError
from services.preview_service import render_pdf_page_preview
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
    "suitability": "Đối chiếu với giáo án",
    "replacement": "Đề xuất câu hỏi thay thế",
}

CATEGORY_LABELS = {
    IssueCategory.VIETNAMESE_SPELLING.value: "Chính tả tiếng Việt",
    IssueCategory.VIETNAMESE_GRAMMAR.value: "Ngữ pháp tiếng Việt",
    IssueCategory.VIETNAMESE_EXPRESSION.value: "Diễn đạt tiếng Việt",
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
    IssueCategory.OUT_OF_SCOPE.value: "Ngoài phạm vi giáo án",
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


def init_state() -> None:
    defaults = {
        "analysis_status": "IDLE",
        "analysis_result": None,
        "lesson_plan_profile": None,
        "analysis_error": None,
        "uploader_version": 0,
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def reset_for_new_inputs(
    identity: str,
    lesson_plan_name: str | None,
    learning_material_name: str | None,
) -> None:
    if st.session_state.get("uploaded_file_hash") == identity:
        return
    clear_analysis_state(st.session_state)
    st.session_state.uploaded_file_hash = identity
    st.session_state.lesson_plan_file_name = lesson_plan_name
    st.session_state.learning_material_file_name = learning_material_name
    st.session_state.current_file_name = learning_material_name
    st.session_state.analysis_status = "IDLE"


def set_preview_page(page_number: int) -> None:
    st.session_state.preview_pdf_page = page_number


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
            + (f"  •  {issue_counts[page]} vấn đề" if issue_counts[page] else "")
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
        numbers = ", ".join(
            f"#{number}" for number in sorted(preview.unmatched_issue_numbers)
        )
        st.caption(
            f"{numbers}: chỉ xác định được trang nên hệ thống đánh dấu viền trang, "
            "không tô nhầm một đoạn văn bản."
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
            st.info("Không còn dữ liệu PDF xem trước trong phiên này.")
            return
        render_pdf_preview(
            parsed,
            file_bytes,
            result,
            select_key=select_key,
        )
    else:
        render_docx_preview(parsed, result)


def render_lesson_plan_profile(profile: LessonPlanProfile) -> None:
    st.markdown("#### Căn cứ đã trích xuất từ giáo án")
    labels = [
        f"**Môn:** {profile.subject or 'Chưa xác định'}",
        f"**Khối/lớp:** {profile.grade_level or 'Chưa xác định'}",
        f"**Chủ đề:** {profile.topic or 'Chưa xác định'}",
    ]
    st.markdown(" · ".join(labels))
    st.write(profile.summary)
    with st.expander("Mục tiêu và phạm vi kiến thức", expanded=True):
        if profile.objectives:
            st.markdown("**Mục tiêu bài học**")
            for item in profile.objectives:
                st.markdown(f"- {item}")
        if profile.knowledge_scope:
            st.markdown("**Phạm vi kiến thức**")
            for item in profile.knowledge_scope:
                st.markdown(f"- {item}")
    with st.expander("Hoạt động và đánh giá"):
        if profile.learning_activities:
            st.markdown("**Hoạt động học tập**")
            for item in profile.learning_activities:
                st.markdown(f"- {item}")
        if profile.assessment_criteria:
            st.markdown("**Tiêu chí đánh giá**")
            for item in profile.assessment_criteria:
                st.markdown(f"- {item}")
    if profile.uncertainties:
        with st.expander("Thông tin giáo án cần xác minh", expanded=True):
            for item in profile.uncertainties:
                st.warning(item)


def render_report_panel(
    result: AnalysisResult,
    profile: LessonPlanProfile,
    learning_material_name: str,
    lesson_plan_name: str,
    metadata: dict[str, str],
) -> None:
    st.markdown("### Báo cáo học liệu")
    st.caption(f"{learning_material_name} · đối chiếu với {lesson_plan_name}")
    render_lesson_plan_profile(profile)
    st.divider()

    counts = Counter(issue.severity.value for issue in result.issues)
    columns = st.columns(2)
    columns[0].metric("Tổng vấn đề", len(result.issues))
    columns[1].metric("Nghiêm trọng", counts["critical"])
    columns = st.columns(2)
    columns[0].metric("Cảnh báo", counts["warning"])
    columns[1].metric("Gợi ý", counts["suggestion"])

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
        col1, col2 = st.columns(2)
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
        selected_pages = st.multiselect("Trang học liệu", pages)
        keyword = st.text_input(
            "Từ khóa",
            placeholder="Tìm trong nội dung và giải thích",
        )
        human_only = st.checkbox("Chỉ hiện vấn đề cần giáo viên kiểm tra lại")

    filtered = []
    for number, issue in _numbered_issues(result):
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
        filtered.append((number, issue))

    st.caption(f"Hiển thị {len(filtered)}/{len(result.issues)} vấn đề")
    for number, issue in filtered:
        location = (
            f"Trang {issue.page_number}"
            if issue.page_number
            else issue.block_id or issue.section_title or "Chưa xác định vị trí"
        )
        title = (
            f"#{number} · {SEVERITY_LABELS[issue.severity.value]} · "
            f"{CATEGORY_LABELS[issue.category.value]} · {location}"
        )
        with st.expander(title):
            if issue.page_number is not None:
                st.button(
                    f"Xem trang {issue.page_number} bên trái",
                    key=f"show_issue_page_{number}",
                    on_click=set_preview_page,
                    args=(issue.page_number,),
                    use_container_width=True,
                )
            if issue.question_number:
                st.caption(f"Câu {issue.question_number}")
            st.progress(issue.confidence, text=f"Độ tin cậy: {issue.confidence:.0%}")
            st.markdown("**Nội dung gốc trong học liệu**")
            st.code(issue.original_text, language=None, wrap_lines=True)
            st.markdown(f"**Giải thích:** {issue.explanation}")
            if issue.lesson_plan_reference:
                st.markdown(
                    f"**Căn cứ từ giáo án:** {issue.lesson_plan_reference}"
                )
            if issue.suggested_text:
                st.markdown(f"**Đề xuất sửa:** {issue.suggested_text}")
            if issue.replacement_question:
                st.markdown(f"**Câu hỏi thay thế:** {issue.replacement_question}")
            if issue.suggested_answer:
                st.markdown(f"**Đáp án gợi ý:** {issue.suggested_answer}")
            if issue.requires_human_review:
                st.warning("Vấn đề này cần giáo viên xác minh.")

    if result.general_recommendations:
        with st.expander("Đề xuất chung"):
            for item in result.general_recommendations:
                st.markdown(f"- {item}")
    if result.limitations:
        with st.expander("Giới hạn của kết quả"):
            for item in result.limitations:
                st.markdown(f"- {item}")

    stem = safe_report_stem(learning_material_name)
    left, right = st.columns(2)
    left.download_button(
        "Tải báo cáo DOCX",
        create_docx_report(
            result,
            learning_material_name,
            metadata,
            lesson_plan=profile,
            lesson_plan_file_name=lesson_plan_name,
        ),
        file_name=f"{stem}-analysis-report.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        use_container_width=True,
    )
    right.download_button(
        "Tải kết quả JSON",
        create_json_report(
            result,
            lesson_plan=profile,
            lesson_plan_file_name=lesson_plan_name,
            learning_material_file_name=learning_material_name,
        ),
        file_name=f"{stem}-analysis-result.json",
        mime="application/json",
        use_container_width=True,
    )


def render_result(
    result: AnalysisResult,
    profile: LessonPlanProfile,
    learning_material_name: str,
    lesson_plan_name: str,
    metadata: dict[str, str],
    material_parsed: ParsedDocument | None,
    material_bytes: bytes | None,
    lesson_plan_parsed: ParsedDocument | None,
    lesson_plan_bytes: bytes | None,
) -> None:
    st.divider()
    st.subheader("Kết quả phân tích")
    st.caption(
        "Báo cáo chỉ đánh dấu lỗi trong học liệu. Giáo án được giữ ở tab riêng làm căn cứ đối chiếu."
    )
    document_column, report_column = st.columns([1.15, 1], gap="large")
    with document_column:
        with st.container(height=950, border=True):
            material_tab, lesson_tab = st.tabs(
                ["Học liệu đã đánh dấu", "Giáo án đối chiếu"]
            )
            with material_tab:
                st.caption(learning_material_name)
                render_document_preview(
                    material_parsed,
                    material_bytes,
                    result,
                    select_key="preview_pdf_page",
                )
            with lesson_tab:
                st.caption(lesson_plan_name)
                render_document_preview(
                    lesson_plan_parsed,
                    lesson_plan_bytes,
                    None,
                    select_key="lesson_plan_preview_pdf_page",
                )
    with report_column:
        with st.container(height=950, border=True):
            render_report_panel(
                result,
                profile,
                learning_material_name,
                lesson_plan_name,
                metadata,
            )


def _uploaded_identity(
    lesson_plan_name: str | None,
    lesson_plan_bytes: bytes | None,
    learning_material_name: str | None,
    learning_material_bytes: bytes | None,
) -> str:
    payload = (
        (lesson_plan_name or "").encode("utf-8")
        + b"\0"
        + (lesson_plan_bytes or b"")
        + b"\0"
        + (learning_material_name or "").encode("utf-8")
        + b"\0"
        + (learning_material_bytes or b"")
    )
    return file_hash(payload)


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
        "Đọc giáo án trước để xác định mục tiêu bài dạy, sau đó kiểm tra học liệu theo đúng ngữ cảnh."
    )
    st.markdown(
        "**Quy trình:** ① Tải giáo án → ② Tải học liệu → "
        "③ AI đọc giáo án → ④ AI kiểm tra học liệu"
    )

    upload_col1, upload_col2 = st.columns(2, gap="large")
    with upload_col1:
        st.markdown("### 1. Giáo án")
        lesson_plan_upload = st.file_uploader(
            "Tải giáo án Word hoặc PDF",
            type=["docx", "pdf"],
            accept_multiple_files=False,
            key=f"lesson_plan_uploader_{st.session_state.uploader_version}",
            help="Nên dùng file DOCX để trích xuất cấu trúc giáo án chính xác hơn.",
        )
    with upload_col2:
        st.markdown("### 2. Học liệu")
        learning_material_upload = st.file_uploader(
            "Tải học liệu Word hoặc PDF",
            type=["docx", "pdf"],
            accept_multiple_files=False,
            key=f"learning_material_uploader_{st.session_state.uploader_version}",
        )

    lesson_plan_bytes = (
        lesson_plan_upload.getvalue() if lesson_plan_upload is not None else None
    )
    learning_material_bytes = (
        learning_material_upload.getvalue()
        if learning_material_upload is not None
        else None
    )
    identity = _uploaded_identity(
        lesson_plan_upload.name if lesson_plan_upload else None,
        lesson_plan_bytes,
        learning_material_upload.name if learning_material_upload else None,
        learning_material_bytes,
    )
    reset_for_new_inputs(
        identity,
        lesson_plan_upload.name if lesson_plan_upload else None,
        learning_material_upload.name if learning_material_upload else None,
    )

    info_col1, info_col2 = st.columns(2)
    if lesson_plan_upload is not None and lesson_plan_bytes is not None:
        info_col1.success(
            f"Giáo án: **{lesson_plan_upload.name}** · "
            f"{format_file_size(len(lesson_plan_bytes))}"
        )
    else:
        info_col1.info("Chưa chọn giáo án.")
    if learning_material_upload is not None and learning_material_bytes is not None:
        info_col2.success(
            f"Học liệu: **{learning_material_upload.name}** · "
            f"{format_file_size(len(learning_material_bytes))}"
        )
    else:
        info_col2.info("Chưa chọn học liệu.")

    with st.expander("Yêu cầu kiểm tra bổ sung"):
        custom_request = st.text_area(
            "Yêu cầu riêng",
            placeholder="Ví dụ: Chú ý câu hỏi vận dụng hoặc cách dùng thuật ngữ chuyên môn.",
        )
    metadata = {
        "subject": "",
        "grade": "",
        "topic": "",
        "objectives": "",
        "custom_request": custom_request,
    }

    st.subheader("Các loại kiểm tra học liệu")
    st.caption(
        "Kết quả sẽ qua một lượt AI kiểm duyệt cuối để loại nhận xét thiếu căn cứ, "
        "trùng lặp hoặc chỉ mang tính văn phong."
    )
    check_columns = st.columns(2)
    selected_checks = [
        key
        for index, (key, label) in enumerate(CHECKS.items())
        if check_columns[index % 2].checkbox(label, value=True, key=f"check_{key}")
    ]

    inputs_ready = lesson_plan_upload is not None and learning_material_upload is not None
    action_col, clear_col, new_col = st.columns([2, 1, 1])
    start = action_col.button(
        "Phân tích giáo án và học liệu",
        type="primary",
        disabled=not inputs_ready,
        use_container_width=True,
    )
    if clear_col.button("Xóa kết quả", use_container_width=True):
        for key in (
            "analysis_result",
            "lesson_plan_profile",
            "analysis_error",
            "document_warnings",
        ):
            st.session_state.pop(key, None)
        st.session_state.analysis_status = "IDLE"
        st.rerun()
    if new_col.button("Chọn bộ tài liệu khác", use_container_width=True):
        clear_analysis_state(st.session_state)
        st.session_state.uploader_version += 1
        st.rerun()

    if (
        start
        and lesson_plan_upload is not None
        and learning_material_upload is not None
        and lesson_plan_bytes is not None
        and learning_material_bytes is not None
    ):
        status = st.status("Đang xử lý bộ tài liệu", expanded=True)
        progress_bar = st.progress(0.02)

        try:
            st.session_state.analysis_status = "LESSON_PLAN_VALIDATING"
            status.update(label="Bước 1/2 · Đang đọc giáo án", state="running")
            lesson_parsed = parse_document(
                lesson_plan_bytes,
                lesson_plan_upload.name,
                settings,
            )
            for warning in lesson_parsed.warnings:
                st.warning(f"Giáo án: {warning}")

            ai_service = OpenAIService(settings)

            def lesson_progress(message: str, value: float) -> None:
                status.update(label=f"Bước 1/2 · {message}", state="running")
                progress_bar.progress(0.05 + value * 0.4)

            st.session_state.analysis_status = "LESSON_PLAN_ANALYZING"
            profile = analyze_lesson_plan(
                parsed=lesson_parsed,
                original_bytes=lesson_plan_bytes,
                settings=settings,
                progress=lesson_progress,
                ai_service=ai_service,
            )

            st.session_state.analysis_status = "MATERIAL_VALIDATING"
            status.update(label="Bước 2/2 · Đang đọc học liệu", state="running")
            progress_bar.progress(0.48)
            material_parsed = parse_document(
                learning_material_bytes,
                learning_material_upload.name,
                settings,
            )
            for warning in material_parsed.warnings:
                st.warning(f"Học liệu: {warning}")

            def material_progress(message: str, value: float) -> None:
                status.update(label=f"Bước 2/2 · {message}", state="running")
                progress_bar.progress(0.5 + value * 0.48)

            st.session_state.analysis_status = "MATERIAL_ANALYZING"
            result = analyze_document(
                parsed=material_parsed,
                original_bytes=learning_material_bytes,
                metadata=metadata,
                lesson_plan=profile,
                selected_checks=selected_checks,
                settings=settings,
                progress=material_progress,
                ai_service=ai_service,
            )
            st.session_state.analysis_status = "COMPLETED"
            st.session_state.analysis_result = result.model_dump(mode="json")
            st.session_state.lesson_plan_profile = profile.model_dump(mode="json")
            st.session_state.analysis_metadata = metadata
            st.session_state.document_warnings = (
                lesson_parsed.warnings + material_parsed.warnings
            )
            st.session_state.preview_document = material_parsed.model_dump(mode="json")
            st.session_state.preview_file_bytes = learning_material_bytes
            st.session_state.lesson_plan_preview_document = lesson_parsed.model_dump(
                mode="json"
            )
            st.session_state.lesson_plan_preview_file_bytes = lesson_plan_bytes
            st.session_state.lesson_plan_file_name = lesson_plan_upload.name
            st.session_state.learning_material_file_name = learning_material_upload.name
            st.session_state.current_file_name = learning_material_upload.name
            st.session_state.analysis_error = None
            progress_bar.progress(1.0)
            status.update(
                label="Hoàn tất phân tích giáo án và học liệu",
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
                "Đã xảy ra lỗi không mong muốn khi xử lý bộ tài liệu. Vui lòng thử lại."
            )
            status.update(label="Phân tích thất bại", state="error")

    if st.session_state.get("analysis_error"):
        st.error(st.session_state.analysis_error)
    if st.session_state.get("analysis_result") and st.session_state.get(
        "lesson_plan_profile"
    ):
        material_preview = (
            ParsedDocument.model_validate(st.session_state.preview_document)
            if st.session_state.get("preview_document")
            else None
        )
        lesson_preview = (
            ParsedDocument.model_validate(st.session_state.lesson_plan_preview_document)
            if st.session_state.get("lesson_plan_preview_document")
            else None
        )
        render_result(
            AnalysisResult.model_validate(st.session_state.analysis_result),
            LessonPlanProfile.model_validate(st.session_state.lesson_plan_profile),
            st.session_state.get("learning_material_file_name", "learning-material"),
            st.session_state.get("lesson_plan_file_name", "lesson-plan"),
            st.session_state.get("analysis_metadata", {}),
            material_preview,
            st.session_state.get("preview_file_bytes"),
            lesson_preview,
            st.session_state.get("lesson_plan_preview_file_bytes"),
        )


if __name__ == "__main__":
    main()
