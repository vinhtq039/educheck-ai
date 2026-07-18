from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class LessonPlanProfile(BaseModel):
    """Structured teaching context extracted from the lesson plan."""

    model_config = ConfigDict(extra="forbid")

    source_document_type: str
    subject: str | None = None
    grade_level: str | None = None
    topic: str | None = None
    objectives: list[str] = Field(default_factory=list)
    knowledge_scope: list[str] = Field(default_factory=list)
    skills_and_competencies: list[str] = Field(default_factory=list)
    learning_activities: list[str] = Field(default_factory=list)
    assessment_criteria: list[str] = Field(default_factory=list)
    required_materials: list[str] = Field(default_factory=list)
    key_terms: list[str] = Field(default_factory=list)
    summary: str
    uncertainties: list[str] = Field(default_factory=list)

    @field_validator("summary")
    @classmethod
    def summary_must_not_be_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Tóm tắt giáo án không được để trống.")
        if len(value) > 800:
            raise ValueError("Tóm tắt giáo án không được vượt quá 800 ký tự.")
        return value

    @model_validator(mode="after")
    def keep_profile_compact(self) -> "LessonPlanProfile":
        list_fields = (
            "objectives",
            "knowledge_scope",
            "skills_and_competencies",
            "learning_activities",
            "assessment_criteria",
            "required_materials",
            "key_terms",
            "uncertainties",
        )
        for field_name in list_fields:
            values = getattr(self, field_name)
            if len(values) > 20:
                raise ValueError(f"{field_name} không được vượt quá 20 mục.")
            if any(not value.strip() or len(value) > 400 for value in values):
                raise ValueError(
                    f"Mỗi mục trong {field_name} phải có 1-400 ký tự."
                )
        return self


class AnalysisPackage(BaseModel):
    """Downloadable result that preserves the two-document relationship."""

    model_config = ConfigDict(extra="forbid")

    lesson_plan_file_name: str
    learning_material_file_name: str
    lesson_plan: LessonPlanProfile
    learning_material_analysis: "AnalysisResult"


from schemas.analysis import AnalysisResult  # noqa: E402

AnalysisPackage.model_rebuild()
