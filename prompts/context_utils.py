from __future__ import annotations

from schemas.lesson_plan import LessonPlanProfile
from schemas.package import TeachingContextProfile


def compact_lesson_context(profile: LessonPlanProfile) -> dict:
    return {
        "subject": profile.subject,
        "grade_level": profile.grade_level,
        "topic": profile.topic,
        "objectives": profile.objectives,
        "knowledge_scope": profile.knowledge_scope,
        "skills_and_competencies": profile.skills_and_competencies,
        "assessment_criteria": profile.assessment_criteria,
        "key_terms": profile.key_terms,
        "summary": profile.summary,
        "uncertainties": profile.uncertainties,
    }


def compact_teaching_context(profile: TeachingContextProfile) -> dict:
    return {
        "covered_content": profile.covered_content,
        "key_terms": profile.key_terms,
        "worked_examples": profile.worked_examples,
        "instructions_and_conventions": profile.instructions_and_conventions,
        "summary": profile.summary,
        "uncertainties": profile.uncertainties,
    }
