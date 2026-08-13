from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from config.settings import Settings
from prompts.answer_key_prompt import build_answer_key_prompt
from prompts.package_comparison_prompt import build_package_comparison_prompt
from prompts.question_extraction_prompt import build_question_extraction_prompt
from prompts.question_solving_prompt import build_question_solving_prompt
from prompts.teaching_context_prompt import build_teaching_context_prompt
from schemas.analysis import AnalysisResult, DocumentSummary
from schemas.document import DocumentType, ParsedDocument
from schemas.lesson_plan import LessonPlanProfile
from schemas.package import (
    AnswerComparison,
    AnswerKeyEntry,
    AnswerKeyProfile,
    ComparisonStatus,
    ExtractedQuestion,
    MaterialScope,
    PackageComparisonResult,
    QuestionRecord,
    StudentQuestionSet,
    TeachingContextProfile,
)
from services.chunk_service import chunk_document
from services.context_retrieval_service import (
    RetrievalDocument,
    retrieve_evidence_for_questions,
)
from services.openai_service import OpenAIService
from utils.text_utils import similarity_key
from utils.validators import FileValidationError


ProgressCallback = Callable[[str, float], None]


@dataclass(frozen=True, slots=True)
class SourceDocument:
    file_name: str
    data: bytes
    parsed: ParsedDocument


def build_quick_analysis_result(
    parsed: ParsedDocument,
    questions: StudentQuestionSet,
) -> AnalysisResult:
    """Create a placeholder when optional English review is skipped."""

    return AnalysisResult(
        document_summary=DocumentSummary(
            document_type=parsed.document_type.value,
            detected_languages=[],
            total_questions=len(questions.questions),
            summary=(
                "Đã kiểm tra nhanh phạm vi, câu hỏi và đáp án. "
                "Chưa chạy kiểm tra chi tiết tiếng Anh và chất lượng đề."
            ),
        ),
        issues=[],
        general_recommendations=[],
        limitations=[
            "Chế độ kiểm tra nhanh không rà soát toàn diện chất lượng tiếng Anh."
        ],
    )


def _unique(values: list[str], limit: int) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        value = value.strip()
        key = similarity_key(value)
        if value and key not in seen:
            seen.add(key)
            result.append(value)
        if len(result) == limit:
            break
    return result


def _compact_summary(values: list[str], limit: int = 800) -> str:
    summary = " ".join(_unique(values, 30))
    if not summary:
        return "Không có đủ nội dung để tóm tắt."
    if len(summary) <= limit:
        return summary
    return f"{summary[:limit].rsplit(' ', 1)[0].rstrip(' ,;:')}."


def _is_reliable_exact_answer(value: str) -> bool:
    normalized = similarity_key(value)
    return bool(normalized) and normalized not in {
        "khong xac dinh",
        "khong ro",
        "khong du du lieu",
        "unknown",
        "uncertain",
        "none",
        "na",
    }


def _question_number_key(value: str) -> str:
    """Normalize labels such as 'Câu 13.', 'Question 13' and '13'."""

    normalized = similarity_key(value)
    normalized = re.sub(
        r"^(?:cau|question|item|q)\s*[:.#-]?\s*",
        "",
        normalized,
    )
    match = re.search(r"\b(?:\d+[a-z]?|[ivxlcdm]+)\b", normalized)
    if match:
        return match.group(0)
    return normalized


def _merge_material_scopes(
    scopes: list[MaterialScope],
    question_numbers: list[str],
) -> MaterialScope:
    conflicts = False

    def consensus_value(field_name: str) -> str | None:
        nonlocal conflicts
        values = [
            value.strip()
            for scope in scopes
            if (value := getattr(scope, field_name)) and value.strip()
        ]
        if not values:
            return None
        groups: dict[str, list[str]] = {}
        for value in values:
            groups.setdefault(similarity_key(value), []).append(value)
        conflicts = conflicts or len(groups) > 1
        return max(groups.values(), key=len)[0]

    detected = any(
        getattr(scope, field_name)
        for scope in scopes
        for field_name in ("title", "unit", "part", "section")
    )
    confidence = min(
        (scope.confidence for scope in scopes if scope.confidence > 0),
        default=0.0,
    )
    title = consensus_value("title")
    unit = consensus_value("unit")
    part = consensus_value("part")
    section = consensus_value("section")
    review = any(scope.requires_human_review for scope in scopes) or conflicts
    if detected and confidence < 0.7:
        review = True
    return MaterialScope(
        title=title,
        unit=unit,
        part=part,
        section=section,
        question_numbers=_unique(
            question_numbers
            + [
                number
                for scope in scopes
                for number in scope.question_numbers
            ],
            300,
        ),
        evidence=_compact_summary(
            [scope.evidence for scope in scopes if scope.evidence],
            600,
        )
        if any(scope.evidence for scope in scopes)
        else None,
        confidence=confidence,
        requires_human_review=review,
    )


