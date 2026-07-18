from __future__ import annotations

import pytest
from pydantic import ValidationError

from schemas.analysis import AnalysisIssue


def test_rejects_confidence_outside_range() -> None:
    with pytest.raises(ValidationError):
        AnalysisIssue(
            issue_id="1",
            category="vietnamese_spelling",
            severity="warning",
            original_text="Sai",
            explanation="Lỗi",
            confidence=1.1,
        )


def test_rejects_unknown_category() -> None:
    with pytest.raises(ValidationError):
        AnalysisIssue(
            issue_id="1",
            category="unknown",
            severity="warning",
            original_text="Sai",
            explanation="Lỗi",
            confidence=0.8,
        )

