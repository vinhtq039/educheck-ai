from __future__ import annotations

from schemas.analysis import (
    AnalysisIssue,
    AnalysisResult,
    DocumentSummary,
    IssueCategory,
    IssueSeverity,
)
from services.result_merge_service import merge_results


def result_with(issue: AnalysisIssue) -> AnalysisResult:
    return AnalysisResult(
        document_summary=DocumentSummary(
            document_type="pdf",
            detected_languages=["vi"],
            total_questions=1,
            summary="Một phần.",
        ),
        issues=[issue],
        general_recommendations=["Rà soát lại."],
        limitations=[],
    )


def issue(**overrides) -> AnalysisIssue:
    values = {
        "issue_id": "issue-1",
        "category": IssueCategory.VIETNAMESE_SPELLING,
        "severity": IssueSeverity.WARNING,
        "page_number": 1,
        "original_text": "Nội dung sai chín tả.",
        "explanation": "Sai chính tả.",
        "suggested_text": None,
        "confidence": 0.7,
    }
    values.update(overrides)
    return AnalysisIssue(**values)


def test_deduplicates_and_keeps_better_issue() -> None:
    better = issue(
        issue_id="issue-2",
        original_text="Nội dung sai chín tả",
        confidence=0.95,
        suggested_text="Nội dung sai chính tả.",
    )
    merged = merge_results([result_with(issue()), result_with(better)])
    assert len(merged.issues) == 1
    assert merged.issues[0].issue_id == "issue-2"


def test_does_not_merge_different_categories() -> None:
    other = issue(issue_id="issue-2", category=IssueCategory.VIETNAMESE_GRAMMAR)
    merged = merge_results([result_with(issue()), result_with(other)])
    assert len(merged.issues) == 2


def test_orders_by_severity() -> None:
    suggestion = issue(issue_id="s", severity=IssueSeverity.SUGGESTION)
    critical = issue(
        issue_id="c",
        severity=IssueSeverity.CRITICAL,
        category=IssueCategory.ENGLISH_GRAMMAR,
    )
    merged = merge_results([result_with(suggestion), result_with(critical)])
    assert [item.issue_id for item in merged.issues] == ["c", "s"]

