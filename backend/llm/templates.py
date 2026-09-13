"""Deterministic narration. The offline fallback and the safety net for the live demo.

Every number is formatted from the same facts Claude sees, so template text always passes the
grounding check."""

from __future__ import annotations

from typing import Any

from llm.facts import money, money_k, pct, signed_money_k
from models import AlertText, ReportItemText

SOURCE_PHRASE = {
    "taxonomy": "from our vendor taxonomy",
    "llm": "inferred by Claude from the charges",
    "user": "confirmed by you",
    "default": "not yet classified, treated as fixed until you confirm",
}

UNKNOWN = {
    "growth_break": "We can't see per-model or per-key usage without a provider key.",
    "new_vendor": "We don't know the plan or what it replaces.",
    "price_change": "We can't tell a price rise from a seat or tier change without the invoice.",
    "stopped": "We can't tell a cancellation from a late invoice until the next cycle.",
    "per_head": "We only see charges, not seat counts.",
    "renewal": "We don't know whether the terms changed.",
    "spike": "We can't see what the charge bought.",
}

DRIVER_PHRASE = {
    "price": "price",
    "volume": "volume",
    "new": "a new recurring charge",
    "missing": "a missing charge",
    "who": "who is spending",
}


def _cost_type(f: dict[str, Any]) -> str:
    return f"Cost type {f['cost_type']} ({SOURCE_PHRASE.get(f['cost_type_source'], 'inferred')})."


def _drivers(f: dict[str, Any]) -> str:
    parts = [f"{DRIVER_PHRASE.get(d['driver'], d['driver'])} {pct(d['share_pct'])}" for d in f["drivers"]]
    return "Driver split: " + ", ".join(parts) + "." if parts else ""


def _confidence(f: dict[str, Any]) -> str:
    n = f.get("n_obs")
    return f"Confidence {f['confidence']}" + (f" ({n} monthly observations)." if n else ".")


def _who(f: dict[str, Any]) -> str:
    ch = f.get("cardholders") or []
    return f" Cardholders: {', '.join(ch)}." if ch else ""


def _share(f: dict[str, Any]) -> str:
    return pct(abs(f["impact_pct_of_spend"] or 0.0))


def headline(f: dict[str, Any]) -> str:
    v, kind = f["vendor"], f["kind"]
    lead = f"{signed_money_k(f['impact_monthly'])}/mo · {_share(f)} of monthly spend"
    tail = {
        "growth_break": f"{v} is running well above its trend"
        if f["impact_monthly"] > 0
        else f"{v} is running below its trend",
        "new_vendor": f"{v} is now a recurring charge",
        "price_change": f"{v} changed its price" + (" upward" if f["impact_monthly"] > 0 else " downward"),
        "stopped": f"{v}'s expected charge did not arrive",
        "per_head": f"{v} is growing faster than headcount",
        "renewal": f"{v}'s annual renewal is coming up",
        "spike": f"{v} had a one-off charge",
    }[kind]
    if kind == "renewal":
        lead = f"{money_k(f.get('last_price') or f['expected_monthly'])} annual"
    return f"{lead} — {tail}"


def what_moved(f: dict[str, Any]) -> str:
    v, kind = f["vendor"], f["kind"]
    actual, expected, impact = f["actual_monthly"], f["expected_monthly"], f["impact_monthly"]
    if kind == "growth_break":
        growth = f.get("trend_growth_pct_per_month")
        trend = f" (about {pct(growth)} month over month)" if growth is not None else ""
        above = f.get("above_expected_pct")
        rel = f" ({pct(abs(above))})" if above is not None else ""
        return (
            f"{v} billed {money(actual)} this month against {money(expected)} expected from its trend{trend}. "
            f"That is {money(abs(impact))}{rel} {'above' if impact > 0 else 'below'} trend, "
            f"{_share(f)} of monthly spend."
        )
    if kind == "new_vendor":
        prior = f" The previous charge was {money(expected)}." if expected else ""
        return (
            f"{v} charged {money(actual)} this month, its second regular charge, which confirms it as recurring.{prior} "
            f"It adds {money(abs(impact))} a month, {_share(f)} of monthly spend."
        )
    if kind == "price_change":
        last = f.get("last_price") or expected
        chg = f.get("price_change_pct")
        rel = f" ({pct(abs(chg))} {'up' if chg > 0 else 'down'})" if chg is not None else ""
        return (
            f"{v} moved from {money(last)} to {money(actual)}{rel} on what looks like the same plan. "
            f"That is {money(abs(impact))} a month, {_share(f)} of monthly spend."
        )
    if kind == "stopped":
        return (
            f"{v}'s regular charge of {money(expected)} did not arrive on schedule; this month shows {money(actual)}. "
            f"That is {money(abs(impact))} a month less, {_share(f)} of monthly spend."
        )
    if kind == "per_head":
        cph = f.get("cost_per_head")
        head = f" Cost per head is now {money(cph)}." if cph else ""
        return (
            f"{v} billed {money(actual)} against {money(expected)} expected at the current headcount.{head} "
            f"That is {money(abs(impact))} a month above, {_share(f)} of monthly spend."
        )
    if kind == "renewal":
        amt = f.get("last_price") or expected
        return f"{v}'s annual contract renews soon; last year's charge was {money(amt)}. It does not change monthly spend."
    return f"{v} had a one-off charge of {money(actual)}, {money(abs(impact))} above its usual {money(expected)}. No recurrence yet."