def _merge_teaching_profiles(
    profiles: list[TeachingContextProfile],
    file_names: list[str],
) -> TeachingContextProfile:
    if not profiles:
        raise FileValidationError(
            "Không tìm thấy đủ nội dung trong tài liệu giảng dạy."
        )

    def merged(field_name: str) -> list[str]:
        return _unique(
            [
                item
                for profile in profiles
                for item in getattr(profile, field_name)
            ],
            30,
        )

    return TeachingContextProfile(
        source_file_names=file_names,
        covered_content=merged("covered_content"),
        key_terms=merged("key_terms"),
        worked_examples=merged("worked_examples"),
        instructions_and_conventions=merged("instructions_and_conventions"),
        summary=_compact_summary([profile.summary for profile in profiles]),
        uncertainties=merged("uncertainties"),
    )


def analyze_teaching_materials(
    *,
    documents: list[SourceDocument],
    lesson_plan: LessonPlanProfile,
    settings: Settings,
    ai_service: OpenAIService,
    progress: ProgressCallback | None = None,
) -> TeachingContextProfile:
    if not documents:
        raise FileValidationError("Vui lòng tải ít nhất một tài liệu giảng dạy.")

    notify = progress or (lambda _message, _value: None)
    all_chunks = [
        (document, chunk)
        for document in documents
        for chunk in chunk_document(
            document.parsed,
            document.data,
            settings.pdf_pages_per_chunk,
            settings.docx_chars_per_chunk,
        )
    ]
    if not all_chunks:
        raise FileValidationError(
            "Không tìm thấy đủ nội dung trong tài liệu giảng dạy."
        )

    profiles: list[TeachingContextProfile] = []
    total = len(all_chunks)
    for index, (document, chunk) in enumerate(all_chunks, start=1):
        notify(
            f"Đang đọc tài liệu giảng dạy {index}/{total}",
            0.1 + 0.8 * (index - 1) / total,
        )
        prompt = build_teaching_context_prompt(
            file_name=document.file_name,
            document_type=document.parsed.document_type.value,
            content=chunk.content,
            lesson_plan=lesson_plan,
            chunk_label=f"phần {chunk.chunk_index}",
        )
        profile = ai_service.analyze_teaching_material_chunk(
            chunk,
            document.parsed.document_type,
            prompt,
        )
        profile.source_file_names = [document.file_name]
        profiles.append(profile)

    notify("Đang tổng hợp nội dung đã dạy", 0.95)
    result = _merge_teaching_profiles(
        profiles,
        [document.file_name for document in documents],
    )
    notify("Đã đọc xong tài liệu giảng dạy", 1.0)
    return result


def _question_location_exists(
    question: QuestionRecord | ExtractedQuestion,
    parsed: ParsedDocument,
) -> bool:
    if parsed.document_type == DocumentType.PDF:
        return question.page_number in {
            page.page_number for page in parsed.pages
        }
    return question.block_id in {
        block.block_id for block in parsed.blocks
    }


