from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from schemas.analysis import IssueSeverity


class ReviewAction(str, Enum):
    KEEP = "keep"
    REVISE = "revise"
    REMOVE = "remove"


class IssueReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    issue_id: str
    action: ReviewAction
    severity: IssueSeverity
    confidence: float = Field(ge=0, le=1)
    explanation: str
    lesson_plan_reference: str | None = None
    suggested_text: str | None = None
    requires_human_review: bool
    review_reason: str

    @field_validator("issue_id", "explanation", "review_reason")
    @classmethod
    def required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Không được để trống.")
        return value

    @model_validator(mode="after")
    def keep_review_compact(self) -> "IssueReview":
        for field_name, limit in (
            ("explanation", 600),
            ("lesson_plan_reference", 500),
            ("suggested_text", 1200),
            ("review_reason", 300),
        ):
            value = getattr(self, field_name)
            if value is not None and len(value) > limit:
                raise ValueError(f"{field_name} vượt quá {limit} ký tự.")
        if self.severity == IssueSeverity.CRITICAL and self.confidence < 0.8:
            raise ValueError("Vấn đề nghiêm trọng phải có confidence từ 0.8 trở lên.")
        if self.confidence < 0.7 and not self.requires_human_review:
            raise ValueError(
                "Vấn đề confidence dưới 0.7 phải yêu cầu giáo viên xác minh."
            )
        return self


class FinalReviewResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str
    reviews: list[IssueReview]
    general_recommendations: list[str]
    limitations: list[str]

    @model_validator(mode="after")
    def constrain_output(self) -> "FinalReviewResult":
        self.summary = self.summary.strip()
        if not self.summary or len(self.summary) > 800:
            raise ValueError("Tóm tắt kiểm duyệt phải có 1-800 ký tự.")
        if len(self.general_recommendations) > 5:
            raise ValueError("Chỉ được trả tối đa 5 đề xuất chung.")
        if len(self.limitations) > 8:
            raise ValueError("Chỉ được trả tối đa 8 giới hạn.")
        if len(self.reviews) > 500:
            raise ValueError("Danh sách kiểm duyệt vượt quá giới hạn.")
        for value in self.general_recommendations + self.limitations:
            if not value.strip() or len(value) > 400:
                raise ValueError(
                    "Đề xuất và giới hạn kiểm duyệt phải có 1-400 ký tự."
                )
        return self
