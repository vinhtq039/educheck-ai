from __future__ import annotations

from schemas.document import DocumentBlock, DocumentType, ParsedDocument
from schemas.lesson_plan import LessonPlanProfile
from schemas.package import ExtractedQuestion, TeachingContextProfile
from services.context_retrieval_service import (
    RetrievalDocument,
    build_evidence_corpus,
    retrieve_evidence_for_questions,
)


def test_retrieval_selects_relevant_teaching_block_with_a_stable_citation() -> None:
    lesson = LessonPlanProfile(
        source_document_type="docx",
        subject="Tiếng Anh",
        topic="KET Reading Part 3",
        objectives=["Chọn phản hồi phù hợp trong hội thoại."],
        knowledge_scope=["Hội thoại tại nhà ga."],
        summary="Luyện đọc hội thoại ngắn.",
    )
    teaching = TeachingContextProfile(
        source_file_names=["slides.docx"],
        covered_content=["Reading Part 3"],
        key_terms=["train station", "ticket"],
        worked_examples=[],
        instructions_and_conventions=["Đọc lượt thoại trước và sau chỗ trống."],
        summary="Tài liệu hướng dẫn chọn phản hồi theo ngữ cảnh.",
        uncertainties=[],
    )
    document = RetrievalDocument(
        file_name="slides.docx",
        parsed=ParsedDocument(
            document_type=DocumentType.DOCX,
            blocks=[
                DocumentBlock(
                    block_id="block-0001",
                    block_type="paragraph",
                    text=(
                        "At the train station, read the previous line before "
                        "choosing the correct response about a ticket."
                    ),
                    order=1,
                ),
                DocumentBlock(
                    block_id="block-0002",
                    block_type="paragraph",
                    text="Unrelated notes about food and weather.",
                    order=2,
                ),
            ],
        ),
    )
    question = ExtractedQuestion(
        question_number="7",
        question_text="Which response is correct at the train station?",
        options=["I need a ticket.", "It is raining."],
        block_id="block-0001",
        confidence=0.95,
    )

    result = retrieve_evidence_for_questions(
        questions=[("question-0007", question)],
        lesson_plan=lesson,
        teaching_context=teaching,
        teaching_documents=[document],
        top_k=3,
        max_chars_per_question=2000,
    )

    evidence = result["question-0007"]
    assert any(
        item["evidence_id"].startswith("teaching:slides-docx:block-0001")
        for item in evidence
    )
    assert not any("food and weather" in item["text"] for item in evidence)
    assert all(
        set(item) == {"evidence_id", "source", "location", "text"}
        for item in evidence
    )


def test_retrieval_falls_back_to_compact_profiles_when_no_term_matches() -> None:
    lesson = LessonPlanProfile(
        source_document_type="docx",
        summary="Phạm vi giáo án đã chuẩn hóa.",
    )
    teaching = TeachingContextProfile(
        source_file_names=["slides.docx"],
        covered_content=[],
        key_terms=[],
        worked_examples=[],
        instructions_and_conventions=[],
        summary="Nội dung thực tế đã dạy.",
        uncertainties=[],
    )
    question = ExtractedQuestion(
        question_number="1",
        question_text="XYZ?",
        options=[],
        block_id="block-0001",
        confidence=0.8,
    )

    result = retrieve_evidence_for_questions(
        questions=[("question-0001", question)],
        lesson_plan=lesson,
        teaching_context=teaching,
        teaching_documents=[],
        top_k=4,
        max_chars_per_question=1000,
    )

    assert {
        item["evidence_id"] for item in result["question-0001"]
    } == {"lesson:summary:1", "taught:summary:1"}


def test_document_evidence_ids_remain_unique_for_similar_file_names() -> None:
    lesson = LessonPlanProfile(
        source_document_type="docx",
        summary="Lesson summary.",
    )
    teaching = TeachingContextProfile(
        source_file_names=["Slide 1.docx", "Slide-1.docx"],
        covered_content=[],
        key_terms=[],
        worked_examples=[],
        instructions_and_conventions=[],
        summary="Teaching summary.",
        uncertainties=[],
    )
    documents = [
        RetrievalDocument(
            file_name=file_name,
            parsed=ParsedDocument(
                document_type=DocumentType.DOCX,
                blocks=[
                    DocumentBlock(
                        block_id="block-0001",
                        block_type="paragraph",
                        text=text,
                        order=1,
                    )
                ],
            ),
        )
        for file_name, text in (
            ("Slide 1.docx", "First source."),
            ("Slide-1.docx", "Second source."),
        )
    ]

    corpus = build_evidence_corpus(
        lesson_plan=lesson,
        teaching_context=teaching,
        teaching_documents=documents,
    )
    document_ids = [
        snippet.evidence_id
        for snippet in corpus
        if snippet.evidence_id.startswith("teaching:")
    ]

    assert len(document_ids) == 2
    assert len(set(document_ids)) == 2
    assert any("document-001" in evidence_id for evidence_id in document_ids)
    assert any("document-002" in evidence_id for evidence_id in document_ids)
