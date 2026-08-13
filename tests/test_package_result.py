from __future__ import annotations

from schemas.package import AnswerKeyProfile, PackageComparisonResult, StudentQuestionSet
from services.package_result_service import package_decision, package_statistics


def test_out_of_scope_answers_are_not_counted_as_actionable_errors() -> None:
    questions = StudentQuestionSet(
        source_file_name="practice.pdf",
        questions=[],
        summary="Không có câu mẫu trong fixture.",
        limitations=[],
    )
    answer_key = AnswerKeyProfile(
        source_file_name="key.pdf",
        entries=[
            {
                "entry_id": "answer-0001",
                "question_number": "20",
                "official_answer": "C",
                "page_number": 5,
                "source_file_name": "key.pdf",
            }
        ],
        summary="Một mục ngoài phạm vi.",
        limitations=[],
        ignored_out_of_scope_count=27,
    )
    comparison = PackageComparisonResult(
        summary="Không có câu trong phạm vi.",
        comparisons=[
            {
                "answer_key_entry_id": "answer-0001",
                "question_number": "20",
                "status": "orphan_key",
                "official_answer": "C",
                "explanation": "Mục đáp án không có câu tương ứng trong bài tập.",
                "confidence": 0.99,
                "requires_human_review": False,
            }
        ],
        recommendations=[],
        limitations=[],
    )

    stats = package_statistics(questions, answer_key, comparison)

    assert stats.actionable_count == 0
    assert stats.outside_scope_count == 28
    assert package_decision(stats)[0] == "Không đủ dữ liệu"


def test_clean_question_set_is_ready_even_when_other_answer_sections_exist() -> None:
    questions = StudentQuestionSet(
        source_file_name="practice.pdf",
        questions=[
            {
                "question_id": "question-0001",
                "question_number": "1",
                "question_text": "Choose A.",
                "options": ["A", "B"],
                "independent_answer": "A",
                "reasoning_summary": "A is supported.",
                "confidence": 0.95,
                "page_number": 1,
                "source_file_name": "practice.pdf",
            }
        ],
        summary="Một câu.",
        limitations=[],
    )
    answer_key = AnswerKeyProfile(
        source_file_name="key.pdf",
        entries=[
            {
                "entry_id": "answer-0001",
                "question_number": "1",
                "official_answer": "A",
                "page_number": 1,
                "source_file_name": "key.pdf",
            }
        ],
        summary="Một đáp án trong phạm vi.",
        limitations=[],
        ignored_out_of_scope_count=28,
    )
    comparison = PackageComparisonResult(
        summary="Một câu khớp.",
        comparisons=[
            {
                "material_question_id": "question-0001",
                "answer_key_entry_id": "answer-0001",
                "question_number": "1",
                "status": "match",
                "independent_answer": "A",
                "official_answer": "A",
                "explanation": "Khớp chính xác.",
                "confidence": 0.95,
                "requires_human_review": False,
            }
        ],
        recommendations=[],
        limitations=[],
    )

    stats = package_statistics(questions, answer_key, comparison)

    assert stats.match_count == 1
    assert stats.actionable_count == 0
    assert stats.outside_scope_count == 28
    assert package_decision(stats)[0] == "Có thể sử dụng"


def test_ai_disagreement_does_not_mark_teacher_answer_as_an_error() -> None:
    questions = StudentQuestionSet(
        source_file_name="practice.pdf",
        questions=[
            {
                "question_id": "question-0001",
                "question_number": "7",
                "question_text": "Choose the best answer.",
                "options": ["A", "B"],
                "independent_answer": "A",
                "reasoning_summary": "AI chọn A.",
                "confidence": 0.9,
                "page_number": 2,
                "source_file_name": "practice.pdf",
            }
        ],
        summary="Một câu.",
        limitations=[],
    )
    answer_key = AnswerKeyProfile(
        source_file_name="key.pdf",
        entries=[
            {
                "entry_id": "answer-0001",
                "question_number": "7",
                "official_answer": "B",
                "page_number": 5,
                "source_file_name": "key.pdf",
            }
        ],
        summary="Một đáp án.",
        limitations=[],
    )
    comparison = PackageComparisonResult(
        summary="AI chưa đồng thuận.",
        comparisons=[
            {
                "material_question_id": "question-0001",
                "answer_key_entry_id": "answer-0001",
                "question_number": "7",
                "status": "ai_disagreement",
                "independent_answer": "A",
                "official_answer": "B",
                "explanation": "AI trả lời khác đáp án giáo viên.",
                "confidence": 0.9,
                "requires_human_review": True,
            }
        ],
        recommendations=[],
        limitations=[],
    )

    stats = package_statistics(questions, answer_key, comparison)

    assert stats.ai_disagreement_count == 1
    assert stats.actionable_count == 0
    assert package_decision(stats)[0] == "Có thể sử dụng"


def test_unread_answer_is_a_reading_uncertainty_not_a_required_edit() -> None:
    questions = StudentQuestionSet(
        source_file_name="practice.pdf",
        questions=[
            {
                "question_id": "question-0001",
                "question_number": "13",
                "question_text": "Choose the best answer.",
                "options": ["A", "B"],
                "independent_answer": "A",
                "reasoning_summary": "AI chọn A.",
                "confidence": 0.9,
                "page_number": 2,
                "source_file_name": "practice.pdf",
            }
        ],
        summary="Một câu.",
        limitations=[],
    )
    answer_key = AnswerKeyProfile(
        source_file_name="key.pdf",
        entries=[],
        summary="Chưa đọc được đáp án.",
        limitations=["Bố cục đáp án chưa đọc chắc chắn."],
    )
    comparison = PackageComparisonResult(
        summary="Chưa ghép được đáp án.",
        comparisons=[
            {
                "material_question_id": "question-0001",
                "question_number": "13",
                "status": "key_extraction_uncertain",
                "independent_answer": "A",
                "explanation": "Chưa trích xuất được mục đáp án tương ứng.",
                "confidence": 0.5,
                "requires_human_review": True,
            }
        ],
        recommendations=[],
        limitations=[],
    )

    stats = package_statistics(questions, answer_key, comparison)

    assert stats.key_extraction_uncertain_count == 1
    assert stats.actionable_count == 1
    assert package_decision(stats)[0] == "Cần giáo viên xác minh"
