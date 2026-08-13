from __future__ import annotations

import pytest
from pydantic import ValidationError

from config.settings import Settings
from schemas.document import DocumentBlock, DocumentType, ParsedDocument
from schemas.lesson_plan import LessonPlanProfile
from schemas.package import (
    AnswerKeyProfile,
    ExtractedQuestionSet,
    MaterialScope,
    PackageComparisonResult,
    QuestionSolutionSet,
    StudentQuestionSet,
    TeachingContextProfile,
)
from services.package_analysis_service import (
    SourceDocument,
    analyze_teaching_materials,
    compare_learning_package,
    extract_answer_key,
    solve_student_material,
)


def settings() -> Settings:
    return Settings(
        openai_api_key="test-key",
        openai_model="gpt-5.6-sol",
        openai_reasoning_effort="medium",
        max_file_size_mb=30,
        max_pdf_pages=150,
        pdf_pages_per_chunk=10,
        docx_chars_per_chunk=30000,
        ai_max_retries=0,
        ai_timeout_seconds=180,
    )


def lesson_plan() -> LessonPlanProfile:
    return LessonPlanProfile(
        source_document_type="docx",
        subject="Tiếng Anh",
        topic="KET Reading",
        objectives=["Đọc hiểu."],
        summary="Giáo án luyện đọc.",
    )


def parsed(text: str = "Câu 1. Chọn A hoặc B.") -> ParsedDocument:
    return ParsedDocument(
        document_type=DocumentType.DOCX,
        blocks=[
            DocumentBlock(
                block_id="block-0001",
                block_type="paragraph",
                text=text,
                order=1,
            )
        ],
    )


def teaching_context() -> TeachingContextProfile:
    return TeachingContextProfile(
        source_file_names=["slides.docx"],
        covered_content=["Reading Part 3"],
        key_terms=["KET"],
        worked_examples=[],
        instructions_and_conventions=["Chọn một đáp án."],
        summary="Slide hướng dẫn.",
        uncertainties=[],
    )


class FakePackageAI:
    def __init__(self) -> None:
        self.teaching_prompts: list[str] = []
        self.question_prompt = ""
        self.answer_prompt = ""
        self.comparison_ids = None

    def analyze_teaching_material_chunk(self, chunk, document_type, prompt):
        self.teaching_prompts.append(prompt)
        return TeachingContextProfile(
            source_file_names=["model-value"],
            covered_content=[f"Nội dung {len(self.teaching_prompts)}"],
            key_terms=["KET"],
            worked_examples=[],
            instructions_and_conventions=[],
            summary=f"Tóm tắt {len(self.teaching_prompts)}.",
            uncertainties=[],
        )

    def extract_student_questions_chunk(self, chunk, document_type, prompt):
        self.question_prompt = prompt
        return ExtractedQuestionSet(
            questions=[
                {
                    "question_number": "1",
                    "question_text": "Chọn A hoặc B.",
                    "options": ["A", "B"],
                    "confidence": 0.9,
                    "block_id": "block-0001",
                }
            ],
            summary="Một câu hỏi.",
            limitations=[],
            scope=MaterialScope(
                part="3",
                question_numbers=["1"],
                confidence=0.9,
            ),
        )

    def solve_question_batch(self, prompt, expected_question_ids):
        self.solve_prompt = prompt
        question_id = next(iter(expected_question_ids))
        return QuestionSolutionSet(
            solutions=[
                {
                    "question_id": question_id,
                    "independent_answer": "A",
                    "reasoning_summary": "A phù hợp ngữ cảnh.",
                    "confidence": 0.9,
                    "evidence_ids": ["lesson:summary:1"],
                }
            ],
            limitations=[],
        )

    def extract_answer_key_chunk(self, chunk, document_type, prompt):
        self.answer_prompt = prompt
        return AnswerKeyProfile(
            source_file_name="model-value",
            entries=[
                {
                    "entry_id": "model-entry",
                    "question_number": "1",
                    "official_answer": "B",
                    "block_id": "block-0001",
                    "source_file_name": "model-value",
                }
            ],
            summary="Một đáp án.",
            limitations=[],
        )

    def compare_package(self, prompt, expected_question_ids, expected_entry_ids):
        self.comparison_ids = (expected_question_ids, expected_entry_ids)
        return PackageComparisonResult(
            summary="AI tự giải khác đáp án chính thức.",
            comparisons=[
                {
                    "material_question_id": "question-0001",
                    "answer_key_entry_id": "answer-0001",
                    "question_number": "1",
                    "status": "conflict",
                    "independent_answer": "A",
                    "official_answer": "B",
                    "explanation": "Hai đáp án khác nhau.",
                    "confidence": 0.9,
                    "requires_human_review": True,
                }
            ],
            recommendations=["Giáo viên kiểm tra lại câu 1."],
            limitations=[],
        )


