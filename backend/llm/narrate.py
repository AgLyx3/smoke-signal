"""Turn `Findings` into alert and report prose. Claude narrates from a facts block; a
grounding check rejects any number the facts do not support; templates fill the gaps."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Iterable, Literal

from pydantic import BaseModel, ValidationError

from llm import templates
from llm.client import LLMClient, create_message, get_client, tool_input
from llm.facts import allowed_numbers, build_facts, unsupported_numbers
from models import AlertText, Findings, NarrateResponse, OpenIssue, ReportItemText, ReportText

log = logging.getLogger("cost_signals.llm")

Mode = Literal["alerts", "report"]
Source = Literal["claude", "template", "mixed"]

STYLE_RULES = (
    "You write short spend notices for a startup's finance channel, from a facts block computed "
    "by a deterministic detector. Rules:\n"
    "- Detect and route, never recommend. No 'consider', 'switch', 'cancel', 'renegotiate', "
    "'should'. Describe what changed and what is known.\n"
    "- Every dollar figure and every percentage must be copied from the facts, rounded at most "
    "to one decimal. Do not compute new figures, do not annualise, do not invent totals.\n"
    "- Write dollars as $26,500 or $10.0K and percentages with the % sign.\n"
    "- Cost types: cost_type_source 'taxonomy' comes from our vendor taxonomy (a rule, say 'from "
    "our vendor taxonomy'); 'llm' is inferred from the charges (say 'inferred'); 'default' means "
    "not yet classified (say so); only 'user' is confirmed.\n"
    "- Plain English, present tense, no exclamation marks, no emoji, no markdown.\n"
    "- Mention the confidence label and, in each 'why', one sentence on what the system does "
    "not know (for example, it cannot see per-model usage without a provider key, or it "
    "cannot tell a cancellation from a late invoice).\n"
    "- A finding with ongoing_issue true was already flagged; say it is still open, do not "
    "announce it as new."
)

ALERTS_INSTRUCTIONS = (
    "For each finding in the facts, write one alert card with three parts. headline: one line "
    "that leads with the consequence, in the form '+$10.0K/mo · 2.0% of monthly spend — Vendor "
    "is running well above its trend' (impact, share of spend, then what happened). what_moved: "
    "two or three sentences with the actual, expected and impact figures. why: the driver "
    "split with shares, the confidence label with the observation count, the cost type and "
    "whether it is inferred, and one sentence on what the system does not know. If "
    "cardholders are listed, name them. Return one entry per finding_id."
)

REPORT_INSTRUCTIONS = (
    "Write a monthly spend report. intro: one paragraph covering the window, trailing monthly "
    "spend versus the prior month when prior_monthly_spend is present (otherwise do not "
    "mention a prior month), and the headcount proxy stated as distinct cardholders. items: "
    "one or two sentences per finding_id covering every finding in the facts, with the "
    "figures that matter for that kind: actual against expected and the impact, or the price "
    "move, or the missing charge, or the upcoming renewal. Decreases and missing charges are "
    "included. Return one entry per finding_id."
)

ALERTS_TOOL_NAME = "write_alerts"
REPORT_TOOL_NAME = "write_report"

_ITEM = {
    "type": "object",
    "additionalProperties": False,
    "required": ["finding_id", "text"],
    "properties": {"finding_id": {"type": "string"}, "text": {"type": "string"}},
}

ALERTS_TOOL: dict[str, Any] = {
    "name": ALERTS_TOOL_NAME,
    "description": "Record one alert card per finding.",
    "strict": True,
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["alerts"],
        "properties": {
            "alerts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["finding_id", "headline", "what_moved", "why"],
                    "properties": {
                        "finding_id": {"type": "string"},
                        "headline": {"type": "string"},
                        "what_moved": {"type": "string"},
                        "why": {"type": "string"},
                    },
                },
            }
        },
    },
}

REPORT_TOOL: dict[str, Any] = {
    "name": REPORT_TOOL_NAME,
    "description": "Record the report intro and one text per finding.",
    "strict": True,
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["intro", "items"],
        "properties": {"intro": {"type": "string"}, "items": {"type": "array", "items": _ITEM}},
    },
}


class _AlertsPayload(BaseModel):
    alerts: list[AlertText]


class _ReportPayload(BaseModel):
    intro: str
    items: list[ReportItemText]


@dataclass
class NarrateResult:
    response: NarrateResponse
    source: Source
    templated: list[str] = field(default_factory=list)
    calls: int = 0


# ---------------------------------------------------------------- selection


def alert_findings(facts: dict[str, Any]) -> list[dict[str, Any]]:
    return [f for f in facts["findings"] if f["route"] == "alert"]


def report_findings(facts: dict[str, Any]) -> list[dict[str, Any]]:
    return [f for f in facts["findings"] if f["route"] != "ignore"]


def needs_attention(f: dict[str, Any]) -> bool:
    return f["route"] == "alert" or bool(f.get("escalation_of")) or bool(f.get("ongoing_issue"))


def _by_impact(items: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(items, key=lambda f: abs(f["impact_monthly"]), reverse=True)


def assemble_report(
    facts: dict[str, Any], intro: str, texts: dict[str, str]
) -> ReportText:
    """Group and sort deterministically; Claude only supplies the sentences."""
    items = report_findings(facts)
    attention = _by_impact(f for f in items if needs_attention(f))
    worth = [f for f in items if not needs_attention(f)]
    grouped: dict[str, list[ReportItemText]] = {}
    for f in _by_impact(worth):
        grouped.setdefault(f["category"], []).append(ReportItemText(finding_id=f["finding_id"], text=texts[f["finding_id"]]))
    return ReportText(
        intro=intro,
        needs_attention=[ReportItemText(finding_id=f["finding_id"], text=texts[f["finding_id"]]) for f in attention],
        worth_knowing=grouped,
    )


# ---------------------------------------------------------------- templates


def template_response(findings: Findings, mode: Mode, open_issues: Iterable[OpenIssue] = ()) -> NarrateResponse:
    facts = build_facts(findings, open_issues)
    if mode == "alerts":
        return NarrateResponse(alerts=[templates.alert_text(f) for f in alert_findings(facts)])
    items = report_findings(facts)
    texts = {f["finding_id"]: templates.report_item(f).text for f in items}
    n_att = sum(1 for f in items if needs_attention(f))
    intro = templates.report_intro(facts["window"], n_att, len(items) - n_att)
    return NarrateResponse(report=assemble_report(facts, intro, texts))


# ---------------------------------------------------------------- claude


def _facts_message(
    facts: dict[str, Any], instructions: str, violations: list[str] | None = None, missing: list[str] | None = None
) -> str:
    text = instructions + "\n\nFacts:\n" + json.dumps(facts, indent=1)
    if violations:
        text += (
            "\n\nA previous draft used figures that are not in the facts: "
            + ", ".join(violations)
            + ". Rewrite every text so that each dollar figure and percentage is copied from the facts."
        )
    if missing:
        text += "\n\nA previous draft left out these ids; include every one: " + ", ".join(missing) + "."
    return text


def _retry_args(bad: dict[str, list[str]], expected_ids: list[str], good_ids: set[str]) -> tuple[list[str], list[str]]:
    violations = sorted({t for v in bad.values() for t in v})
    missing = [i for i in expected_ids if i not in good_ids and i not in bad]
    return violations, missing


def _call(client: LLMClient, tool: dict[str, Any], user_text: str) -> dict[str, Any] | None:
    message = create_message(
        client,
        system=STYLE_RULES,
        messages=[{"role": "user", "content": user_text}],
        tools=[tool],
        tool_choice={"type": "tool", "name": tool["name"], "disable_parallel_tool_use": True},
    )
    if getattr(message, "stop_reason", None) not in ("tool_use", "end_turn"):
        log.warning("narrate: unexpected stop_reason %r", getattr(message, "stop_reason", None))
    return tool_input(message, tool["name"])


def _check_alert(a: AlertText, money_set: set[float], pct_set: set[float]) -> list[str]:
    bad: list[str] = []
    for part in (a.headline, a.what_moved, a.why):
        bad += unsupported_numbers(part, money_set, pct_set)
    return bad


def _narrate_alerts(facts: dict[str, Any], client: LLMClient) -> NarrateResult:
    items = alert_findings(facts)
    if not items:
        return NarrateResult(NarrateResponse(alerts=[]), "template", calls=0)
    sub = {"window": facts["window"], "findings": items}
    by_id = {f["finding_id"]: f for f in items}

    def attempt(violations: list[str] | None, missing: list[str] | None = None) -> tuple[dict[str, AlertText], dict[str, list[str]]]:
        payload = _call(client, ALERTS_TOOL, _facts_message(sub, ALERTS_INSTRUCTIONS, violations, missing))
        got: dict[str, AlertText] = {}
        bad: dict[str, list[str]] = {}
        try:
            parsed = _AlertsPayload.model_validate(payload or {})
        except ValidationError as e:
            log.warning("narrate: alerts payload invalid: %s", e)
            return got, bad
        for a in parsed.alerts:
            f = by_id.get(a.finding_id)
            if f is None:
                continue
            violations_here = _check_alert(a, *allowed_numbers(f, {"window": facts["window"]}))
            if violations_here:
                bad[a.finding_id] = violations_here
            else:
                got[a.finding_id] = a
        return got, bad

    calls = 1
    good, bad = attempt(None)
    if bad or len(good) < len(items):
        log.warning("narrate: alerts grounding violations %s, regenerating once", bad)
        calls += 1
        good2, bad2 = attempt(*_retry_args(bad, list(by_id), set(good)))
        good = {**good2, **good}
        bad = {k: v for k, v in bad2.items() if k not in good}

    templated: list[str] = []
    alerts: list[AlertText] = []
    for f in items:
        fid = f["finding_id"]
        if fid in good:
            alerts.append(good[fid])
        else:
            log.warning("narrate: templated alert for %s (%s)", fid, bad.get(fid, "missing"))
            templated.append(fid)
            alerts.append(templates.alert_text(f))
    source: Source = "template" if len(templated) == len(items) else ("mixed" if templated else "claude")
    return NarrateResult(NarrateResponse(alerts=alerts), source, templated, calls)


def _narrate_report(facts: dict[str, Any], client: LLMClient) -> NarrateResult:
    items = report_findings(facts)
    by_id = {f["finding_id"]: f for f in items}
    sub = {"window": facts["window"], "findings": items}
    window_money, window_pct = allowed_numbers({"window": facts["window"]})
    all_money, all_pct = allowed_numbers(sub)

    def attempt(violations: list[str] | None, missing: list[str] | None = None) -> tuple[str | None, dict[str, str], dict[str, list[str]]]:
        payload = _call(client, REPORT_TOOL, _facts_message(sub, REPORT_INSTRUCTIONS, violations, missing))
        got: dict[str, str] = {}
        bad: dict[str, list[str]] = {}
        try:
            parsed = _ReportPayload.model_validate(payload or {})
        except ValidationError as e:
            log.warning("narrate: report payload invalid: %s", e)
            return None, got, bad
        intro_bad = unsupported_numbers(parsed.intro, all_money | window_money, all_pct | window_pct)
        intro = None if intro_bad else parsed.intro
        if intro_bad:
            bad["intro"] = intro_bad
        for it in parsed.items:
            f = by_id.get(it.finding_id)
            if f is None:
                continue
            v = unsupported_numbers(it.text, *allowed_numbers(f, {"window": facts["window"]}))
            if v:
                bad[it.finding_id] = v
            else:
                got[it.finding_id] = it.text
        return intro, got, bad

    calls = 1
    intro, good, bad = attempt(None)
    if bad or intro is None or len(good) < len(items):
        log.warning("narrate: report grounding violations %s, regenerating once", bad)
        calls += 1
        intro2, good2, bad2 = attempt(*_retry_args(bad, list(by_id), set(good)))
        intro = intro if intro is not None else intro2
        good = {**good2, **good}
        bad = {k: v for k, v in bad2.items() if k not in good}

    templated: list[str] = []
    n_att = sum(1 for f in items if needs_attention(f))
    if intro is None:
        templated.append("intro")
        intro = templates.report_intro(facts["window"], n_att, len(items) - n_att)
    texts: dict[str, str] = {}
    for f in items:
        fid = f["finding_id"]
        if fid in good:
            texts[fid] = good[fid]
        else:
            log.warning("narrate: templated report item for %s (%s)", fid, bad.get(fid, "missing"))
            templated.append(fid)
            texts[fid] = templates.report_item(f).text
    total = len(items) + 1
    source: Source = "template" if len(templated) == total else ("mixed" if templated else "claude")
    return NarrateResult(NarrateResponse(report=assemble_report(facts, intro, texts)), source, templated, calls)


def narrate_result(
    findings: Findings, mode: Mode, client: LLMClient | None = None, open_issues: Iterable[OpenIssue] = ()
) -> NarrateResult:
    """Claude narration with grounding and per-item template fallback.

    Raises `MissingAPIKeyError`, `BudgetExceededError` and `anthropic.APIError` to the caller,
    which decides whether to serve `template_response` instead."""
    facts = build_facts(findings, open_issues)
    client = client or get_client()
    if mode == "alerts":
        return _narrate_alerts(facts, client)
    return _narrate_report(facts, client)


def narrate(
    findings: Findings, mode: Mode, client: LLMClient | None = None, open_issues: Iterable[OpenIssue] = ()
) -> NarrateResponse:
    return narrate_result(findings, mode, client, open_issues).response
