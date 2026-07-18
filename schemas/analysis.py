from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class IssueSeverity(str, Enum):
    CRITICAL = "critical"
    WARNING = "warning"
    SUGGESTION = "suggestion"


class IssueCategory(str, Enum):
    VIETNAMESE_SPELLING = "vietnamese_spelling"
    VIETNAMESE_GRAMMAR = "vietnamese_grammar"
    VIETNAMESE_EXPRESSION = "vietnamese_expression"
    ENGLISH_SPELLING = "english_spelling"
    ENGLISH_GRAMMAR = "english_grammar"
    ENGLISH_EXPRESSION = "english_expression"
    AMBIGUOUS_QUESTION = "ambiguous_question"
    MISSING_INFORMATION = "missing_information"
    CONFLICTING_INFORMATION = "conflicting_information"
    INCORRECT_ANSWER = "incorrect_answer"
    NO_CORRECT_ANSWER = "no_correct_answer"
    MULTIPLE_CORRECT_ANSWERS = "multiple_correct_answers"
    DUPLICATE_QUESTION = "duplicate_question"
    DUPLICATE_OPTION = "duplicate_option"
    QUESTION_ANSWER_MISMATCH = "question_answer_mismatch"
    OUT_OF_SCOPE = "out_of_scope"
    GRADE_LEVEL_MISMATCH = "grade_level_mismatch"
    LEARNING_OBJECTIVE_MISMATCH = "learning_objective_mismatch"
    UNCERTAIN_CONTENT = "uncertain_content"


class AnalysisIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    issue_id: str
    category: IssueCategory
    severity: IssueSeverity
    page_number: int | None = Field(default=None, ge=1)
    block_id: str | None = None
    section_title: str | None = None
    question_number: str | None = None
    original_text: str
    explanation: str
    suggested_text: str | None = None
    replacement_question: str | None = None
    suggested_answer: str | None = None
    confidence: float = Field(ge=0, le=1)
    requires_human_review: bool = False

    @field_validator("issue_id", "original_text", "explanation")
    @classmethod
    def required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Không được để trống.")
        return value


class DocumentSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_type: str
    detected_languages: list[str]
    detected_subject: str | None = None
    detected_grade_level: str | None = None
    total_questions: int | None = Field(default=None, ge=0)
    summary: str


class AnalysisResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_summary: DocumentSummary
    issues: list[AnalysisIssue]
    general_recommendations: list[str]
    limitations: list[str]