class FakeUnsupportedSolutionAI(FakePackageAI):
    def solve_question_batch(self, prompt, expected_question_ids):
        self.solve_prompt = prompt
        question_id = next(iter(expected_question_ids))
        return QuestionSolutionSet(
            solutions=[
                {
                    "question_id": question_id,
                    "independent_answer": "A",
                    "reasoning_summary": "Model answer without valid evidence.",
                    "confidence": 0.95,
                    "evidence_ids": ["invented:evidence"],
                }
            ],
            limitations=[],
        )


def test_solution_without_valid_evidence_is_forced_to_human_review() -> None:
    ai = FakeUnsupportedSolutionAI()
    questions = solve_student_material(
        document=SourceDocument("practice.docx", b"practice", parsed()),
        lesson_plan=lesson_plan(),
        teaching_context=teaching_context(),
        teaching_documents=[],
        settings=settings(),
        ai_service=ai,
    )

    question = questions.questions[0]
    assert question.independent_answer == "A"
    assert question.evidence_ids == []
    assert question.evidence == []
    assert question.confidence == 0.69
    assert question.requires_human_review is True
    assert any("chưa có dẫn chứng hợp lệ" in item for item in questions.limitations)


def test_package_pipeline_keeps_independent_solving_separate_from_answer_key() -> None:
    ai = FakePackageAI()
    teaching_documents = [
        SourceDocument("slides.docx", b"slides", parsed("Slide 1")),
        SourceDocument("handout.docx", b"handout", parsed("Handout 1")),
    ]
    teaching = analyze_teaching_materials(
        documents=teaching_documents,
        lesson_plan=lesson_plan(),
        settings=settings(),
        ai_service=ai,
    )
    questions = solve_student_material(
        document=SourceDocument("practice.docx", b"practice", parsed()),
        lesson_plan=lesson_plan(),
        teaching_context=teaching,
        teaching_documents=teaching_documents,
        settings=settings(),
        ai_service=ai,
        scope_request="Chỉ kiểm tra Part 3.",
    )
    answer_key = extract_answer_key(
        document=SourceDocument(
            "SECRET-KEY.docx",
            b"key",
            parsed("Câu 1: B"),
        ),
        settings=settings(),
        ai_service=ai,
        target_scope=questions.scope,
    )
    comparison = compare_learning_package(
        lesson_plan=lesson_plan(),
        teaching_context=teaching,
        questions=questions,
        answer_key=answer_key,
        ai_service=ai,
    )

    assert teaching.source_file_names == ["slides.docx", "handout.docx"]
    assert "SECRET-KEY.docx" not in ai.question_prompt
    assert "Câu 1: B" not in ai.question_prompt
    assert "SECRET-KEY.docx" not in ai.solve_prompt
    assert "Câu 1: B" not in ai.solve_prompt
    assert "Chỉ kiểm tra Part 3." in ai.question_prompt
    assert questions.questions[0].question_id == "question-0001"
    assert questions.questions[0].source_file_name == "practice.docx"
    assert questions.questions[0].evidence_ids == ["lesson:summary:1"]
    assert questions.questions[0].evidence[0].source == "Giáo án"
    assert answer_key.entries[0].entry_id == "answer-0001"
    assert answer_key.entries[0].source_file_name == "SECRET-KEY.docx"
    assert '"question_numbers":["1"]' in ai.answer_prompt
    assert ai.comparison_ids == ({"question-0001"}, {"answer-0001"})
    assert comparison.comparisons[0].status.value == "ai_disagreement"
    assert "không phải kết luận" in comparison.comparisons[0].explanation


def test_comparison_schema_rejects_status_that_conflicts_with_ids() -> None:
    with pytest.raises(ValidationError, match="missing_key"):
        PackageComparisonResult(
            summary="Kết quả không hợp lệ.",
            comparisons=[
                {
                    "material_question_id": "question-0001",
                    "answer_key_entry_id": "answer-0001",
                    "question_number": "1",
                    "status": "missing_key",
                    "independent_answer": "A",
                    "official_answer": "B",
                    "explanation": "Có đáp án nhưng lại đánh dấu thiếu.",
                    "confidence": 0.9,
                    "requires_human_review": True,
                }
            ],
            recommendations=[],
            limitations=[],
        )


