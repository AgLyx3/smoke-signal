"""Driver decomposition and confidence. Facts only; the narrator turns these into words."""

from models import DriverShare
from pipeline.series import VendorStats

WHO_SHARE = 0.60
HIGH_MIN_OBS = 6
HIGH_MAX_SIGMA = 0.15
MEDIUM_MIN_OBS = 3


def confidence_for(n_obs: int, sigma: float | None) -> str:
    if n_obs >= HIGH_MIN_OBS and (sigma is None or sigma <= HIGH_MAX_SIGMA):
        return "high"
    if n_obs >= MEDIUM_MIN_OBS:
        return "medium"
    return "low"


def _normalise(parts: dict[str, float]) -> list[DriverShare]:
    parts = {k: v for k, v in parts.items() if v > 0}
    total = sum(parts.values())
    if total <= 0:
        return []
    shares = [DriverShare(driver=k, share=round(v / total, 4)) for k, v in parts.items()]
    shares.sort(key=lambda d: -d.share)
    drift = round(1.0 - sum(d.share for d in shares), 4)
    if shares and drift:
        shares[0] = DriverShare(driver=shares[0].driver, share=round(shares[0].share + drift, 4))
    return shares


def price_volume_split(stats: VendorStats, eval_month: int, prior_months: list[int]) -> dict[str, float]:
    """Compare this month's (count, mean charge) with the prior months' averages.
    Usage vendors: a bigger invoice is more usage, so the mean-charge component is 'volume'."""
    count_now = stats.count(eval_month)
    total_now = stats.total(eval_month)
    if not prior_months or count_now == 0:
        return {"volume": 1.0}
    count_base = sum(stats.count(m) for m in prior_months) / len(prior_months)
    total_base = sum(stats.total(m) for m in prior_months) / len(prior_months)
    mean_base = total_base / count_base if count_base else total_now / count_now
    mean_now = total_now / count_now
    volume_part = abs((count_now - count_base) * mean_base)
    price_part = abs(count_now * (mean_now - mean_base))
    if stats.cost_type == "usage":
        return {"volume": volume_part + price_part}
    return {"volume": volume_part, "price": price_part}


def who_share(stats: VendorStats, eval_month: int, prior_months: list[int], increase: float) -> tuple[str | None, float]:
    """Cardholder carrying >= 60% of the increase, when the vendor has more than one cardholder."""
    if increase <= 0 or len(stats.cardholders) < 2:
        return None, 0.0
    best, best_delta = None, 0.0
    for user in stats.cardholders:
        now = stats.user_month.get((eval_month, user), 0.0)
        base = sum(stats.user_month.get((m, user), 0.0) for m in prior_months) / len(prior_months) if prior_months else 0.0
        delta = now - base
        if delta > best_delta:
            best, best_delta = user, delta
    share = min(1.0, best_delta / increase)
    return (best, share) if best and share >= WHO_SHARE else (None, 0.0)


def drivers_for(kind: str, stats: VendorStats, eval_month: int, prior_months: list[int], increase: float) -> tuple[list[DriverShare], list[str]]:
    """Returns (drivers summing to 1, cardholders for the month with the main contributor first)."""
    holders = sorted(
        {u for (m, u) in stats.user_month if m == eval_month},
        key=lambda u: -stats.user_month.get((eval_month, u), 0.0),
    )
    if kind in ("new_vendor", "spike"):
        return [DriverShare(driver="new", share=1.0)], holders
    if kind == "stopped":
        return [DriverShare(driver="missing", share=1.0)], []
    if kind == "renewal":
        return [], holders
    parts = price_volume_split(stats, eval_month, prior_months)
    who, w = who_share(stats, eval_month, prior_months, increase)
    if who:
        parts = {k: v * (1 - w) for k, v in _scaled(parts).items()}
        parts["who"] = w
        holders = [who] + [h for h in holders if h != who]
    return _normalise(parts), holders


def _scaled(parts: dict[str, float]) -> dict[str, float]:
    total = sum(v for v in parts.values() if v > 0)
    return {k: v / total for k, v in parts.items() if v > 0} if total > 0 else {}
