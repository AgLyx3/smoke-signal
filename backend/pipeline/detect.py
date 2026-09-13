"""Gate 1: is this vendor off its own normal? Emits candidates; route.py applies materiality."""

import math
from dataclasses import dataclass
from datetime import date, timedelta

from models import Baseline
from pipeline.baseline import (
    WINDOW_MONTHS,
    fixed_baseline,
    headcount_baseline,
    per_head_limit,
    prior_months,
    usage_baseline,
)
from pipeline.filter import FEE_CATEGORY
from pipeline.series import REGULAR_CADENCES, VendorStats

GROWTH_SIGMAS = 2.0
PRICE_CHANGE_PCT = 0.01
STOPPED_GRACE_DAYS = 5
RENEWAL_LOOKAHEAD_DAYS = 30
STOPPED_VISIBLE_CYCLES = 2
ANNUAL_DAYS = 365


@dataclass
class Candidate:
    stats: VendorStats
    kind: str
    actual: float
    expected: float
    baseline: Baseline
    n_obs: int
    sigma: float | None
    prior_months: list[int]
    display_impact: float | None = None  # renewal: annual amount shown, not a change


@dataclass(frozen=True)
class EvalContext:
    as_of: date
    eval_month: int
    complete: bool  # as_of is the last day of eval_month
    window_start: date
    headcount: dict[int, int]
    eval_headcount: int
    materiality: dict[str, float]  # cost_type -> $ threshold for the run


def _month_of(d: date) -> int:
    return d.year * 12 + d.month - 1


def _can_evaluate_month(stats: VendorStats, ctx: EvalContext) -> bool:
    """Complete months are evaluated for every vendor; a partial month only for monthly vendors
    whose charge for the month has already arrived."""
    if stats.total(ctx.eval_month) <= 0:
        return False
    return ctx.complete or (stats.cadence == "monthly" and stats.count(ctx.eval_month) >= 1)


def detect_vendor(stats: VendorStats, ctx: EvalContext) -> list[Candidate]:
    if stats.cost_type == "payroll" or stats.category == FEE_CATEGORY:
        return []
    if stats.cost_type == "annual" or stats.cadence == "annual":
        c = detect_renewal(stats, ctx)
        return [c] if c else []
    if not stats.recurring:
        c = detect_spike(stats, ctx)
        return [c] if c else []
    c = detect_new_vendor(stats, ctx)
    if c:
        return [c]
    out: list[Candidate] = []
    c = detect_stopped(stats, ctx)
    if c:
        out.append(c)
    if _can_evaluate_month(stats, ctx):
        if stats.cost_type == "usage":
            c = detect_growth_break(stats, ctx)
        elif stats.cost_type == "fixed":
            c = detect_price_change(stats, ctx)
        elif stats.cost_type == "headcount":
            c = detect_per_head(stats, ctx)
        else:
            c = None
        if c:
            out.append(c)
    return out


def detect_growth_break(stats: VendorStats, ctx: EvalContext) -> Candidate | None:
    b = usage_baseline(stats, ctx.eval_month)
    if b is None:
        return None
    actual = stats.total(ctx.eval_month)
    residual = math.log(actual) - math.log(b.expected)
    if residual < GROWTH_SIGMAS * b.sigma:
        return None
    baseline = Baseline(n_obs=b.n_obs, expected_monthly=b.expected, growth_pct=b.growth_pct, sigma=b.sigma)
    return Candidate(stats, "growth_break", actual, b.expected, baseline, b.n_obs, b.sigma, b.months)


def detect_price_change(stats: VendorStats, ctx: EvalContext) -> Candidate | None:
    b = fixed_baseline(stats, ctx.eval_month)
    if b is None or b.last_price <= 0:
        return None
    actual = stats.total(ctx.eval_month)
    if abs(actual - b.last_price) / b.last_price <= PRICE_CHANGE_PCT:
        return None
    baseline = Baseline(n_obs=b.n_obs, expected_monthly=b.last_price, last_price=b.last_price)
    return Candidate(stats, "price_change", actual, b.last_price, baseline, b.n_obs, None, b.months)


