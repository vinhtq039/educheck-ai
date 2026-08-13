from __future__ import annotations

from typing import Any

from schemas.usage import AIUsageRecord, AIUsageSummary


# Standard API prices verified from the OpenAI model catalog on 2026-07-18.
# Values are USD per one million tokens: input, cached input, output.
MODEL_PRICING_USD_PER_MILLION = {
    "gpt-5-nano": (0.05, 0.005, 0.4),
    "gpt-5-mini": (0.25, 0.025, 2.0),
    "gpt-4o-mini": (0.15, 0.075, 0.6),
    "gpt-5.6-sol": (5.0, 0.5, 30.0),
    "gpt-5.6-terra": (2.5, 0.25, 15.0),
    "gpt-5.6-luna": (1.0, 0.1, 6.0),
    "gpt-5.5": (5.0, 0.5, 30.0),
}


def _value(source: Any, name: str, default: Any = None) -> Any:
    if source is None:
        return default
    if isinstance(source, dict):
        return source.get(name, default)
    return getattr(source, name, default)


def _integer(source: Any, name: str) -> int:
    value = _value(source, name, 0)
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _pricing_for_model(model: str) -> tuple[float, float, float] | None:
    normalized = model.casefold()
    return next(
        (
            prices
            for model_name, prices in MODEL_PRICING_USD_PER_MILLION.items()
            if normalized == model_name or normalized.startswith(f"{model_name}-")
        ),
        None,
    )


def usage_record_from_response(
    response: Any,
    *,
    stage: str,
    requested_model: str,
    reasoning_effort: str,
    attempt: int,
) -> AIUsageRecord:
    usage = _value(response, "usage")
    input_details = _value(usage, "input_tokens_details")
    output_details = _value(usage, "output_tokens_details")
    input_tokens = _integer(usage, "input_tokens")
    cached_tokens = _integer(input_details, "cached_tokens")
    cache_write_tokens = max(
        _integer(usage, "cache_write_tokens"),
        _integer(input_details, "cache_write_tokens"),
    )
    output_tokens = _integer(usage, "output_tokens")
    reasoning_tokens = _integer(output_details, "reasoning_tokens")
    actual_model = str(_value(response, "model", requested_model) or requested_model)

    estimated_cost = 0.0
    prices = _pricing_for_model(actual_model)
    if prices is not None:
        input_price, cached_price, output_price = prices
        ordinary_input = max(
            0,
            input_tokens - cached_tokens - cache_write_tokens,
        )
        estimated_cost = (
            ordinary_input * input_price
            + cached_tokens * cached_price
            + cache_write_tokens * input_price * 1.25
            + output_tokens * output_price
        ) / 1_000_000

    return AIUsageRecord(
        stage=stage,
        model=actual_model,
        reasoning_effort=reasoning_effort,
        attempt=attempt,
        input_tokens=input_tokens,
        cached_input_tokens=cached_tokens,
        cache_write_tokens=cache_write_tokens,
        output_tokens=output_tokens,
        reasoning_tokens=reasoning_tokens,
        estimated_cost_usd=round(estimated_cost, 8),
    )


def summarize_usage(records: list[AIUsageRecord]) -> AIUsageSummary:
    return AIUsageSummary(
        call_count=len(records),
        input_tokens=sum(item.input_tokens for item in records),
        cached_input_tokens=sum(item.cached_input_tokens for item in records),
        cache_write_tokens=sum(item.cache_write_tokens for item in records),
        output_tokens=sum(item.output_tokens for item in records),
        reasoning_tokens=sum(item.reasoning_tokens for item in records),
        estimated_cost_usd=round(
            sum(item.estimated_cost_usd for item in records),
            8,
        ),
        records=records,
    )
