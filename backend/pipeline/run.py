"""run_pipeline: filter -> resolve -> series -> classify -> baseline -> gates -> route -> Findings."""

import calendar
from collections.abc import Callable
from datetime import date

import pandas as pd

from models import (
    DEFAULT_CONFIG,
    Classification,
    Config,
    Finding,
    Findings,
    OpenIssue,
    Override,
    VendorFacts,
    VendorSummary,
)
from pipeline.baseline import usage_baseline
from pipeline.detect import Candidate, EvalContext, detect_vendor, window_start_for
from pipeline.explain import confidence_for, drivers_for
from pipeline.filter import filter_spend
from pipeline.resolve import EmptyTaxonomy, normalize_fallback, resolve_vendors
from pipeline.route import impact_for, materiality_table, route_candidate, slug
from pipeline.series import VendorStats, build_vendor_stats, headcount_by_month, month_label, total_spend_by_month

TRAILING_SPEND_MONTHS = 3

ClassifyHook = Callable[[list[VendorFacts]], dict[str, Classification]]


def _month_of(d: date) -> int:
    return d.year * 12 + d.month - 1


def _is_month_end(d: date) -> bool:
    return d.day == calendar.monthrange(d.year, d.month)[1]


def _vendor_facts(s: VendorStats) -> VendorFacts:
    return VendorFacts(
        vendor=s.vendor,
        monthly_amounts={month_label(m): round(v, 2) for m, v in sorted(s.monthly_total.items())},
        cadence=s.cadence,
        charge_count=s.n_charges,
        sample_descriptors=s.descriptors,
        sample_memos=s.memos,
        sample_card_names=s.card_names,
    )


def apply_classifications(
    stats: dict[str, VendorStats],
    overrides: list[Override],
    classify_unknown: ClassifyHook | None,
    taxonomy,
) -> None:
    """Priority: user override > taxonomy > hook result > default. Mutates stats in place."""
    unknown = [s for s in stats.values() if not s.known and s.recurring]
    if classify_unknown and unknown:
        results = classify_unknown([_vendor_facts(s) for s in unknown]) or {}
        for s in unknown:
            r = results.get(s.vendor)
            if r is not None:
                s.cost_type = r.cost_type
                s.category = r.category or s.category
                s.cost_type_source = "llm"
    normalize = getattr(taxonomy, "normalize", normalize_fallback)
    by_key = {slug(normalize(v)): v for v in stats}
    by_key.update({slug(v): v for v in stats})
    for o in overrides:
        key = by_key.get(slug(o.vendor)) or by_key.get(slug(normalize(o.vendor)))
        if key is not None:
            stats[key].cost_type = o.cost_type
            stats[key].cost_type_source = "user"


def trailing_monthly_spend(totals: dict[int, float], eval_month: int, n: int = TRAILING_SPEND_MONTHS) -> float:
    months = [m for m in sorted(totals) if m < eval_month][-n:]
    return sum(totals[m] for m in months) / len(months) if months else 0.0


def _finding(c: Candidate, ctx: EvalContext, config: Config, trailing: float, open_issues: list[OpenIssue]) -> Finding:
    s = c.stats
    impact = impact_for(c.kind, c.actual, c.expected, c.display_impact)
    routing = route_candidate(c.kind, s.vendor, s.cost_type, s.cost_type_source, impact, config, trailing, open_issues)
    drivers, holders = drivers_for(c.kind, s, ctx.eval_month, c.prior_months, c.actual - c.expected)
    return Finding(
        id=f"{slug(s.vendor)}:{c.kind}:{ctx.as_of.isoformat()}",
        vendor=s.vendor,
        category=s.category,
        cost_type=s.cost_type,
        cost_type_source=s.cost_type_source,
        kind=c.kind,
        route=routing.route,
        actual_monthly=round(c.actual, 2),
        impact_monthly=round(impact, 2),
        impact_pct_of_spend=round(impact / trailing, 6) if trailing > 0 else 0.0,
        baseline=c.baseline,
        drivers=drivers,
        confidence=confidence_for(c.n_obs, c.sigma),
        ask_cost_type=routing.ask_cost_type,
        escalation_of=routing.escalation_of,
        cardholders=holders,
        month=month_label(ctx.eval_month),
    )


def run_pipeline(
    df: pd.DataFrame,
    as_of: date,
    config: Config | None = None,
    overrides: list[Override] | None = None,
    open_issues: list[OpenIssue] | None = None,
    taxonomy=None,
    classify_unknown: ClassifyHook | None = None,
    stage: str = "history",
) -> Findings:
    config = config or DEFAULT_CONFIG
    overrides = overrides or []
    open_issues = open_issues or []
    taxonomy = taxonomy or EmptyTaxonomy()

    spend = resolve_vendors(filter_spend(df), taxonomy)
    spend = spend[spend["date"].dt.date <= as_of] if len(spend) else spend
    stats = build_vendor_stats(spend)
    apply_classifications(stats, overrides, classify_unknown, taxonomy)

    eval_month = _month_of(as_of)
    complete = _is_month_end(as_of)
    last_complete = eval_month if complete else eval_month - 1
    headcount = headcount_by_month(spend)
    eval_headcount = headcount.get(eval_month if complete else last_complete, 0)
    totals = total_spend_by_month(spend)
    trailing = trailing_monthly_spend(totals, eval_month)
    first_month = min(totals) if totals else None
    ctx = EvalContext(
        as_of=as_of,
        eval_month=eval_month,
        complete=complete,
        window_start=window_start_for(eval_month, first_month),
        headcount=headcount,
        eval_headcount=eval_headcount,
        materiality=materiality_table(config, trailing),
    )

    findings = [
        _finding(c, ctx, config, trailing, open_issues)
        for s in stats.values()
        for c in detect_vendor(s, ctx)
    ]
    findings = [f for f in findings if f.route != "ignore"]
    findings.sort(key=lambda f: (f.route != "alert", -abs(f.impact_monthly), f.vendor))

    vendors = [
        VendorSummary(
            vendor=s.vendor,
            category=s.category,
            cost_type=s.cost_type,
            cost_type_source=s.cost_type_source,
            cadence=s.cadence,
            monthly_spend=round(s.total(last_complete), 2),
            growth_pct=_growth_pct(s, eval_month),
        )
        for s in stats.values()
        if s.recurring
    ]
    vendors.sort(key=lambda v: (-v.monthly_spend, v.vendor))

    category_totals: dict[str, float] = {}
    for s in stats.values():
        category_totals[s.category] = round(category_totals.get(s.category, 0.0) + s.total(last_complete), 2)
    category_totals = {k: v for k, v in category_totals.items() if v != 0}

    return Findings(
        stage=stage,
        window_start=ctx.window_start,
        window_end=as_of,
        trailing_monthly_spend=round(trailing, 2),
        last_monthly_spend=round(totals[last_complete], 2) if last_complete in totals else None,
        prior_monthly_spend=round(totals[last_complete - 1], 2) if (last_complete - 1) in totals else None,
        headcount_proxy=eval_headcount,
        findings=findings,
        vendors=vendors,
        category_totals=category_totals,
    )


def _growth_pct(s: VendorStats, eval_month: int) -> float | None:
    if s.cost_type != "usage":
        return None
    b = usage_baseline(s, eval_month)
    return round(b.growth_pct, 4) if b else None
