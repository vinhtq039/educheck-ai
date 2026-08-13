from __future__ import annotations

import re
from dataclasses import dataclass

from schemas.document import DocumentType, ParsedDocument
from schemas.lesson_plan import LessonPlanProfile
from schemas.package import ExtractedQuestion, TeachingContextProfile
from utils.text_utils import similarity_key


_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "cau",
    "choose",
    "chọn",
    "correct",
    "do",
    "đúng",
    "for",
    "from",
    "hãy",
    "in",
    "is",
    "là",
    "of",
    "or",
    "the",
    "to",
    "trong",
    "và",
    "which",
}


@dataclass(frozen=True, slots=True)
class RetrievalDocument:
    file_name: str
    parsed: ParsedDocument


@dataclass(frozen=True, slots=True)
class EvidenceSnippet:
    evidence_id: str
    source: str
    location: str
    text: str

    def as_prompt_payload(self) -> dict[str, str]:
        return {
            "evidence_id": self.evidence_id,
            "source": self.source,
            "location": self.location,
            "text": self.text,
        }


def _terms(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", similarity_key(text))
        if len(token) > 1 and token not in _STOPWORDS
    }


def _split_text(text: str, limit: int = 1200) -> list[str]:
    normalized = " ".join(text.split())
    if not normalized:
        return []
    if len(normalized) <= limit:
        return [normalized]
    parts: list[str] = []
    remaining = normalized
    while remaining:
        if len(remaining) <= limit:
            parts.append(remaining)
            break
        cut = remaining.rfind(" ", 0, limit + 1)
        if cut < limit // 2:
            cut = limit
        parts.append(remaining[:cut].strip())
        remaining = remaining[cut:].strip()
    return parts


def _profile_snippets(
    lesson_plan: LessonPlanProfile,
    teaching_context: TeachingContextProfile,
) -> list[EvidenceSnippet]:
    snippets: list[EvidenceSnippet] = []
    lesson_fields = (
        ("summary", [lesson_plan.summary]),
        ("objective", lesson_plan.objectives),
        ("knowledge", lesson_plan.knowledge_scope),
        ("skill", lesson_plan.skills_and_competencies),
        ("criterion", lesson_plan.assessment_criteria),
        ("term", lesson_plan.key_terms),
    )
    for field_name, values in lesson_fields:
        for index, value in enumerate(values, start=1):
            if value.strip():
                snippets.append(
                    EvidenceSnippet(
                        evidence_id=f"lesson:{field_name}:{index}",
                        source="Giáo án",
                        location=field_name,
                        text=value.strip(),
                    )
                )

    teaching_fields = (
        ("summary", [teaching_context.summary]),
        ("covered", teaching_context.covered_content),
        ("term", teaching_context.key_terms),
        ("example", teaching_context.worked_examples),
        ("instruction", teaching_context.instructions_and_conventions),
    )
    for field_name, values in teaching_fields:
        for index, value in enumerate(values, start=1):
            if value.strip():
                snippets.append(
                    EvidenceSnippet(
                        evidence_id=f"taught:{field_name}:{index}",
                        source="Hồ sơ nội dung đã dạy",
                        location=field_name,
                        text=value.strip(),
                    )
                )
    return snippets


def _document_snippets(
    documents: list[RetrievalDocument],
) -> list[EvidenceSnippet]:
    snippets: list[EvidenceSnippet] = []
    for document_index, document in enumerate(documents, start=1):
        safe_source = re.sub(r"[^a-z0-9]+", "-", similarity_key(document.file_name))
        safe_source = safe_source.strip("-") or f"file-{document_index}"
        if document.parsed.document_type == DocumentType.PDF:
            for page in document.parsed.pages:
                for part_index, text in enumerate(_split_text(page.text), start=1):
                    snippets.append(
                        EvidenceSnippet(
                            evidence_id=(
                                f"teaching:{safe_source}:page-{page.page_number}"
                                f":document-{document_index:03d}:part-{part_index}"
                            ),
                            source=document.file_name,
                            location=f"Trang {page.page_number}",
                            text=text,
                        )
                    )
        else:
            for block in document.parsed.blocks:
                block_text = block.text
                if block.rows:
                    block_text = " | ".join(
                        " ; ".join(cell for cell in row if cell)
                        for row in block.rows
                    ) or block_text
                for part_index, text in enumerate(_split_text(block_text), start=1):
                    snippets.append(
                        EvidenceSnippet(
                            evidence_id=(
                                f"teaching:{safe_source}:{block.block_id}"
                                f":document-{document_index:03d}:part-{part_index}"
                            ),
                            source=document.file_name,
                            location=block.block_id,
                            text=text,
                        )
                    )
    return snippets


