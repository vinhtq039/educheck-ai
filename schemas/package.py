from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class TeachingContextProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_file_names: list[str]
    covered_content: list[str]
    key_terms: list[str]
    worked_examples: list[str]
    instructions_and_conventions: list[str]
    summary: str
    uncertainties: list[str]

    @model_validator(mode="after")
    def keep_compact(self) -> "TeachingContextProfile":
        if not self.summary.strip() or len(self.summary) > 800:
            raise ValueError("Tóm tắt tài liệu dạy phải có 1-800 ký tự.")
        for field_name in (
            "source_file_names",
            "covered_content",
            "key_terms",
            "worked_examples",
            "instructions_and_conventions",
            "uncertainties",
        ):
            values = getattr(self, field_name)
            if len(values) > 30:
                raise ValueError(f"{field_name} không được vượt quá 30 mục.")
            if any(not value.strip() or len(value) > 500 for value in values):
                raise ValueError(f"Mỗi mục trong {field_name} phải có 1-500 ký tự.")
        return self


class MaterialScope(BaseModel):
    """Phạm vi nhận diện được của một học liệu hoặc phần đáp án."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    unit: str | None = None
    part: str | None = None
    section: str | None = None
    question_numbers: list[str] = Field(default_factory=list)
    evidence: str | None = None
    confidence: float = Field(default=0.0, ge=0, le=1)
    requires_human_review: bool = False

    @model_validator(mode="after")
    def keep_scope_reliable(self) -> "MaterialScope":
        if len(self.question_numbers) > 300:
            raise ValueError("Phạm vi không được chứa quá 300 số câu.")
        if self.evidence and len(self.evidence) > 600:
            raise ValueError("Căn cứ xác định phạm vi vượt quá 600 ký tự.")
        if self.confidence < 0.7 and any(
            (self.title, self.unit, self.part, self.section)
        ) and not self.requires_human_review:
            raise ValueError(
                "Phạm vi có độ tin cậy dưới 0.7 phải yêu cầu giáo viên xác minh."
            )
        return self


class EvidenceReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    source: str
    location: str
    excerpt: str

    @field_validator("evidence_id", "source", "location", "excerpt")
    @classmethod
    def required_evidence_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Dẫn chứng không được để trống.")
        return value

    @model_validator(mode="after")
    def constrain_evidence(self) -> "EvidenceReference":
        if len(self.evidence_id) > 200 or len(self.source) > 300:
            raise ValueError("Định danh hoặc nguồn dẫn chứng quá dài.")
        if len(self.location) > 200 or len(self.excerpt) > 1200:
            raise ValueError("Vị trí hoặc trích đoạn dẫn chứng quá dài.")
        return self


class QuestionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: str
    question_number: str
    question_text: str
    options: list[str]
    independent_answer: str | None = None
    reasoning_summary: str
    confidence: float = Field(ge=0, le=1)
    page_number: int | None = Field(default=None, ge=1)
    block_id: str | None = None
    source_file_name: str
    scope_label: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    evidence: list[EvidenceReference] = Field(default_factory=list)
    requires_human_review: bool = False

    @field_validator(
        "question_id",
        "question_number",
        "question_text",
        "reasoning_summary",
        "source_file_name",
    )
    @classmethod
    def required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Không được để trống.")
        return value

    @model_validator(mode="after")
    def constrain_question(self) -> "QuestionRecord":
        if len(self.question_text) > 3000:
            raise ValueError("Câu hỏi vượt quá 3000 ký tự.")
        if len(self.reasoning_summary) > 600:
            raise ValueError("Giải thích đáp án vượt quá 600 ký tự.")
        if len(self.options) > 12:
            raise ValueError("Một câu không được có quá 12 phương án.")
        if any(not option.strip() or len(option) > 1000 for option in self.options):
            raise ValueError("Mỗi phương án phải có 1-1000 ký tự.")
        if len(self.evidence_ids) > 8 or any(
            not item.strip() or len(item) > 200 for item in self.evidence_ids
        ):
            raise ValueError("Mỗi câu chỉ được có tối đa 8 mã dẫn chứng hợp lệ.")
        if len(self.evidence) > 8:
            raise ValueError("Mỗi câu chỉ được lưu tối đa 8 trích đoạn dẫn chứng.")
        if {item.evidence_id for item in self.evidence} - set(self.evidence_ids):
            raise ValueError("Trích đoạn dẫn chứng phải thuộc evidence_ids đã chọn.")
        if self.confidence < 0.7 and not self.requires_human_review:
            raise ValueError(
                "Đáp án độc lập confidence dưới 0.7 phải yêu cầu xác minh."
            )
        return self


class ExtractedQuestion(BaseModel):
    """Question structure extracted before any independent solving."""

    model_config = ConfigDict(extra="forbid")

    question_number: str
    question_text: str
    options: list[str]
    page_number: int | None = Field(default=None, ge=1)
    block_id: str | None = None
    scope_label: str | None = None
    confidence: float = Field(ge=0, le=1)
    requires_human_review: bool = False

    @field_validator("question_number", "question_text")
    @classmethod
    def required_question_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Câu hỏi trích xuất không được để trống.")
        return value

    @model_validator(mode="after")
    def constrain_extracted_question(self) -> "ExtractedQuestion":
        if len(self.question_text) > 3000:
            raise ValueError("Câu hỏi vượt quá 3000 ký tự.")
        if len(self.options) > 12 or any(
            not option.strip() or len(option) > 1000 for option in self.options
        ):
            raise ValueError("Danh sách phương án không hợp lệ.")
        if self.confidence < 0.7 and not self.requires_human_review:
            raise ValueError(
                "Câu hỏi trích xuất confidence dưới 0.7 phải yêu cầu xác minh."
            )
        return self


class ExtractedQuestionSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    questions: list[ExtractedQuestion]
    summary: str
    limitations: list[str]
    scope: MaterialScope = Field(default_factory=MaterialScope)

    @model_validator(mode="after")
    def keep_extraction_bounded(self) -> "ExtractedQuestionSet":
        if len(self.questions) > 100:
            raise ValueError("Một phần tài liệu không được trả quá 100 câu hỏi.")
        if not self.summary.strip() or len(self.summary) > 800:
            raise ValueError("Tóm tắt câu hỏi phải có 1-800 ký tự.")
        if len(self.limitations) > 8 or any(
            not item.strip() or len(item) > 400 for item in self.limitations
        ):
            raise ValueError("Giới hạn trích xuất không hợp lệ.")
        return self


class QuestionSolution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: str
    independent_answer: str | None = None
    reasoning_summary: str
    confidence: float = Field(ge=0, le=1)
    evidence_ids: list[str] = Field(default_factory=list)
    requires_human_review: bool = False

    @field_validator("question_id", "reasoning_summary")
    @classmethod
    def required_solution_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Lời giải không được để trống.")
        return value

    @model_validator(mode="after")
    def constrain_solution(self) -> "QuestionSolution":
        if len(self.reasoning_summary) > 400:
            raise ValueError("Lập luận tóm tắt vượt quá 400 ký tự.")
        if len(self.evidence_ids) > 8 or any(
            not item.strip() or len(item) > 200 for item in self.evidence_ids
        ):
            raise ValueError("Danh sách dẫn chứng lời giải không hợp lệ.")
        if self.confidence < 0.7 and not self.requires_human_review:
            raise ValueError(
                "Lời giải confidence dưới 0.7 phải yêu cầu xác minh."
            )
        return self


class QuestionSolutionSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    solutions: list[QuestionSolution]
    limitations: list[str]

    @model_validator(mode="after")
    def keep_solutions_bounded(self) -> "QuestionSolutionSet":
        if len(self.solutions) > 50:
            raise ValueError("Không được giải quá 50 câu trong một nhóm.")
        if len(self.limitations) > 8 or any(
            not item.strip() or len(item) > 400 for item in self.limitations
        ):
            raise ValueError("Giới hạn lời giải không hợp lệ.")
        return self


class StudentQuestionSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_file_name: str
    questions: list[QuestionRecord]
    summary: str
    limitations: list[str]
    scope: MaterialScope = Field(default_factory=MaterialScope)


class AnswerKeyEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entry_id: str
    question_number: str
    official_answer: str
    explanation: str | None = None
    page_number: int | None = Field(default=None, ge=1)
    block_id: str | None = None
    source_file_name: str
    scope_label: str | None = None

    @field_validator(
        "entry_id",
        "question_number",
        "official_answer",
        "source_file_name",
    )
    @classmethod
    def required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Không được để trống.")
        return value


class AnswerKeyProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_file_name: str
    entries: list[AnswerKeyEntry]
    summary: str
    limitations: list[str]
    target_scope: MaterialScope = Field(default_factory=MaterialScope)
    ignored_out_of_scope_count: int = Field(default=0, ge=0)
    ignored_scope_notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def keep_scope_notes_compact(self) -> "AnswerKeyProfile":
        if len(self.ignored_scope_notes) > 20:
            raise ValueError("Không được trả quá 20 ghi chú ngoài phạm vi.")
        if any(not item.strip() or len(item) > 500 for item in self.ignored_scope_notes):
            raise ValueError("Ghi chú ngoài phạm vi phải có 1-500 ký tự.")
        return self


class ComparisonStatus(str, Enum):
    MATCH = "match"
    CONFLICT = "conflict"
    AI_DISAGREEMENT = "ai_disagreement"
    AMBIGUOUS = "ambiguous"
    MISSING_KEY = "missing_key"
    KEY_EXTRACTION_UNCERTAIN = "key_extraction_uncertain"
    ORPHAN_KEY = "orphan_key"
    VERSION_MISMATCH = "version_mismatch"


class AnswerComparison(BaseModel):
    model_config = ConfigDict(extra="forbid")

    material_question_id: str | None = None
    answer_key_entry_id: str | None = None
    question_number: str
    status: ComparisonStatus
    independent_answer: str | None = None
    official_answer: str | None = None
    explanation: str
    lesson_plan_reference: str | None = None
    teaching_material_reference: str | None = None
    confidence: float = Field(ge=0, le=1)
    requires_human_review: bool

    @model_validator(mode="after")
    def validate_comparison(self) -> "AnswerComparison":
        if not self.material_question_id and not self.answer_key_entry_id:
            raise ValueError("Đối chiếu phải tham chiếu ít nhất một nguồn.")
        if not self.explanation.strip() or len(self.explanation) > 700:
            raise ValueError("Giải thích đối chiếu phải có 1-700 ký tự.")
        if self.confidence < 0.7 and not self.requires_human_review:
            raise ValueError(
                "Đối chiếu confidence dưới 0.7 phải yêu cầu xác minh."
            )
        paired_statuses = {
            ComparisonStatus.MATCH,
            ComparisonStatus.CONFLICT,
            ComparisonStatus.AI_DISAGREEMENT,
            ComparisonStatus.AMBIGUOUS,
            ComparisonStatus.VERSION_MISMATCH,
        }
        if self.status in paired_statuses and (
            not self.material_question_id or not self.answer_key_entry_id
        ):
            raise ValueError(
                f"Trạng thái {self.status.value} phải có cả câu hỏi và mục đáp án."
            )
        if self.status in {
            ComparisonStatus.MATCH,
            ComparisonStatus.CONFLICT,
            ComparisonStatus.AI_DISAGREEMENT,
        } and (not self.independent_answer or not self.official_answer):
            raise ValueError(
                f"Trạng thái {self.status.value} phải có đủ hai đáp án để so sánh."
            )
        if self.status in {
            ComparisonStatus.MISSING_KEY,
            ComparisonStatus.KEY_EXTRACTION_UNCERTAIN,
        } and (
            not self.material_question_id
            or self.answer_key_entry_id is not None
            or bool(self.official_answer and self.official_answer.strip())
        ):
            raise ValueError(
                f"{self.status.value} chỉ được tham chiếu câu hỏi và không được có "
                "đáp án chính thức."
            )
        if self.status == ComparisonStatus.ORPHAN_KEY and (
            self.material_question_id is not None
            or not self.answer_key_entry_id
            or bool(self.independent_answer and self.independent_answer.strip())
        ):
            raise ValueError(
                "orphan_key chỉ được tham chiếu mục đáp án và không được có lời giải độc lập."
            )
        if (
            self.status not in {ComparisonStatus.MATCH, ComparisonStatus.ORPHAN_KEY}
            and not self.requires_human_review
        ):
            raise ValueError(
                "Mọi kết quả cần xử lý phải được giáo viên xác minh."
            )
        return self


class PackageComparisonResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str
    comparisons: list[AnswerComparison]
    recommendations: list[str]
    limitations: list[str]

    @model_validator(mode="after")
    def keep_focused(self) -> "PackageComparisonResult":
        if not self.summary.strip() or len(self.summary) > 800:
            raise ValueError("Tóm tắt đối chiếu phải có 1-800 ký tự.")
        if len(self.recommendations) > 5 or len(self.limitations) > 8:
            raise ValueError("Đối chiếu trả quá nhiều đề xuất hoặc giới hạn.")
        return self
