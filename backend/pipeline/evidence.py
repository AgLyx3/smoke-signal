"""Evidence pack for a thread question about one finding: the facts the card was built on, the
vendor's monthly series, and the individual charges behind the evaluated and prior month.
Everything a clarifying answer may quote comes from here and nowhere else."""

from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd

from llm.facts import finding_facts
from models import Config, Finding, Findings
from pipeline.filter import filter_spend
from pipeline.resolve import resolve_vendors
from pipeline.route import threshold_for
from pipeline.series import month_label

MAX_CHARGES = 40
SERIES_MONTHS = 8


def prepare_spend(df: pd.DataFrame, as_of: date, taxonomy=None) -> pd.DataFrame:
    """The same filtered, vendor-resolved frame the pipeline detects on."""
    spend = resolve_vendors(filter_spend(df), taxonomy)
    return spend[spend["date"].dt.date <= as_of] if len(spend) else spend


def _month_of(d: date) -> int:
    return d.year * 12 + d.month - 1


def _charges(rows: pd.DataFrame) -> list[dict[str, Any]]:
    holder = rows["user_full_name"].where(rows["user_full_name"].notna(), rows["user_id"])
    out = []
    for (_, r), h in zip(rows.iterrows(), holder):
        out.append(
            {
                "date": r["date"].date().isoformat(),
                "amount": round(float(r["amount"]), 2),
                "cardholder": None if pd.isna(h) else str(h),
                "card_name": None if pd.isna(r.get("card_name")) else str(r.get("card_name")),
                "memo": None if pd.isna(r.get("memo")) else str(r.get("memo")),
                "descriptor": str(r.get("counterparty_name") or ""),
                "type": str(r.get("transaction_type") or ""),
                "settled": bool(r["settled"]),
            }
        )
    out.sort(key=lambda c: (-abs(c["amount"]), c["date"]))
    return out[:MAX_CHARGES]


def build_evidence(spend: pd.DataFrame, findings: Findings, finding: Finding, config: Config, as_of: date) -> dict[str, Any]:
    eval_month = _month_of(as_of)
    prior_month = eval_month - 1
    rows = spend[spend["vendor"] == finding.vendor] if len(spend) else spend
    settled = rows[rows["settled"]] if len(rows) else rows

    series: list[dict[str, Any]] = []
    if len(settled):
        by_month = settled.groupby("month")["amount"].agg(["sum", "count"])
        for m in range(eval_month - SERIES_MONTHS + 1, eval_month + 1):
            if m in by_month.index:
                series.append({"month": month_label(m), "total": round(float(by_month.loc[m, "sum"]), 2), "charges": int(by_month.loc[m, "count"])})
            else:
                series.append({"month": month_label(m), "total": 0.0, "charges": 0})

    eval_rows = rows[rows["month"] == eval_month] if len(rows) else rows
    prior_rows = rows[rows["month"] == prior_month] if len(rows) else rows

    holders: dict[str, float] = {}
    if len(eval_rows):
        h = eval_rows["user_full_name"].where(eval_rows["user_full_name"].notna(), eval_rows["user_id"])
        for name, amt in eval_rows.assign(_h=h).dropna(subset=["_h"]).groupby("_h")["amount"].sum().items():
            holders[str(name)] = round(float(amt), 2)

    t = threshold_for(config, finding.cost_type)
    trailing = findings.trailing_monthly_spend
    return {
        "finding": finding_facts(finding),
        "reporting": {
            "as_of": as_of.isoformat(),
            "evaluated_month": month_label(eval_month),
            "period_label": findings.period.label if findings.period else None,
            "baseline_window": f"{findings.window_start.isoformat()} to {findings.window_end.isoformat()}",
        },
        "thresholds": {
            "alert_pct_of_monthly_spend": round(t.alert_pct * 100, 2),
            "alert_dollars_per_month": round(t.alert_pct * trailing, 2),
            "report_floor_pct_of_monthly_spend": round(config.report_floor_pct * 100, 3),
            "report_floor_dollars_per_month": round(config.report_floor_pct * trailing, 2),
            "trailing_monthly_spend": round(trailing, 2),
            "alerts_enabled_for_cost_type": t.alerts,
        },
        "vendor_monthly_series": series,
        "charges_evaluated_month": _charges(eval_rows) if len(eval_rows) else [],
        "charges_prior_month": _charges(prior_rows) if len(prior_rows) else [],
        "cardholder_totals_evaluated_month": dict(sorted(holders.items(), key=lambda kv: -kv[1])),
        "not_visible": [
            "per-model or per-API-key usage (needs a provider key)",
            "invoice line items",
            "the vendor's plan or seat count",
            "anything outside this vendor's Rho transactions",
        ],
    }
