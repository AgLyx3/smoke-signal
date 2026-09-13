"""Gate 2 (materiality), routing, and dedupe against open issues."""

import re
from dataclasses import dataclass

from models import DEFAULT_CONFIG, Config, OpenIssue, TypeThreshold

ESCALATION_GROWTH = 0.5
NEVER_ALERT_KINDS = {"renewal", "spike", "stopped"}
CONFIRMED_SOURCES = {"taxonomy", "user"}


@dataclass(frozen=True)
class Routing:
    route: str
    impact: float
    threshold: float
    escalation_of: str | None
    ask_cost_type: bool


def threshold_for(config: Config, cost_type: str) -> TypeThreshold:
    return config.thresholds.get(cost_type) or DEFAULT_CONFIG.thresholds.get(cost_type) or TypeThreshold(alert_pct=0.01)


def materiality_table(config: Config, trailing_monthly_spend: float) -> dict[str, float]:
    return {ct: threshold_for(config, ct).alert_pct * trailing_monthly_spend for ct in DEFAULT_CONFIG.thresholds}


def impact_for(kind: str, actual: float, expected: float, display_impact: float | None) -> float:
    if kind == "renewal":
        return display_impact if display_impact is not None else actual
    if kind == "stopped":
        return -expected
    return actual - expected


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-") or "vendor"


def _same_vendor(a: str, b: str) -> bool:
    return slug(a) == slug(b)


def route_candidate(
    kind: str,
    vendor: str,
    cost_type: str,
    cost_type_source: str,
    impact: float,
    config: Config,
    trailing_monthly_spend: float,
    open_issues: list[OpenIssue],
) -> Routing:
    t = threshold_for(config, cost_type)
    threshold = t.alert_pct * trailing_monthly_spend
    material = trailing_monthly_spend > 0 and abs(impact) >= threshold
    route = "alert" if (material and t.alerts and kind not in NEVER_ALERT_KINDS) else "report"

    escalation_of = None
    if route == "alert":
        prior = [i for i in open_issues if i.kind == kind and _same_vendor(i.vendor, vendor)]
        if prior:
            worst = max(prior, key=lambda i: abs(i.impact_monthly))
            grew_by = abs(impact) - abs(worst.impact_monthly)
            escalated = abs(impact) >= (1 + ESCALATION_GROWTH) * abs(worst.impact_monthly) and grew_by >= threshold
            if escalated:
                escalation_of = worst.id
            else:
                route = "report"

    ask = route == "alert" and cost_type_source not in CONFIRMED_SOURCES
    return Routing(route, impact, threshold, escalation_of, ask)
