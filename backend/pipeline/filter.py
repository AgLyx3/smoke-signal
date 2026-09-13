"""Spend filter over the full Rho TransactionType enum (rho-sandbox-findings.md).

Output amounts are dollars, positive for spend, negative for offsets. Only `settled` rows count
toward baselines; `pending` rows are kept (settled=False) so they stay visible.
"""

from typing import Literal

import pandas as pd

RowKind = Literal["spend", "fee", "offset", "fee_offset", "excluded", "inflow", "unknown"]

SPEND = {"card_debit", "ach_debit", "wire_out", "international_wire_out", "check_payment"}
FEES = {"wire_fee", "international_wire_fee", "treasury_fee"}
OFFSETS = {"card_refund", "card_credit", "ach_return"}
FEE_OFFSETS = {"wire_fee_refund", "international_wire_fee_refund", "treasury_fee_refund"}
INFLOWS = {"ach_credit", "wire_in", "international_wire_in", "check_deposit"}
EXCLUDED_EXACT = {"credit_repayment", "credit_repayment_refund", "internal_transfer", "credit_cashback"}
EXCLUDED_PREFIXES = ("credit_repayment", "internal_transfer", "savings_", "treasury_", "rewards_", "adjustment_")

FEE_CATEGORY = "Fees & other"
KEPT_STATUSES = {"settled", "pending"}


def classify_type(transaction_type: object) -> RowKind:
    t = str(transaction_type or "").strip().lower()
    if t in SPEND:
        return "spend"
    if t in FEES:
        return "fee"
    if t in OFFSETS:
        return "offset"
    if t in FEE_OFFSETS:
        return "fee_offset"
    if t in INFLOWS:
        return "inflow"
    if t in EXCLUDED_EXACT or t.startswith(EXCLUDED_PREFIXES):
        return "excluded"
    return "unknown"


def month_index(d: pd.Timestamp | pd.Series) -> object:
    """Calendar month as an integer so month arithmetic is plain subtraction."""
    if isinstance(d, pd.Series):
        return d.dt.year * 12 + d.dt.month - 1
    return d.year * 12 + d.month - 1


def filter_spend(df: pd.DataFrame) -> pd.DataFrame:
    """Rows -> spend rows. Columns: id, date, month, amount, is_charge, settled, kind, is_fee,
    counterparty_name, transaction_type, user_id, user_full_name, card_id, card_name, memo."""
    if df is None or len(df) == 0:
        return _empty()
    out = df.copy()
    out["kind"] = out["transaction_type"].map(classify_type)
    out = out[out["kind"].isin(["spend", "fee", "offset", "fee_offset"])]
    status = out["status"].astype("string").str.strip().str.lower()
    out = out[status.isin(KEPT_STATUSES)]
    if len(out) == 0:
        return _empty()

    posted = pd.to_datetime(out["posted_at"], utc=True, errors="coerce", format="ISO8601")
    initiated = pd.to_datetime(out["initiated_at"], utc=True, errors="coerce", format="ISO8601")
    when = posted.fillna(initiated)
    out = out[when.notna()].copy()
    when = when[when.notna()]
    out["date"] = when.dt.tz_convert(None).dt.normalize()
    out["month"] = month_index(out["date"]).astype(int)

    minor = pd.to_numeric(out["amount_minor"], errors="coerce").fillna(0)
    magnitude = minor.abs() / 100.0
    is_offset = out["kind"].isin(["offset", "fee_offset"])
    out["amount"] = magnitude.where(~is_offset, -magnitude).astype(float)
    out["is_charge"] = ~is_offset
    out["is_fee"] = out["kind"].isin(["fee", "fee_offset"])
    out["settled"] = out["status"].astype("string").str.strip().str.lower().eq("settled")

    keep = [
        "id", "date", "month", "amount", "is_charge", "settled", "kind", "is_fee",
        "counterparty_name", "transaction_type", "user_id", "user_full_name", "card_id", "card_name", "memo",
    ]
    return out[keep].reset_index(drop=True)


def _empty() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "id": pd.Series(dtype=object),
            "date": pd.Series(dtype="datetime64[ns]"),
            "month": pd.Series(dtype=int),
            "amount": pd.Series(dtype=float),
            "is_charge": pd.Series(dtype=bool),
            "settled": pd.Series(dtype=bool),
            "kind": pd.Series(dtype=object),
            "is_fee": pd.Series(dtype=bool),
            "counterparty_name": pd.Series(dtype=object),
            "transaction_type": pd.Series(dtype=object),
            "user_id": pd.Series(dtype=object),
            "user_full_name": pd.Series(dtype=object),
            "card_id": pd.Series(dtype=object),
            "card_name": pd.Series(dtype=object),
            "memo": pd.Series(dtype=object),
        }
    )
