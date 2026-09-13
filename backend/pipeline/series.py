"""Per-vendor series: monthly totals, charge counts, cadence, cardholders. Settled rows only."""

from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd

REGULAR_CADENCES = ("semi-monthly", "monthly", "annual")


@dataclass
class VendorStats:
    vendor: str
    category: str
    cost_type: str
    cost_type_source: str
    known: bool
    monthly_total: dict[int, float] = field(default_factory=dict)  # month_index -> settled net $
    monthly_count: dict[int, int] = field(default_factory=dict)  # month_index -> settled charges
    charge_dates: list[date] = field(default_factory=list)  # settled charges, sorted
    pending_total: dict[int, float] = field(default_factory=dict)
    median_gap: float | None = None
    cadence: str = "irregular"
    recurring: bool = False
    user_month: dict[tuple[int, str], float] = field(default_factory=dict)  # (month, cardholder) -> $
    cardholders: list[str] = field(default_factory=list)
    descriptors: list[str] = field(default_factory=list)
    memos: list[str] = field(default_factory=list)
    card_names: list[str] = field(default_factory=list)

    @property
    def n_charges(self) -> int:
        return len(self.charge_dates)

    @property
    def first_date(self) -> date | None:
        return self.charge_dates[0] if self.charge_dates else None

    @property
    def last_date(self) -> date | None:
        return self.charge_dates[-1] if self.charge_dates else None

    def total(self, month: int) -> float:
        return float(self.monthly_total.get(month, 0.0))

    def count(self, month: int) -> int:
        return int(self.monthly_count.get(month, 0))

    def months_active(self) -> list[int]:
        return sorted(m for m, v in self.monthly_total.items() if v > 0)


def cadence_from_gap(median_gap: float | None) -> str:
    if median_gap is None:
        return "irregular"
    if 14 <= median_gap <= 16:
        return "semi-monthly"
    if 26 <= median_gap <= 35:
        return "monthly"
    if 330 <= median_gap <= 400:
        return "annual"
    return "irregular"


def _samples(values: pd.Series, n: int = 5) -> list[str]:
    seen: list[str] = []
    for v in values:
        if isinstance(v, str) and v.strip() and v not in seen:
            seen.append(v)
        if len(seen) >= n:
            break
    return seen


def build_vendor_stats(df: pd.DataFrame) -> dict[str, VendorStats]:
    stats: dict[str, VendorStats] = {}
    if len(df) == 0:
        return stats
    holder = df["user_full_name"].where(df["user_full_name"].notna(), df["user_id"])
    df = df.assign(_holder=holder)
    for vendor, g in df.groupby("vendor", sort=True):
        first = g.iloc[0]
        s = VendorStats(
            vendor=vendor,
            category=first["category"],
            cost_type=first["cost_type"],
            cost_type_source=first["cost_type_source"],
            known=bool(first["known"]),
        )
        settled = g[g["settled"]]
        pending = g[~g["settled"]]
        s.monthly_total = {int(m): float(v) for m, v in settled.groupby("month")["amount"].sum().items()}
        s.pending_total = {int(m): float(v) for m, v in pending.groupby("month")["amount"].sum().items()}
        charges = settled[settled["is_charge"]]
        s.monthly_count = {int(m): int(c) for m, c in charges.groupby("month").size().items()}
        s.charge_dates = sorted(d.date() for d in charges["date"])
        if len(s.charge_dates) >= 2:
            gaps = np.diff(np.array([d.toordinal() for d in s.charge_dates]))
            s.median_gap = float(np.median(gaps))
        s.cadence = cadence_from_gap(s.median_gap)
        # Regular interval, or present in >= 3 months (high-frequency vendors billed many times a month).
        s.recurring = (s.n_charges >= 2 and s.cadence in REGULAR_CADENCES) or len(s.months_active()) >= 3
        with_holder = charges[charges["_holder"].notna()]
        s.user_month = {
            (int(m), str(u)): float(v)
            for (m, u), v in with_holder.groupby(["month", "_holder"])["amount"].sum().items()
        }
        s.cardholders = sorted({str(u) for u in with_holder["_holder"]})
        s.descriptors = _samples(g["counterparty_name"])
        s.memos = _samples(g["memo"])
        s.card_names = _samples(g["card_name"])
        stats[vendor] = s
    return stats


def headcount_by_month(df: pd.DataFrame) -> dict[int, int]:
    """Headcount proxy: distinct user_ids with a settled card_debit in the month (DESIGN A3)."""
    if len(df) == 0:
        return {}
    card = df[df["settled"] & df["transaction_type"].eq("card_debit") & df["user_id"].notna()]
    return {int(m): int(n) for m, n in card.groupby("month")["user_id"].nunique().items()}


def total_spend_by_month(df: pd.DataFrame) -> dict[int, float]:
    """All settled net spend per month, payroll and fees included."""
    if len(df) == 0:
        return {}
    settled = df[df["settled"]]
    return {int(m): float(v) for m, v in settled.groupby("month")["amount"].sum().items()}


def month_label(month: int) -> str:
    return f"{month // 12:04d}-{month % 12 + 1:02d}"