def solve_student_material(
    *,
    document: SourceDocument,
    lesson_plan: LessonPlanProfile,
    teaching_context: TeachingContextProfile,
    teaching_documents: list[SourceDocument] | None = None,
    settings: Settings,
    ai_service: OpenAIService,
    scope_request: str = "",
    progress: ProgressCallback | None = None,
) -> StudentQuestionSet:
    notify = progress or (lambda _message, _value: None)
    chunks = chunk_document(
        document.parsed,
        document.data,
        settings.pdf_pages_per_chunk,
        settings.docx_chars_per_chunk,
    )
    if not chunks:
        raise FileValidationError("Không tìm thấy câu hỏi trong học liệu.")

    extracted: list[tuple[str, ExtractedQuestion]] = []
    summaries: list[str] = []
    limitations: list[str] = list(document.parsed.warnings)
    scopes: list[MaterialScope] = []
    seen: set[tuple[str, str]] = set()
    total = len(chunks)

    for index, chunk in enumerate(chunks, start=1):
        notify(
            f"Đang tách câu hỏi phần {index}/{total}",
            0.08 + 0.34 * (index - 1) / total,
        )
        prompt = build_question_extraction_prompt(
            file_name=document.file_name,
            document_type=document.parsed.document_type.value,
            content=chunk.content,
            chunk_label=f"phần {index}/{total}",
            scope_request=scope_request,
        )
        result = ai_service.extract_student_questions_chunk(
            chunk,
            document.parsed.document_type,
            prompt,
        )
        summaries.append(result.summary)
        limitations.extend(result.limitations)
        scopes.append(result.scope)
        for question in result.questions:
            key = (
                similarity_key(question.question_number),
                similarity_key(question.question_text),
            )
            if key in seen:
                continue
            seen.add(key)
            if not _question_location_exists(question, document.parsed):
                limitations.append(
                    f"Đã bỏ câu {question.question_number} vì vị trí không tồn tại."
                )
                continue
            question_id = f"question-{len(extracted) + 1:04d}"
            extracted.append((question_id, question))
            if len(extracted) > settings.max_extracted_questions:
                raise FileValidationError(
                    "Số câu hỏi nhận diện được vượt quá giới hạn "
                    f"{settings.max_extracted_questions}. Hãy chia bài tập thành "
                    "nhiều bộ nhỏ hơn."
                )

    if not extracted:
        raise FileValidationError("Không nhận diện được câu hỏi trong học liệu.")

    notify("Đang truy xuất nội dung liên quan cho từng câu", 0.46)
    evidence_by_question = retrieve_evidence_for_questions(
        questions=extracted,
        lesson_plan=lesson_plan,
        teaching_context=teaching_context,
        teaching_documents=[
            RetrievalDocument(
                file_name=teaching_document.file_name,
                parsed=teaching_document.parsed,
            )
            for teaching_document in (teaching_documents or [])
        ],
        top_k=settings.retrieval_top_k,
        max_chars_per_question=settings.retrieval_max_chars_per_question,
    )

    solution_by_id = {}
    solving_batches = [
        extracted[index : index + settings.solving_batch_size]
        for index in range(0, len(extracted), settings.solving_batch_size)
    ]
    for batch_index, batch in enumerate(solving_batches, start=1):
        notify(
            f"Đang tự giải nhóm {batch_index}/{len(solving_batches)}",
            0.52 + 0.4 * (batch_index - 1) / len(solving_batches),
        )
        prompt = build_question_solving_prompt(
            questions=batch,
            evidence_by_question=evidence_by_question,
        )
        solved = ai_service.solve_question_batch(
            prompt,
            {question_id for question_id, _question in batch},
        )
        limitations.extend(solved.limitations)
        for solution in solved.solutions:
            allowed_evidence = {
                item["evidence_id"]
                for item in evidence_by_question.get(solution.question_id, [])
            }
            invalid_evidence = [
                item
                for item in solution.evidence_ids
                if item not in allowed_evidence
            ]
            if invalid_evidence:
                limitations.append(
                    f"Câu {solution.question_id}: đã bỏ mã dẫn chứng không có "
                    "trong dữ liệu truy xuất."
                )
                solution.evidence_ids = [
                    item
                    for item in solution.evidence_ids
                    if item in allowed_evidence
                ]
            if solution.independent_answer and not solution.evidence_ids:
                limitations.append(
                    f"Câu {solution.question_id}: lời giải chưa có dẫn chứng hợp lệ; "
                    "đã chuyển sang trạng thái cần giáo viên xác minh."
                )
                solution.confidence = min(solution.confidence, 0.69)
                solution.requires_human_review = True
            solution_by_id[solution.question_id] = solution

    questions: list[QuestionRecord] = []
    for question_id, draft in extracted:
        solution = solution_by_id[question_id]
        retrieved_by_id = {
            item["evidence_id"]: item
            for item in evidence_by_question.get(question_id, [])
        }
        confidence = min(draft.confidence, solution.confidence)
        requires_review = (
            draft.requires_human_review
            or solution.requires_human_review
            or solution.independent_answer is None
            or not solution.evidence_ids
            or confidence < 0.7
        )
        questions.append(
            QuestionRecord(
                question_id=question_id,
                question_number=draft.question_number,
                question_text=draft.question_text,
                options=draft.options,
                independent_answer=solution.independent_answer,
                reasoning_summary=solution.reasoning_summary,
                confidence=confidence,
                page_number=draft.page_number,
                block_id=draft.block_id,
                source_file_name=document.file_name,
                scope_label=draft.scope_label,
                evidence_ids=solution.evidence_ids,
                evidence=[
                    {
                        "evidence_id": evidence_id,
                        "source": retrieved_by_id[evidence_id]["source"],
                        "location": retrieved_by_id[evidence_id]["location"],
                        "excerpt": retrieved_by_id[evidence_id]["text"],
                    }
                    for evidence_id in solution.evidence_ids
                ],
                requires_human_review=requires_review,
            )
        )

    notify("Đang tổng hợp lời giải độc lập", 0.95)
    result = StudentQuestionSet(
        source_file_name=document.file_name,
        questions=questions,
        summary=_compact_summary(summaries),
        limitations=_unique(limitations, 8),
        scope=_merge_material_scopes(
            scopes,
            [question.question_number for question in questions],
        ),
    )
    notify("Đã tự giải xong học liệu", 1.0)
    return result