def why(f: dict[str, Any]) -> str:
    parts = [_drivers(f), _confidence(f), _cost_type(f), UNKNOWN.get(f["kind"], "")]
    return " ".join(p for p in parts if p) + _who(f)


def alert_text(f: dict[str, Any]) -> AlertText:
    return AlertText(finding_id=f["finding_id"], headline=headline(f), what_moved=what_moved(f), why=why(f))


def report_item(f: dict[str, Any]) -> ReportItemText:
    v, kind = f["vendor"], f["kind"]
    actual, expected, impact = f["actual_monthly"], f["expected_monthly"], f["impact_monthly"]
    ongoing = " Already flagged; still open." if f.get("ongoing_issue") else ""
    conf = f"confidence {f['confidence']}"
    if kind == "growth_break":
        text = (
            f"{v} billed {money(actual)} against {money(expected)} expected from its trend, "
            f"{money(abs(impact))} {'above' if impact > 0 else 'below'} ({_share(f)} of monthly spend); {conf}."
        )
    elif kind == "new_vendor":
        text = f"{v} is now recurring at {money(actual)} a month ({_share(f)} of monthly spend); {conf}."
    elif kind == "price_change":
        last = f.get("last_price") or expected
        text = (
            f"{v} moved from {money(last)} to {money(actual)}, {money(abs(impact))} a month "
            f"{'more' if impact > 0 else 'less'} ({_share(f)} of monthly spend); {conf}."
        )
    elif kind == "stopped":
        text = f"{v}'s regular {money(expected)} charge did not arrive, {money(abs(impact))} a month less; {conf}."
    elif kind == "per_head":
        text = (
            f"{v} billed {money(actual)} against {money(expected)} expected at the current headcount, "
            f"{money(abs(impact))} a month above; {conf}."
        )
    elif kind == "renewal":
        amt = f.get("last_price") or expected
        text = f"{v}'s annual renewal of {money(amt)} is coming up; no change to monthly spend."
    else:
        text = f"{v} had a one-off charge of {money(actual)} against its usual {money(expected)}; no recurrence yet."
    return ReportItemText(finding_id=f["finding_id"], text=text + ongoing)


def report_intro(w: dict[str, Any], n_attention: int, n_worth: int) -> str:
    trailing = money(w["trailing_monthly_spend"])
    if w.get("last_monthly_spend") is not None and "change_vs_prior_month" in w:
        delta = w["change_vs_prior_month"]
        direction = "up" if delta > 0 else "down"
        month = (
            f"The last full month closed at {money(w['last_monthly_spend'])}, {direction} {money(abs(delta))} "
            f"({pct(abs(w['change_vs_prior_month_pct']))}) from {money(w['prior_monthly_spend'])} the month before; "
            f"the trailing three-month average is {trailing}. "
        )
    elif w.get("last_monthly_spend") is not None:
        month = f"The last full month closed at {money(w['last_monthly_spend'])}; the trailing three-month average is {trailing}. "
    else:
        month = f"Trailing monthly spend is {trailing}. "
    return (
        f"Spend report for {w['window_start']} to {w['window_end']}. {month}"
        f"{w['headcount_proxy_cardholders']} distinct cardholders in the window, our headcount proxy, across "
        f"{w['vendor_count']} vendors. {n_attention} items need attention and {n_worth} are worth knowing."
    )
