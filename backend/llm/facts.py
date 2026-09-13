"""Facts block per finding, number formatting, and the grounding check.

Everything here is pure. Claude writes prose only from `build_facts`; `unsupported_numbers`
verifies that every dollar figure and percentage in the prose came from those facts."""

from __future__ import annotations

import re
from typing import Any, Iterable

from models import Finding, Findings, OpenIssue

# ---------------------------------------------------------------- formatting


def money(x: float) -> str:
    """Full figure: $26,500 / $1,875.50 / -$480."""
    sign = "-" if x < 0 else ""
    v = abs(x)
    body = f"{v:,.0f}" if abs(v - round(v)) < 0.005 else f"{v:,.2f}"
    return f"{sign}${body}"


def money_k(x: float) -> str:
    """Headline figure: $10.0K above 1,000, else the full figure."""
    sign = "-" if x < 0 else ""
    v = abs(x)
    if v >= 1000:
        return f"{sign}${v / 1000:.1f}K"
    return money(x)


def signed_money_k(x: float) -> str:
    return ("+" if x > 0 else "") + money_k(x)


def pct(x_percent: float) -> str:
    """x is already in percent units: 2.0 -> '2.0%'."""
    return f"{x_percent:.1f}%"


# ---------------------------------------------------------------- facts


def _pct_units(fraction: float | None) -> float | None:
    return None if fraction is None else round(fraction * 100, 2)


def finding_facts(f: Finding, open_vendors: set[str] = frozenset()) -> dict[str, Any]:
    b = f.baseline
    expected = b.expected_monthly
    above_expected_pct = None
    if expected and f.kind in ("growth_break", "price_change", "per_head", "new_vendor"):
        above_expected_pct = round((f.actual_monthly / expected - 1) * 100, 2)
    facts: dict[str, Any] = {
        "finding_id": f.id,
        "vendor": f.vendor,
        "kind": f.kind,
        "category": f.category,
        "cost_type": f.cost_type,
        "cost_type_source": f.cost_type_source,
        "route": f.route,
        "actual_monthly": round(f.actual_monthly, 2),
        "expected_monthly": round(expected, 2),
        "impact_monthly": round(f.impact_monthly, 2),
        "impact_pct_of_spend": _pct_units(f.impact_pct_of_spend),
        "trend_growth_pct_per_month": _pct_units(b.growth_pct),
        "above_expected_pct": above_expected_pct,
        "n_obs": b.n_obs,
        "sigma": b.sigma,
        "last_price": b.last_price,
        "cost_per_head": b.cost_per_head,
        "drivers": [{"driver": d.driver, "share_pct": _pct_units(d.share)} for d in f.drivers],
        "confidence": f.confidence,
        "ask_cost_type": f.ask_cost_type,
        "escalation_of": f.escalation_of,
        "ongoing_issue": bool(f.escalation_of) or f.vendor in open_vendors,
    }
    if any(d.driver == "who" for d in f.drivers) and f.cardholders:
        facts["cardholders"] = list(f.cardholders)
    if f.kind == "price_change" and b.last_price:
        facts["price_change_pct"] = round((f.actual_monthly / b.last_price - 1) * 100, 2)
    return facts


def window_facts(findings: Findings) -> dict[str, Any]:
    p = findings.period
    facts: dict[str, Any] = {
        "stage": findings.stage,
        # The reporting period is what the report is about; the baseline window is only the
        # range each vendor's trend was fitted on.
        "period_kind": p.kind if p else "month",
        "period_label": p.label if p else None,
        "period_start": p.start.isoformat() if p else None,
        "period_end": p.end.isoformat() if p else findings.window_end.isoformat(),
        "baseline_window_start": findings.window_start.isoformat(),
        "baseline_window_end": findings.window_end.isoformat(),
        "window_start": findings.window_start.isoformat(),
        "window_end": findings.window_end.isoformat(),
        "transaction_count": findings.transaction_count,
        "data_start": findings.data_start.isoformat() if findings.data_start else None,
        "trailing_monthly_spend": round(findings.trailing_monthly_spend, 2),
        "last_monthly_spend": findings.last_monthly_spend,
        "prior_monthly_spend": findings.prior_monthly_spend,
        "headcount_proxy_cardholders": findings.headcount_proxy,
        # The count the reports quote: recurring vendors big enough to matter, not every coffee shop.
        "vendor_count": findings.recurring_vendor_count if findings.recurring_vendor_count is not None else len(findings.vendors),
        "vendors_listed": len(findings.vendors),
        "finding_count": len(findings.findings),
        "category_totals": {k: round(v, 2) for k, v in findings.category_totals.items()},
    }
    # Month over month compares two full months, never the trailing mean against a month.
    if findings.prior_monthly_spend and findings.last_monthly_spend is not None:
        delta = findings.last_monthly_spend - findings.prior_monthly_spend
        facts["change_vs_prior_month"] = round(delta, 2)
        facts["change_vs_prior_month_pct"] = round(delta / findings.prior_monthly_spend * 100, 2)
    return facts


