"""Answer a clarifying question in the thread under one finding, from its evidence pack only.
Same discipline as the cards: detect and route, never recommend; every number must come from
the evidence; say plainly what the data cannot show."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Iterable, Literal

from llm.client import LLMClient, create_message, get_client, tool_input
from llm.facts import money, unsupported_numbers
from models import AskTurn

log = logging.getLogger("cost_signals.llm")

TOOL_NAME = "answer_question"
ANSWER_TOOL: dict[str, Any] = {
    "name": TOOL_NAME,
    "description": "Reply in the thread with one short, grounded answer.",
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["answer"],
        "properties": {"answer": {"type": "string", "description": "Plain text, one short paragraph, optionally followed by a short list of charges"}},
    },
}

SYSTEM = (
    "You answer follow-up questions in a Slack thread under one spend alert, for a startup's "
    "founder. You are given an evidence pack: the finding's facts, the vendor's monthly series, "
    "the individual charges in the evaluated and prior month, cardholder totals, and the "
    "thresholds in force. Rules:\n"
    "- Answer only from the evidence pack. Every dollar figure and percentage you write must "
    "appear in it (rounded at most to one decimal); never compute new totals or annualise.\n"
    "- If the pack cannot answer the question, say exactly what is not visible (the pack lists "
    "it) and stop. Do not guess.\n"
    "- Detect and route, never recommend: no 'consider', 'switch', 'cancel', 'renegotiate', "
    "'should'. Describe what the data shows.\n"
    "- Questions about other vendors, budgets, or general spend are out of scope: say so in one "
    "sentence and point to the @Rho assistant for general questions.\n"
    "- Name cardholders when asked who; list charges as 'date · $amount · cardholder · memo' "
    "when asked to show them, at most eight lines.\n"
    "- Plain English, present tense, no exclamation marks, no emoji, no markdown headings. "
    "One short paragraph; a short list only when asked for charges or people."
)

Source = Literal["claude", "template"]


@dataclass
class AskResult:
    answer: str
    source: Source


def _numeric_leaves(v: Any, out: set[float]) -> None:
    if isinstance(v, bool):
        return
    if isinstance(v, (int, float)):
        out.add(abs(float(v)))
    elif isinstance(v, dict):
        for x in v.values():
            _numeric_leaves(x, out)
    elif isinstance(v, list):
        for x in v:
            _numeric_leaves(x, out)


def allowed_from_evidence(evidence: dict[str, Any]) -> tuple[set[float], set[float]]:
    """Every number in the pack may be quoted as money or as a percent."""
    nums: set[float] = set()
    _numeric_leaves(evidence, nums)
    return nums, nums


def _user_text(evidence: dict[str, Any], question: str, thread: Iterable[AskTurn], violations: list[str] | None = None) -> str:
    turns = "\n".join(f"{t.role}: {t.text}" for t in thread)
    text = "Evidence pack:\n" + json.dumps(evidence, indent=1)
    if turns:
        text += "\n\nThread so far:\n" + turns
    text += "\n\nQuestion: " + question
    if violations:
        text += (
            "\n\nA previous draft used figures that are not in the evidence pack: "
            + ", ".join(violations)
            + ". Rewrite the answer so that every dollar figure and percentage is copied from the pack."
        )
    return text


def template_answer(evidence: dict[str, Any], question: str) -> str:
    """Deterministic fallback: restate the finding and show the evidence that exists."""
    f = evidence["finding"]
    parts = [
        f"Here is what I can show for {f['vendor']}: {money(f['actual_monthly'])} this period against "
        f"{money(f['expected_monthly'])} expected, an impact of {money(f['impact_monthly'])} a month "
        f"({f['impact_pct_of_spend']}% of monthly spend), confidence {f['confidence']}."
    ]
    holders = evidence.get("cardholder_totals_evaluated_month") or {}
    if holders:
        top = list(holders.items())[:5]
        parts.append("Cardholders this period: " + "; ".join(f"{n} {money(a)}" for n, a in top) + ".")
    charges = evidence.get("charges_evaluated_month") or []
    if charges:
        lines = [f"{c['date']} · {money(c['amount'])} · {c['cardholder'] or 'system'} · {c['memo'] or c['descriptor']}" for c in charges[:8]]
        parts.append("Largest charges: " + " | ".join(lines) + ".")
    parts.append("Not visible from Rho data: " + "; ".join(evidence.get("not_visible", [])[:2]) + ".")
    return " ".join(parts)


def answer_question(evidence: dict[str, Any], question: str, thread: Iterable[AskTurn] = (), client: LLMClient | None = None) -> AskResult:
    """One call, grounding check, one regeneration, then the template. Never raises."""
    thread = list(thread)
    money_set, pct_set = allowed_from_evidence(evidence)
    try:
        client = client or get_client()
        violations: list[str] = []
        for _ in range(2):
            message = create_message(
                client,
                system=SYSTEM,
                messages=[{"role": "user", "content": _user_text(evidence, question, thread, violations)}],
                tools=[ANSWER_TOOL],
                tool_choice={"type": "tool", "name": TOOL_NAME, "disable_parallel_tool_use": True},
            )
            payload = tool_input(message, TOOL_NAME) or {}
            answer = str(payload.get("answer") or "").strip()
            if not answer:
                violations = ["(empty answer)"]
                continue
            bad = unsupported_numbers(answer, money_set, pct_set)
            if not bad:
                return AskResult(answer=answer, source="claude")
            log.warning("ask: ungrounded figures %s; regenerating", bad)
            violations = bad
    except Exception as e:  # noqa: BLE001 - the thread must always get an answer
        log.warning("ask: %s: %s; serving the template", type(e).__name__, e)
    return AskResult(answer=template_answer(evidence, question), source="template")