def detect_per_head(stats: VendorStats, ctx: EvalContext) -> Candidate | None:
    b = headcount_baseline(stats, ctx.eval_month, ctx.headcount, ctx.eval_headcount)
    if b is None:
        return None
    actual = stats.total(ctx.eval_month)
    if actual / b.headcount <= per_head_limit(b):
        return None
    baseline = Baseline(
        n_obs=b.n_obs, expected_monthly=b.expected, cost_per_head=b.cost_per_head,
        sigma=(b.std / b.cost_per_head) if b.cost_per_head else None, headcount_proxy=b.headcount,
    )
    return Candidate(stats, "per_head", actual, b.expected, baseline, b.n_obs, baseline.sigma, b.months)


def detect_new_vendor(stats: VendorStats, ctx: EvalContext) -> Candidate | None:
    """Second regular charge arrived this month and the vendor was unseen before the window."""
    if stats.n_charges < 2 or stats.cadence not in REGULAR_CADENCES:
        return None
    second = stats.charge_dates[1]
    if _month_of(second) != ctx.eval_month or stats.first_date < ctx.window_start:
        return None
    actual = stats.total(ctx.eval_month)
    if actual <= 0:
        return None
    baseline = Baseline(n_obs=1, expected_monthly=0.0)
    return Candidate(stats, "new_vendor", actual, 0.0, baseline, 1, None, [])


def detect_stopped(stats: VendorStats, ctx: EvalContext) -> Candidate | None:
    """Expected charge overdue by median gap + grace, as of `as_of`. Stays visible for
    STOPPED_VISIBLE_CYCLES billing cycles (so a monthly vendor that stopped mid-quarter still shows
    in the next month-end report), then goes quiet."""
    if stats.cadence not in REGULAR_CADENCES or stats.median_gap is None or stats.last_date is None:
        return None
    gap = timedelta(days=stats.median_gap)
    due = stats.last_date + gap + timedelta(days=STOPPED_GRACE_DAYS)
    if not (due < ctx.as_of <= due + STOPPED_VISIBLE_CYCLES * gap):
        return None
    months = [m for m in prior_months(ctx.eval_month + 1) if stats.total(m) > 0][-3:]
    if not months:
        return None
    expected = sum(stats.total(m) for m in months) / len(months)
    baseline = Baseline(n_obs=len(months), expected_monthly=expected)
    return Candidate(stats, "stopped", 0.0, expected, baseline, len(months), None, months)


def detect_renewal(stats: VendorStats, ctx: EvalContext) -> Candidate | None:
    """Annual vendor whose anniversary falls within RENEWAL_LOOKAHEAD_DAYS after as_of."""
    if stats.last_date is None:
        return None
    days = stats.median_gap if stats.cadence == "annual" and stats.median_gap else ANNUAL_DAYS
    anniversary = stats.last_date + timedelta(days=days)
    if not (ctx.as_of < anniversary <= ctx.as_of + timedelta(days=RENEWAL_LOOKAHEAD_DAYS)):
        return None
    amount = stats.total(_month_of(stats.last_date))
    baseline = Baseline(n_obs=stats.n_charges, expected_monthly=amount)
    return Candidate(stats, "renewal", amount, amount, baseline, stats.n_charges, None, [], display_impact=amount)


def detect_spike(stats: VendorStats, ctx: EvalContext) -> Candidate | None:
    """One-off vendor above materiality this month, no recurrence. Context only."""
    actual = stats.total(ctx.eval_month)
    if actual <= 0 or actual < ctx.materiality.get(stats.cost_type, float("inf")):
        return None
    baseline = Baseline(n_obs=0, expected_monthly=0.0)
    return Candidate(stats, "spike", actual, 0.0, baseline, 0, None, [])


def window_start_for(eval_month: int, first_month: int | None) -> date:
    start = eval_month - WINDOW_MONTHS
    if first_month is not None:
        start = max(start, first_month)
    return date(start // 12, start % 12 + 1, 1)