def _answer_location_exists(
    entry: AnswerKeyEntry,
    parsed: ParsedDocument,
) -> bool:
    if parsed.document_type == DocumentType.PDF:
        return entry.page_number in {
            page.page_number for page in parsed.pages
        }
    return entry.block_id in {
        block.block_id for block in parsed.blocks
    }


def extract_answer_key(
    *,
    document: SourceDocument,
    settings: Settings,
    ai_service: OpenAIService,
    target_scope: MaterialScope | None = None,
    progress: ProgressCallback | None = None,
) -> AnswerKeyProfile:
    notify = progress or (lambda _message, _value: None)
    target_scope = target_scope or MaterialScope()
    chunks = chunk_document(
        document.parsed,
        document.data,
        settings.pdf_pages_per_chunk,
        settings.docx_chars_per_chunk,
    )
    if not chunks:
        raise FileValidationError("Không tìm thấy nội dung trong file đáp án.")

    entries: list[AnswerKeyEntry] = []
    summaries: list[str] = []
    limitations: list[str] = list(document.parsed.warnings)
    ignored_count = 0
    ignored_notes: list[str] = []
    seen: set[tuple[str, str]] = set()
    total = len(chunks)

    for index, chunk in enumerate(chunks, start=1):
        notify(
            f"Đang trích xuất đáp án phần {index}/{total}",
            0.1 + 0.8 * (index - 1) / total,
        )
        prompt = build_answer_key_prompt(
            file_name=document.file_name,
            document_type=document.parsed.document_type.value,
            content=chunk.content,
            chunk_label=f"phần {index}/{total}",
            target_scope=target_scope,
        )
        result = ai_service.extract_answer_key_chunk(
            chunk,
            document.parsed.document_type,
            prompt,
        )
        summaries.append(result.summary)
        limitations.extend(result.limitations)
        ignored_count += result.ignored_out_of_scope_count
        ignored_notes.extend(result.ignored_scope_notes)
        for entry in result.entries:
            entry.source_file_name = document.file_name
            key = (
                similarity_key(entry.question_number),
                similarity_key(entry.official_answer),
            )
            if key in seen:
                continue
            seen.add(key)
            if not _answer_location_exists(entry, document.parsed):
                limitations.append(
                    f"Đã bỏ đáp án câu {entry.question_number} vì vị trí không tồn tại."
                )
                continue
            entry.entry_id = f"answer-{len(entries) + 1:04d}"
            entries.append(entry)

    notify("Đang tổng hợp đáp án chính thức", 0.95)
    result = AnswerKeyProfile(
        source_file_name=document.file_name,
        entries=entries,
        summary=_compact_summary(summaries),
        limitations=_unique(limitations, 8),
        target_scope=target_scope,
        ignored_out_of_scope_count=ignored_count,
        ignored_scope_notes=_unique(ignored_notes, 20),
    )
    notify("Đã trích xuất xong đáp án", 1.0)
    return result


