from __future__ import annotations

from schemas.analysis import AnalysisIssue, AnalysisResult, IssueCategory
from schemas.document import DocumentType, ParsedDocument
from schemas.review import FinalReviewResult, ReviewAction
from services.result_merge_service import sort_issues
from utils.text_utils import similarity_key


def _unique_limited(values: list[str], limit: int) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        value = value.strip()
        normalized = similarity_key(value)
        if value and normalized not in seen:
            seen.add(normalized)
            result.append(value)
        if len(result) == limit:
            break
    return result


def apply_review(
    candidate: AnalysisResult,
    review: FinalReviewResult,
) -> AnalysisResult:
    review_by_id = {item.issue_id: item for item in review.reviews}
    candidate_ids = {issue.issue_id for issue in candidate.issues}
    if set(review_by_id) != candidate_ids or len(review.reviews) != len(review_by_id):
        raise ValueError("Kết quả kiểm duyệt không khớp danh sách vấn đề.")

    kept: list[AnalysisIssue] = []
    for issue in candidate.issues:
        decision = review_by_id[issue.issue_id]
        if decision.action == ReviewAction.REMOVE:
            continue
        payload = issue.model_dump(mode="python")
        payload.update(
            severity=decision.severity,
            confidence=decision.confidence,
            explanation=decision.explanation,
            lesson_plan_reference=(
                decision.lesson_plan_reference or issue.lesson_plan_reference
            ),
            suggested_text=decision.suggested_text,
            requires_human_review=decision.requires_human_review,
        )
        kept.append(AnalysisIssue.model_validate(payload))

    summary = candidate.document_summary.model_copy(
        update={"summary": review.summary.strip()}
    )
    return AnalysisResult(
        document_summary=summary,
        issues=sort_issues(kept),
        general_recommendations=_unique_limited(
            review.general_recommendations,
            5,
        ),
        limitations=_unique_limited(
            candidate.limitations + review.limitations,
            8,
        ),
    )


_LAYOUT_OR_PREFERENCE_MARKERS = (
    "cách xuống dòng",
    "xuống dòng",
    "độ rộng",
    "chiều rộng",
    "căn lề",
    "phông chữ",
    "font",
    "văn phong",
    "sở thích",
    "tự nhiên hơn",
    "trôi chảy hơn",
    "có thể diễn đạt",
    "nên diễn đạt",
)
_MEANING_IMPACT_MARKERS = (
    "mơ hồ",
    "hai cách hiểu",
    "nhiều cách hiểu",
    "sai nghĩa",
    "đổi nghĩa",
    "không thể hiểu",
    "khó hiểu",
    "mâu thuẫn",
    "thiếu thông tin",
    "thiếu dữ kiện",
)
_GRAMMAR_EVIDENCE_MARKERS = (
    "sai ngữ pháp",
    "thiếu chủ ngữ",
    "thiếu vị ngữ",
    "chia động từ",
    "hòa hợp",
    "mạo từ",
    "giới từ",
    "số ít",
    "số nhiều",
    "thì của động từ",
    "subject-verb",
    "agreement",
    "tense",
)


def filter_subjective_issues(result: AnalysisResult) -> AnalysisResult:
    """Remove presentation/style preferences that cannot justify an edit."""

    kept: list[AnalysisIssue] = []
    removed = 0
    expression_categories = {
        IssueCategory.VIETNAMESE_EXPRESSION,
        IssueCategory.ENGLISH_EXPRESSION,
    }
    grammar_categories = {
        IssueCategory.VIETNAMESE_GRAMMAR,
        IssueCategory.ENGLISH_GRAMMAR,
    }

    for issue in result.issues:
        evidence = " ".join(
            value
            for value in (
                issue.original_text,
                issue.explanation,
                issue.suggested_text,
            )
            if value
        ).casefold()
        has_meaning_impact = any(
            marker in evidence for marker in _MEANING_IMPACT_MARKERS
        )
        is_layout_preference = any(
            marker in evidence for marker in _LAYOUT_OR_PREFERENCE_MARKERS
        )
        has_grammar_evidence = any(
            marker in evidence for marker in _GRAMMAR_EVIDENCE_MARKERS
        )

        if is_layout_preference and not has_meaning_impact:
            removed += 1
            continue
        if issue.category in expression_categories and not has_meaning_impact:
            removed += 1
            continue
        if (
            issue.category in grammar_categories
            and "không tự nhiên" in evidence
            and not has_meaning_impact
            and not has_grammar_evidence
        ):
            removed += 1
            continue
        kept.append(issue)

    if not removed:
        return result

    summary_text = (
        "Không phát hiện lỗi khách quan cần chỉnh sửa trong học liệu."
        if not kept
        else (
            f"Giữ lại {len(kept)} vấn đề có căn cứ kiểm chứng. "
            "Đã loại nhận xét thuần sở thích diễn đạt hoặc trình bày."
        )
    )
    return AnalysisResult(
        document_summary=result.document_summary.model_copy(
            update={"summary": summary_text}
        ),
        issues=sort_issues(kept),
        general_recommendations=[
            item
            for item in result.general_recommendations
            if not any(
                marker in item.casefold()
                for marker in _LAYOUT_OR_PREFERENCE_MARKERS
            )
        ][:5],
        limitations=result.limitations,
    )


def validate_result_locations(
    result: AnalysisResult,
    parsed: ParsedDocument,
) -> AnalysisResult:
    """Lock AI findings to real pages/blocks without guessing a new location."""

    limitations = list(result.limitations)
    validated: list[AnalysisIssue] = []
    page_text = {
        page.page_number: similarity_key(page.text)
        for page in parsed.pages
    }
    blocks = {block.block_id: block for block in parsed.blocks}

    for issue in result.issues:
        payload = issue.model_dump(mode="python")
        source_text = ""

        if parsed.document_type == DocumentType.PDF:
            if issue.page_number not in page_text:
                limitations.append(
                    f"Đã loại {issue.issue_id} vì số trang không tồn tại trong học liệu."
                )
                continue
            source_text = page_text[issue.page_number]
        else:
            payload["page_number"] = None
            if issue.block_id:
                block = blocks.get(issue.block_id)
                if block is None:
                    limitations.append(
                        f"Đã loại {issue.issue_id} vì block không tồn tại trong học liệu."
                    )
                    continue
                source_text = similarity_key(block.text)
            elif issue.section_title:
                source_text = " ".join(
                    similarity_key(block.text)
                    for block in parsed.blocks
                    if block.section_title == issue.section_title
                )

        quote = similarity_key(issue.original_text)
        if not source_text or (quote and quote not in source_text):
            payload["requires_human_review"] = True
            limitations.append(
                f"{issue.issue_id}: nguyên văn chưa khớp hoàn toàn với nội dung trích xuất; "
                "cần giáo viên xác minh vị trí."
            )
        validated.append(AnalysisIssue.model_validate(payload))

    return AnalysisResult(
        document_summary=result.document_summary,
        issues=sort_issues(validated),
        general_recommendations=result.general_recommendations,
        limitations=_unique_limited(limitations, 8),
    )