def open_issue_vendors(open_issues: Iterable[OpenIssue]) -> set[str]:
    return {o.vendor for o in open_issues}


def build_facts(findings: Findings, open_issues: Iterable[OpenIssue] = ()) -> dict[str, Any]:
    vendors = open_issue_vendors(open_issues)
    return {
        "window": window_facts(findings),
        "findings": [finding_facts(f, vendors) for f in findings.findings],
    }


# ---------------------------------------------------------------- grounding

# Thousands groups or a plain integer, optional decimals, optional K/M; must not run into a
# word character or another digit group, so "$16,500." parses as 16,500 and not 16.
_MONEY_RE = re.compile(r"[-+−–]?\$\s?((?:\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d+))?)\s?([KkMm])?(?![\w]|,\d)")
_PCT_RE = re.compile(r"(?<![\w.])(\d+(?:\.(\d+))?)\s?%")
_MULT = {"k": 1_000, "m": 1_000_000}


def extract_numbers(text: str) -> list[tuple[str, float, float, str]]:
    """(token, value, half-unit of the displayed precision, 'money'|'pct') for every figure."""
    out: list[tuple[str, float, float, str]] = []
    for m in _MONEY_RE.finditer(text):
        digits, frac, suffix = m.group(1), m.group(2), m.group(3)
        mult = _MULT.get((suffix or "").lower(), 1)
        value = float(digits.replace(",", "")) * mult
        half_unit = 0.5 * 10 ** (-(len(frac) if frac else 0)) * mult
        out.append((m.group(0).strip(), value, half_unit, "money"))
    for m in _PCT_RE.finditer(text):
        frac = m.group(2)
        value = float(m.group(1))
        half_unit = 0.5 * 10 ** (-(len(frac) if frac else 0))
        out.append((m.group(0), value, half_unit, "pct"))
    return out


def _numbers(v: Any) -> Iterable[float]:
    if isinstance(v, bool) or v is None:
        return
    if isinstance(v, (int, float)):
        yield float(v)
    elif isinstance(v, dict):
        for x in v.values():
            yield from _numbers(x)
    elif isinstance(v, (list, tuple)):
        for x in v:
            yield from _numbers(x)


_PCT_KEYS = ("pct", "share")
_MONEY_KEYS = (
    "actual_monthly",
    "expected_monthly",
    "impact_monthly",
    "last_price",
    "cost_per_head",
    "trailing_monthly_spend",
    "prior_monthly_spend",
    "change_vs_prior_month",
    "category_totals",
)


def allowed_numbers(*fact_blocks: dict[str, Any]) -> tuple[set[float], set[float]]:
    """(money values, percent values) a text built on these facts may quote."""
    money_set: set[float] = set()
    pct_set: set[float] = set()

    def walk(d: dict[str, Any]) -> None:
        for k, v in d.items():
            if isinstance(v, dict) and k != "category_totals":
                walk(v)
            elif isinstance(v, list):
                for item in v:
                    if isinstance(item, dict):
                        walk(item)
            elif any(p in k for p in _PCT_KEYS):
                pct_set.update(abs(x) for x in _numbers(v))
            elif k in _MONEY_KEYS:
                money_set.update(abs(x) for x in _numbers(v))

    for block in fact_blocks:
        walk(block)
    return money_set, pct_set


def _supported(value: float, half_unit: float, candidates: set[float]) -> bool:
    for c in candidates:
        if abs(value - c) <= max(half_unit, 0.01 * abs(c)) + 1e-9:
            return True
    return False


def unsupported_numbers(text: str, money_set: set[float], pct_set: set[float]) -> list[str]:
    """Tokens in `text` that match no allowed number within display rounding."""
    bad: list[str] = []
    for token, value, half_unit, kind in extract_numbers(text):
        pool = money_set if kind == "money" else pct_set
        if not _supported(value, half_unit, pool):
            bad.append(token)
    return bad