def build_evidence_corpus(
    *,
    lesson_plan: LessonPlanProfile,
    teaching_context: TeachingContextProfile,
    teaching_documents: list[RetrievalDocument],
) -> list[EvidenceSnippet]:
    # Prefer original page/block provenance over synthesized profile text when the
    # same sentence occurs in both places.
    combined = _document_snippets(teaching_documents) + _profile_snippets(
        lesson_plan,
        teaching_context,
    )
    seen: set[str] = set()
    seen_ids: set[str] = set()
    unique: list[EvidenceSnippet] = []
    for snippet in combined:
        if snippet.evidence_id in seen_ids:
            raise ValueError(
                f"Mã dẫn chứng bị trùng trong cùng bộ học liệu: {snippet.evidence_id}"
            )
        seen_ids.add(snippet.evidence_id)
        key = similarity_key(snippet.text)
        if key and key not in seen:
            seen.add(key)
            unique.append(snippet)
    return unique


def retrieve_question_evidence(
    *,
    question: ExtractedQuestion,
    corpus: list[EvidenceSnippet],
    top_k: int,
    max_chars: int,
) -> list[EvidenceSnippet]:
    query = " ".join(
        [question.question_text, *question.options, question.scope_label or ""]
    )
    query_terms = _terms(query)
    scored: list[tuple[float, int, EvidenceSnippet]] = []
    for index, snippet in enumerate(corpus):
        snippet_terms = _terms(snippet.text)
        overlap = query_terms & snippet_terms
        if not overlap:
            continue
        coverage = len(overlap) / max(1, len(query_terms))
        density = len(overlap) / max(1, len(snippet_terms))
        scope_bonus = (
            0.25
            if question.scope_label
            and similarity_key(question.scope_label) in similarity_key(snippet.text)
            else 0.0
        )
        scored.append((2 * coverage + density + scope_bonus, -index, snippet))

    ranked = [
        item[2]
        for item in sorted(scored, key=lambda item: (item[0], item[1]), reverse=True)
    ]
    if not ranked:
        ranked = [
            snippet
            for snippet in corpus
            if snippet.evidence_id in {"lesson:summary:1", "taught:summary:1"}
        ]

    selected: list[EvidenceSnippet] = []
    used_chars = 0
    for snippet in ranked:
        if len(selected) >= top_k:
            break
        if selected and used_chars + len(snippet.text) > max_chars:
            continue
        selected.append(snippet)
        used_chars += len(snippet.text)
    return selected


def retrieve_evidence_for_questions(
    *,
    questions: list[tuple[str, ExtractedQuestion]],
    lesson_plan: LessonPlanProfile,
    teaching_context: TeachingContextProfile,
    teaching_documents: list[RetrievalDocument],
    top_k: int,
    max_chars_per_question: int,
) -> dict[str, list[dict[str, str]]]:
    corpus = build_evidence_corpus(
        lesson_plan=lesson_plan,
        teaching_context=teaching_context,
        teaching_documents=teaching_documents,
    )
    return {
        question_id: [
            snippet.as_prompt_payload()
            for snippet in retrieve_question_evidence(
                question=question,
                corpus=corpus,
                top_k=top_k,
                max_chars=max_chars_per_question,
            )
        ]
        for question_id, question in questions
    }