class FakeBatchComparisonAI:
    def __init__(self) -> None:
        self.calls: list[tuple[set[str], set[str]]] = []

    def compare_package(self, prompt, expected_question_ids, expected_entry_ids):
        self.calls.append((expected_question_ids, expected_entry_ids))
        question_ids = sorted(expected_question_ids)
        answer_ids = sorted(expected_entry_ids)
        return PackageComparisonResult(
            summary=f"Đã đối chiếu {len(question_ids)} câu.",
            comparisons=[
                {
                    "material_question_id": question_id,
                    "answer_key_entry_id": answer_id,
                    "question_number": question_id.rsplit("-", 1)[-1],
                    "status": "conflict",
                    "independent_answer": "A",
                    "official_answer": "B",
                    "explanation": "Hai đáp án khác nhau.",
                    "confidence": 0.95,
                    "requires_human_review": True,
                }
                for question_id, answer_id in zip(question_ids, answer_ids)
            ],
            recommendations=[],
            limitations=[],
        )


def test_large_comparison_is_split_into_complete_batches() -> None:
    questions = StudentQuestionSet(
        source_file_name="practice.docx",
        questions=[
            {
                "question_id": f"question-{index:04d}",
                "question_number": str(index),
                "question_text": f"Câu hỏi {index}",
                "options": ["A", "B"],
                "independent_answer": "A",
                "reasoning_summary": "A phù hợp.",
                "confidence": 0.9,
                "requires_human_review": True,
                "block_id": "block-0001",
                "source_file_name": "practice.docx",
            }
            for index in range(1, 6)
        ],
        summary="Năm câu hỏi.",
        limitations=[],
    )
    answer_key = AnswerKeyProfile(
        source_file_name="key.docx",
        entries=[
            {
                "entry_id": f"answer-{index:04d}",
                "question_number": str(index),
                "official_answer": "B",
                "block_id": "block-0001",
                "source_file_name": "key.docx",
            }
            for index in range(1, 6)
        ],
        summary="Năm đáp án.",
        limitations=[],
    )
    ai = FakeBatchComparisonAI()

    result = compare_learning_package(
        lesson_plan=lesson_plan(),
        teaching_context=teaching_context(),
        questions=questions,
        answer_key=answer_key,
        ai_service=ai,
        batch_size=4,
    )

    assert len(ai.calls) == 3
    assert len(result.comparisons) == 5
    assert {
        item.material_question_id for item in result.comparisons
    } == {f"question-{index:04d}" for index in range(1, 6)}


def test_exact_answers_are_compared_without_an_extra_ai_call() -> None:
    questions = StudentQuestionSet(
        source_file_name="practice.docx",
        questions=[
            {
                "question_id": "question-0001",
                "question_number": "1",
                "question_text": "Chọn đáp án.",
                "options": ["A", "B"],
                "independent_answer": "A.",
                "reasoning_summary": "A phù hợp.",
                "confidence": 0.92,
                "block_id": "block-0001",
                "source_file_name": "practice.docx",
            }
        ],
        summary="Một câu hỏi.",
        limitations=[],
        scope=MaterialScope(part="3", confidence=0.95),
    )
    answer_key = AnswerKeyProfile(
        source_file_name="key.docx",
        entries=[
            {
                "entry_id": "answer-0001",
                "question_number": "1",
                "official_answer": "A",
                "block_id": "block-0001",
                "source_file_name": "key.docx",
            }
        ],
        summary="Một đáp án.",
        limitations=[],
        target_scope=questions.scope,
    )
    ai = FakeBatchComparisonAI()

    result = compare_learning_package(
        lesson_plan=lesson_plan(),
        teaching_context=teaching_context(),
        questions=questions,
        answer_key=answer_key,
        ai_service=ai,
    )

    assert ai.calls == []
    assert result.comparisons[0].status.value == "match"
    assert "1 khớp" in result.summary
    assert "0 mục cần giáo viên xác minh" in result.summary