def compare_learning_package(
    *,
    lesson_plan: LessonPlanProfile,
    teaching_context: TeachingContextProfile,
    questions: StudentQuestionSet,
    answer_key: AnswerKeyProfile,
    ai_service: OpenAIService,
    progress: ProgressCallback | None = None,
    batch_size: int = 40,
) -> PackageComparisonResult:
    notify = progress or (lambda _message, _value: None)
    if not questions.questions and not answer_key.entries:
        return PackageComparisonResult(
            summary="Không tìm thấy câu hỏi hoặc mục đáp án để đối chiếu.",
            comparisons=[],
            recommendations=[
                "Kiểm tra lại khả năng đọc nội dung của file bài tập và đáp án."
            ],
            limitations=_unique(
                questions.limitations + answer_key.limitations,
                8,
            ),
        )

    question_groups: dict[str, list[QuestionRecord]] = {}
    answer_groups: dict[str, list[AnswerKeyEntry]] = {}
    for question in questions.questions:
        key = _question_number_key(question.question_number)
        question_groups.setdefault(key, []).append(question)
    for entry in answer_key.entries:
        key = _question_number_key(entry.question_number)
        answer_groups.setdefault(key, []).append(entry)

    units: list[tuple[list[QuestionRecord], list[AnswerKeyEntry]]] = []
    matched_keys = [
        key for key in question_groups if key in answer_groups
    ]
    units.extend(
        (question_groups[key], answer_groups[key])
        for key in matched_keys
    )

    unmatched_question_groups = [
        values for key, values in question_groups.items() if key not in answer_groups
    ]
    unmatched_answer_groups = [
        values for key, values in answer_groups.items() if key not in question_groups
    ]
    deterministic: list[AnswerComparison] = []

    unresolved_units: list[tuple[list[QuestionRecord], list[AnswerKeyEntry]]] = []
    for unit_questions, unit_answers in units:
        if len(unit_questions) == 1 and len(unit_answers) == 1:
            question = unit_questions[0]
            answer = unit_answers[0]
            independent = similarity_key(question.independent_answer or "")
            official = similarity_key(answer.official_answer)
            if (
                _is_reliable_exact_answer(question.independent_answer or "")
                and _is_reliable_exact_answer(answer.official_answer)
                and independent
                and question.confidence >= 0.7
                and not question.requires_human_review
            ):
                answers_match = independent == official
                if not answers_match:
                    unresolved_units.append((unit_questions, unit_answers))
                    continue
                deterministic.append(
                    AnswerComparison(
                        material_question_id=question.question_id,
                        answer_key_entry_id=answer.entry_id,
                        question_number=question.question_number,
                        status=ComparisonStatus.MATCH,
                        independent_answer=question.independent_answer,
                        official_answer=answer.official_answer,
                        explanation="Lời giải độc lập khớp chính xác với đáp án chính thức.",
                        confidence=min(question.confidence, 0.99),
                        teaching_material_reference=(
                            ", ".join(question.evidence_ids) or None
                        ),
                        requires_human_review=False,
                    )
                )
                continue
        unresolved_units.append((unit_questions, unit_answers))

    # Numbering differences are an important signal of a version mismatch. Send
    # all unmatched records through the second verifier instead of finalizing
    # them as missing/orphan entries before verification.
    if unmatched_question_groups or unmatched_answer_groups:
        unmatched_questions = [
            question for group in unmatched_question_groups for question in group
        ]
        unmatched_answers = [
            answer for group in unmatched_answer_groups for answer in group
        ]
        per_side = max(1, batch_size // 2)
        for offset in range(
            0,
            max(len(unmatched_questions), len(unmatched_answers)),
            per_side,
        ):
            unresolved_units.append(
                (
                    unmatched_questions[offset : offset + per_side],
                    unmatched_answers[offset : offset + per_side],
                )
            )

    batches: list[tuple[list[QuestionRecord], list[AnswerKeyEntry]]] = []
    current_questions: list[QuestionRecord] = []
    current_answers: list[AnswerKeyEntry] = []
    maximum_records = max(2, batch_size)
    for unit_questions, unit_answers in unresolved_units:
        incoming = len(unit_questions) + len(unit_answers)
        current_size = len(current_questions) + len(current_answers)
        if current_size and current_size + incoming > maximum_records:
            batches.append((current_questions, current_answers))
            current_questions = []
            current_answers = []
        current_questions.extend(unit_questions)
        current_answers.extend(unit_answers)
    if current_questions or current_answers:
        batches.append((current_questions, current_answers))

    results: list[PackageComparisonResult] = []
    total = len(batches)
    for index, (batch_questions, batch_answers) in enumerate(batches, start=1):
        notify(
            f"Đang đối chiếu nhóm {index}/{total}",
            0.1 + 0.8 * (index - 1) / total,
        )
        question_subset = StudentQuestionSet(
            source_file_name=questions.source_file_name,
            questions=batch_questions,
            summary=questions.summary,
            limitations=[],
            scope=questions.scope,
        )
        answer_subset = AnswerKeyProfile(
            source_file_name=answer_key.source_file_name,
            entries=batch_answers,
            summary=answer_key.summary,
            limitations=[],
            target_scope=answer_key.target_scope,
        )
        prompt = build_package_comparison_prompt(
            lesson_plan=lesson_plan,
            teaching_context=teaching_context,
            questions=question_subset,
            answer_key=answer_subset,
        )
        results.append(
            ai_service.compare_package(
                prompt,
                {
                    question.question_id
                    for question in batch_questions
                },
                {entry.entry_id for entry in batch_answers},
            )
        )

    comparisons = deterministic + [
        comparison
        for item in results
        for comparison in item.comparisons
    ]
    normalized_comparisons: list[AnswerComparison] = []
    for comparison in comparisons:
        payload = comparison.model_dump(mode="python")
        if comparison.status == ComparisonStatus.CONFLICT:
            payload["status"] = ComparisonStatus.AI_DISAGREEMENT
            payload["explanation"] = (
                "Lời giải độc lập của AI chưa đồng thuận với đáp án chính thức. "
                "Đây không phải kết luận đáp án giáo viên sai."
            )
        elif comparison.status == ComparisonStatus.MISSING_KEY:
            payload["status"] = ComparisonStatus.KEY_EXTRACTION_UNCERTAIN
            payload["explanation"] = (
                "Hệ thống chưa trích xuất hoặc ghép được đáp án tương ứng; "
                "chưa đủ căn cứ kết luận file đáp án bị thiếu."
            )
        normalized_comparisons.append(AnswerComparison.model_validate(payload))
    comparisons = normalized_comparisons
    question_order = {
        question.question_id: index
        for index, question in enumerate(questions.questions)
    }
    answer_order = {
        entry.entry_id: index
        for index, entry in enumerate(answer_key.entries)
    }
    comparisons.sort(
        key=lambda item: (
            0 if item.material_question_id else 1,
            question_order.get(item.material_question_id or "", 10**9),
            answer_order.get(item.answer_key_entry_id or "", 10**9),
        )
    )
    status_counts = {
        status: sum(item.status == status for item in comparisons)
        for status in ComparisonStatus
    }
    actionable_count = sum(
        status_counts[status]
        for status in (
            ComparisonStatus.CONFLICT,
            ComparisonStatus.AMBIGUOUS,
            ComparisonStatus.MISSING_KEY,
            ComparisonStatus.KEY_EXTRACTION_UNCERTAIN,
            ComparisonStatus.VERSION_MISMATCH,
        )
    )
    disagreement_count = status_counts[ComparisonStatus.AI_DISAGREEMENT]
    outside_scope_count = (
        answer_key.ignored_out_of_scope_count
        + status_counts[ComparisonStatus.ORPHAN_KEY]
    )
    summary = (
        f"Đã kiểm tra {len(questions.questions)} câu bài tập: "
        f"{status_counts[ComparisonStatus.MATCH]} khớp, "
        f"{disagreement_count} lượt AI chưa đồng thuận, "
        f"{actionable_count} mục cần giáo viên xác minh."
    )
    if outside_scope_count:
        summary += (
            f" Có {outside_scope_count} mục đáp án ngoài phạm vi hoặc chưa ghép; "
            "các mục này không được tính là lỗi của bài tập."
        )

    result = PackageComparisonResult(
        summary=summary,
        comparisons=comparisons,
        recommendations=_unique(
            [
                recommendation
                for item in results
                for recommendation in item.recommendations
            ],
            5,
        ),
        limitations=_unique(
            [
                limitation
                for item in results
                for limitation in item.limitations
            ],
            8,
        ),
    )

    returned_question_ids = [
        item.material_question_id
        for item in result.comparisons
        if item.material_question_id
    ]
    returned_answer_ids = [
        item.answer_key_entry_id
        for item in result.comparisons
        if item.answer_key_entry_id
    ]
    expected_question_ids = {
        question.question_id for question in questions.questions
    }
    expected_answer_ids = {
        entry.entry_id for entry in answer_key.entries
    }
    if (
        set(returned_question_ids) != expected_question_ids
        or len(returned_question_ids) != len(set(returned_question_ids))
        or set(returned_answer_ids) != expected_answer_ids
        or len(returned_answer_ids) != len(set(returned_answer_ids))
    ):
        raise FileValidationError(
            "Kết quả đối chiếu theo nhóm bị thiếu, thừa hoặc trùng dữ liệu."
        )

    result.limitations = _unique(
        questions.limitations + answer_key.limitations + result.limitations,
        8,
    )
    notify("Đã đối chiếu xong câu hỏi và đáp án", 1.0)
    return result
