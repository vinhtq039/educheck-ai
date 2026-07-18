from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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


LESSON_PLAN_EVIDENCE_CATEGORIES = {
    IssueCategory.OUT_OF_SCOPE,
    IssueCategory.GRADE_LEVEL_MISMATCH,
    IssueCategory.LEARNING_OBJECTIVE_MISMATCH,
}


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
    lesson_plan_reference: str | None = None
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

    @field_validator(
        "lesson_plan_reference",
        "suggested_text",
        "replacement_question",
        "suggested_answer",
        mode="before",
    )
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @model_validator(mode="after")
    def enforce_focused_output(self) -> "AnalysisIssue":
        limits = {
            "original_text": 1200,
            "explanation": 600,
            "lesson_plan_reference": 500,
            "suggested_text": 1200,
            "replacement_question": 2000,
            "suggested_answer": 1200,
        }
        for field_name, limit in limits.items():
            value = getattr(self, field_name)
            if value is not None and len(value) > limit:
                raise ValueError(f"{field_name} vượt quá {limit} ký tự.")
        if (
            self.category in LESSON_PLAN_EVIDENCE_CATEGORIES
            and not self.lesson_plan_reference
        ):
            raise ValueError(
                "Vấn đề về độ phù hợp phải nêu căn cứ cụ thể từ giáo án."
            )
        if self.severity == IssueSeverity.CRITICAL and self.confidence < 0.8:
            raise ValueError("Vấn đề nghiêm trọng phải có confidence từ 0.8 trở lên.")
        if self.confidence < 0.7 and not self.requires_human_review:
            raise ValueError(
                "Vấn đề confidence dưới 0.7 phải yêu cầu giáo viên xác minh."
            )
        return self


class DocumentSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_type: str
    detected_languages: list[str]
    detected_subject: str | None = None
    detected_grade_level: str | None = None
    total_questions: int | None = Field(default=None, ge=0)
    summary: str

    @field_validator("summary")
    @classmethod
    def concise_summary(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Tóm tắt không được để trống.")
        if len(value) > 800:
            raise ValueError("Tóm tắt không được vượt quá 800 ký tự.")
        return value


class AnalysisResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_summary: DocumentSummary
    issues: list[AnalysisIssue]
    general_recommendations: list[str]
    limitations: list[str]

    @model_validator(mode="after")
    def constrain_lists(self) -> "AnalysisResult":
        if len(self.general_recommendations) > 5:
            raise ValueError("Chỉ được trả tối đa 5 đề xuất chung.")
        if len(self.limitations) > 8:
            raise ValueError("Chỉ được trả tối đa 8 giới hạn.")
        for value in self.general_recommendations + self.limitations:
            if not value.strip():
                raise ValueError("Đề xuất và giới hạn không được để trống.")
            if len(value) > 400:
                raise ValueError("Đề xuất và giới hạn không được vượt quá 400 ký tự.")
        return self
