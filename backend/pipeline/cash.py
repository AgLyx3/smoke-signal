"""Cash position from Rho's own accounts: runway from total cash and net burn, and what the
operating balance allows. This is the part only the bank can compute without asking the
founder for anything: Rho holds the operating account, the treasury account, and the flows."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from models import CashPosition, Finding
from pipeline.filter import INFLOWS

WEEKS_PER_MONTH = 52 / 12
MIN_NET_BURN = 1_000.0  # a company with no net burn has no runway arithmetic to do


def load_accounts(data_dir: Path | str, stage: str) -> dict[str, Any] | None:
    path = Path(data_dir) / "accounts.json"
    if not path.exists():
        return None
    with open(path) as f:
        payload = json.load(f)
    snap = (payload.get("snapshots") or {}).get(stage)
    return snap


def _balance(accounts: list[dict[str, Any]], account_type: str) -> float:
    total = 0.0
    for a in accounts:
        if a.get("account_type") == account_type:
            bal = a.get("balance") or {}
            amt = bal.get("amount") if isinstance(bal, dict) else bal
            total += float(amt or 0) / 100.0
    return total


def _month_of(d: date) -> int:
    return d.year * 12 + d.month - 1


def monthly_inflows(df: pd.DataFrame, eval_month: int, months: int = 3) -> float:
    """Average settled inflow per month over the `months` complete months before the evaluated
    month. Inflows are customer payments and other credits, not internal transfers."""
    if len(df) == 0 or "transaction_type" not in df.columns:
        return 0.0
    types = df["transaction_type"].astype(str).str.lower()
    rows = df[types.isin(INFLOWS) & (df["status"].astype(str).str.lower() == "settled")]
    if len(rows) == 0:
        return 0.0
    when = pd.to_datetime(rows["initiated_at"], utc=True, errors="coerce")
    month_idx = when.dt.year * 12 + when.dt.month - 1
    window = rows[(month_idx >= eval_month - months) & (month_idx < eval_month)]
    if len(window) == 0:
        return 0.0
    amounts = window["amount_minor"].astype(float).abs() / 100.0
    return float(amounts.sum() / months)


def runway_weeks_delta(total_cash: float, net_burn: float, impact_monthly: float) -> float | None:
    """Weeks of runway lost (positive) or gained (negative) if a monthly change persists."""
    if net_burn < MIN_NET_BURN or total_cash <= 0:
        return None
    new_burn = net_burn + impact_monthly
    if new_burn < MIN_NET_BURN:
        return None
    before = total_cash / net_burn
    after = total_cash / new_burn
    return round((before - after) * WEEKS_PER_MONTH, 2)


def cash_position(
    df: pd.DataFrame,
    as_of: date,
    trailing_monthly_spend: float,
    accounts: dict[str, Any] | None,
    buffer_months: float,
    treasury_apy: float,
) -> CashPosition | None:
    if not accounts:
        return None
    acct_list = accounts.get("accounts") or []
    operating = _balance(acct_list, "checking")
    treasury = _balance(acct_list, "investment")
    inflows = monthly_inflows(df, _month_of(as_of))
    net_burn = max(trailing_monthly_spend - inflows, 0.0)
    total = operating + treasury
    runway_months = round(total / net_burn, 1) if net_burn >= MIN_NET_BURN else None
    operating_months = round(operating / net_burn, 1) if net_burn >= MIN_NET_BURN else None
    recommended = buffer_months * net_burn
    sweep = round(max(operating - recommended, 0.0), 2)
    shortfall = round(max(recommended - operating, 0.0), 2)
    return CashPosition(
        as_of=date.fromisoformat(accounts["as_of"]) if accounts.get("as_of") else as_of,
        operating_balance=round(operating, 2),
        treasury_balance=round(treasury, 2),
        total_cash=round(total, 2),
        monthly_inflows=round(inflows, 2),
        net_burn_monthly=round(net_burn, 2),
        runway_months=runway_months,
        operating_months_of_burn=operating_months,
        buffer_months=buffer_months,
        recommended_operating=round(recommended, 2),
        sweep_to_treasury=sweep,
        shortfall_from_treasury=shortfall,
        treasury_apy=treasury_apy,
        treasury_upside_monthly=round(sweep * treasury_apy / 12, 2),
    )


def attach_runway(findings: list[Finding], cash: CashPosition | None) -> None:
    if cash is None or cash.runway_months is None:
        return
    for f in findings:
        if f.kind in ("renewal", "spike"):
            continue  # one-offs do not change the run rate
        f.runway_weeks_delta = runway_weeks_delta(cash.total_cash, cash.net_burn_monthly, f.impact_monthly)
