from __future__ import annotations

from dataclasses import dataclass

from schemas.package import (
    AnswerKeyProfile,
    ComparisonStatus,
    PackageComparisonResult,
    StudentQuestionSet,
)


ACTIONABLE_STATUSES = frozenset(
    {
        ComparisonStatus.CONFLICT,
        ComparisonStatus.AMBIGUOUS,
        ComparisonStatus.MISSING_KEY,
        ComparisonStatus.KEY_EXTRACTION_UNCERTAIN,
        ComparisonStatus.VERSION_MISMATCH,
    }
)


@dataclass(frozen=True, slots=True)
class PackageStatistics:
    question_count: int
    match_count: int
    ai_disagreement_count: int
    actionable_count: int
    outside_scope_count: int
    conflict_count: int
    ambiguous_count: int
    missing_key_count: int
    key_extraction_uncertain_count: int
    version_mismatch_count: int


def package_statistics(
    questions: StudentQuestionSet,
    answer_key: AnswerKeyProfile,
    comparison: PackageComparisonResult,
) -> PackageStatistics:
    def count(status: ComparisonStatus) -> int:
        return sum(item.status == status for item in comparison.comparisons)

    return PackageStatistics(
        question_count=len(questions.questions),
        match_count=count(ComparisonStatus.MATCH),
        ai_disagreement_count=count(ComparisonStatus.AI_DISAGREEMENT),
        actionable_count=sum(
            item.status in ACTIONABLE_STATUSES for item in comparison.comparisons
        ),
        outside_scope_count=(
            answer_key.ignored_out_of_scope_count
            + count(ComparisonStatus.ORPHAN_KEY)
        ),
        conflict_count=count(ComparisonStatus.CONFLICT),
        ambiguous_count=count(ComparisonStatus.AMBIGUOUS),
        missing_key_count=count(ComparisonStatus.MISSING_KEY),
        key_extraction_uncertain_count=count(
            ComparisonStatus.KEY_EXTRACTION_UNCERTAIN
        ),
        version_mismatch_count=count(ComparisonStatus.VERSION_MISMATCH),
    )


def package_decision(stats: PackageStatistics) -> tuple[str, str]:
    if stats.question_count == 0:
        return (
            "Không đủ dữ liệu",
            "Không nhận diện được câu hỏi để kiểm tra. Hãy kiểm tra lại file bài tập.",
        )
    if stats.actionable_count:
        return (
            "Cần giáo viên xác minh",
            "Có dữ liệu chưa đọc hoặc chưa ghép chắc chắn; hệ thống chưa kết luận "
            "tài liệu hay đáp án bị sai.",
        )
    return (
        "Có thể sử dụng",
        "Các câu trong phạm vi đã kiểm tra không có lỗi đối chiếu cần xử lý.",
    )