def test_question_number_labels_are_normalized_before_matching() -> None:
    questions = StudentQuestionSet(
        source_file_name="practice.docx",
        questions=[
            {
                "question_id": "question-0013",
                "question_number": "Câu 13.",
                "question_text": "Chọn đáp án.",
                "options": ["A", "B"],
                "independent_answer": "B",
                "reasoning_summary": "B phù hợp.",
                "confidence": 0.9,
                "block_id": "block-0001",
                "source_file_name": "practice.docx",
            }
        ],
        summary="Một câu.",
        limitations=[],
    )
    answer_key = AnswerKeyProfile(
        source_file_name="key.docx",
        entries=[
            {
                "entry_id": "answer-0013",
                "question_number": "13",
                "official_answer": "B",
                "block_id": "block-0001",
                "source_file_name": "key.docx",
            }
        ],
        summary="Một đáp án.",
        limitations=[],
    )
    ai = FakeBatchComparisonAI()

    result = compare_learning_package(
        lesson_plan=lesson_plan(),
        teaching_context=teaching_context(),
        questions=questions,
        answer_key=answer_key,
        ai_service=ai,
    )

    assert ai.calls == []
    assert result.comparisons[0].status.value == "match"


def test_unlabeled_question_suffixes_do_not_collapse_into_roman_tokens() -> None:
    questions = StudentQuestionSet(
        source_file_name="practice.docx",
        questions=[
            {
                "question_id": f"question-000{index}",
                "question_number": label,
                "question_text": "Choose an answer.",
                "options": ["A", "B"],
                "independent_answer": "A",
                "reasoning_summary": "A is supported.",
                "confidence": 0.9,
                "block_id": "block-0001",
                "source_file_name": "practice.docx",
            }
            for index, label in enumerate(("unlabeled-A", "unlabeled-B"), start=1)
        ],
        summary="Two questions.",
        limitations=[],
    )
    answer_key = AnswerKeyProfile(
        source_file_name="key.docx",
        entries=[
            {
                "entry_id": f"answer-000{index}",
                "question_number": label,
                "official_answer": "A",
                "block_id": "block-0001",
                "source_file_name": "key.docx",
            }
            for index, label in enumerate(("unlabeled-A", "unlabeled-B"), start=1)
        ],
        summary="Two answers.",
        limitations=[],
    )
    ai = FakeBatchComparisonAI()

    result = compare_learning_package(
        lesson_plan=lesson_plan(),
        teaching_context=teaching_context(),
        questions=questions,
        answer_key=answer_key,
        ai_service=ai,
    )

    assert ai.calls == []
    assert [item.status.value for item in result.comparisons] == ["match", "match"]


class FakeVersionCheckAI:
    def __init__(self) -> None:
        self.calls: list[tuple[set[str], set[str]]] = []

    def compare_package(self, prompt, expected_question_ids, expected_entry_ids):
        self.calls.append((expected_question_ids, expected_entry_ids))
        return PackageComparisonResult(
            summary="Phát hiện dấu hiệu lệch phiên bản.",
            comparisons=[
                {
                    "material_question_id": next(iter(expected_question_ids)),
                    "answer_key_entry_id": next(iter(expected_entry_ids)),
                    "question_number": "13/14",
                    "status": "version_mismatch",
                    "explanation": "Số câu lệch nhất quán giữa hai file.",
                    "confidence": 0.9,
                    "requires_human_review": True,
                }
            ],
            recommendations=[],
            limitations=[],
        )


def test_unmatched_numbers_are_sent_to_second_version_check() -> None:
    questions = StudentQuestionSet(
        source_file_name="practice.docx",
        questions=[
            {
                "question_id": "question-0013",
                "question_number": "13",
                "question_text": "Chọn đáp án.",
                "options": ["A", "B"],
                "independent_answer": "A",
                "reasoning_summary": "A phù hợp.",
                "confidence": 0.9,
                "block_id": "block-0001",
                "source_file_name": "practice.docx",
            }
        ],
        summary="Một câu.",
        limitations=[],
    )
    answer_key = AnswerKeyProfile(
        source_file_name="key.docx",
        entries=[
            {
                "entry_id": "answer-0014",
                "question_number": "14",
                "official_answer": "B",
                "block_id": "block-0001",
                "source_file_name": "key.docx",
            }
        ],
        summary="Một đáp án.",
        limitations=[],
    )
    ai = FakeVersionCheckAI()

    result = compare_learning_package(
        lesson_plan=lesson_plan(),
        teaching_context=teaching_context(),
        questions=questions,
        answer_key=answer_key,
        ai_service=ai,
    )

    assert ai.calls == [({"question-0013"}, {"answer-0014"})]
    assert [item.status.value for item in result.comparisons] == ["version_mismatch"]
