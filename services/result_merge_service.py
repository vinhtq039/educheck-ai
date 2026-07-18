from __future__ import annotations

from difflib import SequenceMatcher

from schemas.analysis import AnalysisIssue, AnalysisResult, IssueSeverity
from utils.text_utils import similarity_key


SEVERITY_RANK = {
    IssueSeverity.CRITICAL: 0,
    IssueSeverity.WARNING: 1,
    IssueSeverity.SUGGESTION: 2,
}


def _same_location(left: AnalysisIssue, right: AnalysisIssue) -> bool:
    if left.page_number is not None or right.page_number is not None:
        return left.page_number == right.page_number
    if left.block_id or right.block_id:
        return left.block_id == right.block_id
    return left.section_title == right.section_title


def _duplicate(left: AnalysisIssue, right: AnalysisIssue) -> bool:
    if left.category != right.category or not _same_location(left, right):
        return False
    ratio = SequenceMatcher(
        None, similarity_key(left.original_text), similarity_key(right.original_text)
    ).ratio()
    return ratio >= 0.84


def _quality(issue: AnalysisIssue) -> tuple[float, int, int, int]:
    location = int(issue.page_number is not None or bool(issue.block_id))
    suggestion = int(bool(issue.suggested_text or issue.replacement_question))
    severity = 2 - SEVERITY_RANK[issue.severity]
    return (issue.confidence, location, suggestion, severity)


def merge_results(results: list[AnalysisResult]) -> AnalysisResult:
    if not results:
        raise ValueError("Không có kết quả để tổng hợp.")

    issues: list[AnalysisIssue] = []
    for result in results:
        for candidate in result.issues:
            duplicate_index = next(
                (index for index, issue in enumerate(issues) if _duplicate(issue, candidate)),
                None,
            )
            if duplicate_index is None:
                issues.append(candidate)
            elif _quality(candidate) > _quality(issues[duplicate_index]):
                issues[duplicate_index] = candidate

    issues.sort(
        key=lambda issue: (
            SEVERITY_RANK[issue.severity],
            issue.page_number or 10**9,
            int(issue.block_id.split("-")[-1])
            if issue.block_id and issue.block_id.split("-")[-1].isdigit()
            else 10**9,
        )
    )

    base = results[0].document_summary.model_copy(deep=True)
    base.detected_languages = sorted(
        {language for result in results for language in result.document_summary.detected_languages}
    )
    totals = [
        result.document_summary.total_questions
        for result in results
        if result.document_summary.total_questions is not None
    ]
    base.total_questions = sum(totals) if totals else None
    if len(results) > 1:
        base.summary = " ".join(
            result.document_summary.summary.strip() for result in results
        )

    return AnalysisResult(
        document_summary=base,
        issues=issues,
        general_recommendations=list(
            dict.fromkeys(
                recommendation
                for result in results
                for recommendation in result.general_recommendations
            )
        ),
        limitations=list(
            dict.fromkeys(
                limitation for result in results for limitation in result.limitations
            )
        ),
    )

