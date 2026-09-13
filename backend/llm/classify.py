"""Classify vendors the taxonomy does not know: one batched Claude call, validated by Pydantic.

Never raises into the pipeline. Anything that goes wrong (no key, API error, budget, bad
payload) degrades to a low-confidence default per vendor and a logged warning."""

from __future__ import annotations

import json
import logging
from typing import Any, get_args

from pydantic import BaseModel, ValidationError

from llm.client import LLMClient, create_message, get_client, tool_input
from models import Classification, Confidence, CostType, VendorFacts

log = logging.getLogger("cost_signals.llm")

COST_TYPES: tuple[str, ...] = get_args(CostType)
CONFIDENCES: tuple[str, ...] = get_args(Confidence)

CATEGORIES: tuple[str, ...] = (
    "AI & inference",
    "Cloud & infra",
    "Data & tooling",
    "Software",
    "People & payroll",
    "Sales & marketing",
    "Office & travel",
    "Professional services",
    "Fees & other",
)

COST_TYPE_DEFINITIONS = {
    "usage": "usage-scaling: billed on consumption (API calls, compute, storage); expected to grow along its own trend",
    "fixed": "fixed: same plan, same price each period; only a price change moves it",
    "headcount": "headcount-scaling: seat or per-employee pricing; grows with the number of people",
    "annual": "annual / one-off: yearly contracts, deposits, single purchases; a renewal, not a monthly cost",
    "payroll": "payroll: salaries, payroll taxes, benefits providers; context only, never an alert",
}

FALLBACK = Classification(cost_type="fixed", category="Software", confidence="low")

TOOL_NAME = "classify_vendors"

CLASSIFY_TOOL: dict[str, Any] = {
    "name": TOOL_NAME,
    "description": "Record a cost type, spend category and confidence for every vendor in the batch.",
    # No `strict`: grammar-constrained decoding made latency scale with batch size (4 vendors
    # 3.9 s, 10 vendors 20 s; the same 10 without strict 4.4 s). Pydantic validates every entry
    # and bad ones fall back, so strictness at the API buys nothing here.
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["classifications"],
        "properties": {
            "classifications": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["vendor", "cost_type", "category", "confidence"],
                    "properties": {
                        "vendor": {"type": "string", "description": "Exactly as given in the input"},
                        "cost_type": {"type": "string", "enum": list(COST_TYPES)},
                        "category": {"type": "string", "enum": list(CATEGORIES)},
                        "confidence": {"type": "string", "enum": list(CONFIDENCES)},
                    },
                },
            }
        },
    },
}

SYSTEM_PROMPT = (
    "You classify vendors for a startup's spend-monitoring system. For each vendor you are given "
    "the normalised name, its net spend by calendar month, the charge cadence and count, and "
    "sample card descriptors, memos and card names. Assign exactly one cost type and one category.\n\n"
    "Cost types:\n"
    + "\n".join(f"- {k}: {v.split(': ', 1)[1]}" for k, v in COST_TYPE_DEFINITIONS.items())
    + "\n\nCategories (use these strings exactly): "
    + ", ".join(CATEGORIES)
    + ".\n\n"
    "Confidence: high when the vendor is well known and the amounts fit the type; medium when the "
    "name is known but the billing pattern is ambiguous; low when you are guessing from the "
    "descriptor alone. Prefer low confidence over a confident guess. Vendors you do not recognise "
    "get the most plausible type from the amounts and cadence, with low confidence. Return one "
    f"entry per vendor, in the same order, by calling {TOOL_NAME} once."
)


class _Batch(BaseModel):
    classifications: list[dict[str, Any]]


def _user_message(facts: list[VendorFacts]) -> str:
    rows = [
        {
            "vendor": f.vendor,
            "monthly_amounts": {m: round(a, 2) for m, a in sorted(f.monthly_amounts.items())},
            "cadence": f.cadence,
            "charge_count": f.charge_count,
            "sample_descriptors": f.sample_descriptors[:5],
            "sample_memos": f.sample_memos[:5],
            "sample_card_names": f.sample_card_names[:3],
        }
        for f in facts
    ]
    return "Classify these vendors:\n" + json.dumps(rows, indent=1)


def _key(vendor: str) -> str:
    return " ".join(vendor.lower().split())


def parse_classifications(payload: dict[str, Any] | None, facts: list[VendorFacts]) -> dict[str, Classification]:
    """Validate a tool payload per vendor; unknown, missing or invalid entries fall back."""
    out: dict[str, Classification] = {}
    by_key: dict[str, dict[str, Any]] = {}
    try:
        batch = _Batch.model_validate(payload or {})
        for item in batch.classifications:
            if isinstance(item, dict) and isinstance(item.get("vendor"), str):
                by_key.setdefault(_key(item["vendor"]), item)
    except ValidationError as e:
        log.warning("classify: payload shape invalid, falling back for all %d vendors: %s", len(facts), e)

    for f in facts:
        item = by_key.get(_key(f.vendor))
        if item is None:
            log.warning("classify: no entry for %r, using fallback", f.vendor)
            out[f.vendor] = FALLBACK
            continue
        try:
            c = Classification.model_validate({k: item.get(k) for k in ("cost_type", "category", "confidence")})
            if c.category not in CATEGORIES:
                raise ValueError(f"category {c.category!r} not in list")
            out[f.vendor] = c
        except (ValidationError, ValueError) as e:
            log.warning("classify: invalid entry for %r (%s), using fallback", f.vendor, e)
            out[f.vendor] = FALLBACK
    return out


# Per-process cache so reruns (an override, a threshold change) make no further calls.
_CACHE: dict[str, Classification] = {}


def clear_cache() -> None:
    _CACHE.clear()


def classify_unknown(facts: list[VendorFacts], client: LLMClient | None = None) -> dict[str, Classification]:
    """Classify the uncached vendors in one call. Never raises. If the call itself fails (no key,
    API error, budget) the uncached vendors are left OUT of the result, so the pipeline keeps them
    at their default cost type and still asks the user; only a bad entry inside a successful
    response falls back to FALLBACK."""
    todo = [f for f in facts if f.vendor not in _CACHE]
    if todo:
        try:
            client = client or get_client()
            message = create_message(
                client,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": _user_message(todo)}],
                tools=[CLASSIFY_TOOL],
                tool_choice={"type": "tool", "name": TOOL_NAME, "disable_parallel_tool_use": True},
            )
        except Exception as e:  # noqa: BLE001 - the pipeline must keep running without Claude
            log.warning("classify: call failed (%s: %s); %d vendors stay unclassified", type(e).__name__, e, len(todo))
        else:
            _CACHE.update(parse_classifications(tool_input(message, TOOL_NAME), todo))
    return {f.vendor: _CACHE[f.vendor] for f in facts if f.vendor in _CACHE}
