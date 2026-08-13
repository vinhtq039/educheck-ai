from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class AIUsageRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage: str
    model: str
    reasoning_effort: str
    attempt: int = Field(ge=1)
    input_tokens: int = Field(ge=0)
    cached_input_tokens: int = Field(ge=0)
    cache_write_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    reasoning_tokens: int = Field(ge=0)
    estimated_cost_usd: float = Field(ge=0)


class AIUsageSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    call_count: int = Field(ge=0)
    input_tokens: int = Field(ge=0)
    cached_input_tokens: int = Field(ge=0)
    cache_write_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    reasoning_tokens: int = Field(ge=0)
    estimated_cost_usd: float = Field(ge=0)
    records: list[AIUsageRecord]

