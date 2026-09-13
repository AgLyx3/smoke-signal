"""Baselines per cost type, fitted only on months strictly before the evaluated month."""

from dataclasses import dataclass, field

import numpy as np

from pipeline.series import VendorStats

WINDOW_MONTHS = 6
SIGMA_FLOOR = 0.08  # a perfectly smooth history must not make every deviation "unusual"
MIN_USAGE_OBS = 3
MIN_FIXED_IDENTICAL = 2
MIN_HEADCOUNT_OBS = 3
PER_HEAD_MIN_OBS_FOR_SIGMA = 4
PER_HEAD_FALLBACK_PCT = 0.15
PER_HEAD_FLOOR_PCT = 0.05


def prior_months(eval_month: int, window: int = WINDOW_MONTHS) -> range:
    return range(eval_month - window, eval_month)


@dataclass
class UsageBaseline:
    n_obs: int
    expected: float
    growth_pct: float
    sigma: float
    months: list[int] = field(default_factory=list)


@dataclass
class FixedBaseline:
    n_obs: int
    last_price: float
    months: list[int] = field(default_factory=list)


@dataclass
class HeadcountBaseline:
    n_obs: int
    cost_per_head: float  # trailing mean
    std: float
    expected: float  # mean cost per head x headcount for the evaluated month
    headcount: int
    history: list[float] = field(default_factory=list)
    months: list[int] = field(default_factory=list)


def observed_months(stats: VendorStats, eval_month: int, window: int = WINDOW_MONTHS) -> list[int]:
    return [m for m in prior_months(eval_month, window) if stats.total(m) > 0]


def usage_baseline(stats: VendorStats, eval_month: int, window: int = WINDOW_MONTHS) -> UsageBaseline | None:
    """Log-linear trend over the trailing window; expected for eval_month is the extrapolation."""
    months = observed_months(stats, eval_month, window)
    if len(months) < MIN_USAGE_OBS:
        return None
    t = np.array(months, dtype=float)
    y = np.log(np.array([stats.total(m) for m in months]))
    slope, intercept = np.polyfit(t, y, 1)
    residuals = y - (intercept + slope * t)
    sigma = max(float(np.sqrt(np.mean(residuals**2))), SIGMA_FLOOR)
    expected = float(np.exp(intercept + slope * eval_month))
    return UsageBaseline(len(months), expected, float(np.exp(slope) - 1), sigma, months)


def fixed_baseline(stats: VendorStats, eval_month: int, window: int = WINDOW_MONTHS) -> FixedBaseline | None:
    """Last price = the most recent prior monthly total, accepted only when the window holds
    >= 2 identical prices (so the vendor plausibly is fixed-price)."""
    months = observed_months(stats, eval_month, window)
    if not months:
        return None
    prices = [round(stats.total(m), 2) for m in months]
    if max(prices.count(p) for p in prices) < MIN_FIXED_IDENTICAL:
        return None
    return FixedBaseline(len(months), prices[-1], months)


def headcount_baseline(
    stats: VendorStats, eval_month: int, headcount: dict[int, int], eval_headcount: int, window: int = WINDOW_MONTHS
) -> HeadcountBaseline | None:
    months = [m for m in observed_months(stats, eval_month, window) if headcount.get(m, 0) > 0]
    if len(months) < MIN_HEADCOUNT_OBS or eval_headcount <= 0:
        return None
    history = [stats.total(m) / headcount[m] for m in months]
    mean = float(np.mean(history))
    std = float(np.std(history))
    return HeadcountBaseline(len(months), mean, std, mean * eval_headcount, eval_headcount, history, months)


def per_head_limit(b: HeadcountBaseline) -> float:
    """Own mean + 2 sigma with >= 4 observations, else +15% of the trailing mean; never below +5%."""
    if b.n_obs >= PER_HEAD_MIN_OBS_FOR_SIGMA:
        return b.cost_per_head + max(2 * b.std, PER_HEAD_FLOOR_PCT * b.cost_per_head)
    return b.cost_per_head * (1 + PER_HEAD_FALLBACK_PCT)
