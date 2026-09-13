"""Load a demo stage from the committed Rho-style JSON envelopes."""

import json
from datetime import date
from pathlib import Path

import pandas as pd

from models import Stage

# Stage -> (files in order, as_of). Later files extend earlier ones.
STAGES: dict[str, tuple[tuple[str, ...], date]] = {
    "history": (("history.json",), date(2026, 8, 31)),
    "inject-1": (("history.json", "inject-1.json"), date(2026, 9, 5)),
    "inject-2": (("history.json", "inject-1.json", "inject-2.json"), date(2026, 9, 30)),
}

# Every field the pipeline reads. Absent ones are added as None, like the sandbox omits `memo`.
COLUMNS = [
    "id",
    "amount_minor",
    "currency",
    "counterparty_name",
    "transaction_type",
    "status",
    "initiated_at",
    "posted_at",
    "card_id",
    "card_name",
    "user_id",
    "user_full_name",
    "memo",
    "account_id",
    "account_type",
]


def _flatten(tx: dict) -> dict:
    row = dict(tx)
    amount = row.pop("amount", None)
    if isinstance(amount, dict):
        row["amount_minor"] = amount.get("amount")
        row["currency"] = amount.get("currency")
    else:
        row["amount_minor"] = amount
        row.setdefault("currency", None)
    return row


def frame_from_transactions(transactions: list[dict]) -> pd.DataFrame:
    """Rho rows -> flat DataFrame with every expected column present (None when absent)."""
    rows = [_flatten(t) for t in transactions]
    df = pd.DataFrame(rows)
    for col in COLUMNS:
        if col not in df.columns:
            df[col] = None
    if len(df) and df["id"].notna().any():
        df = df.drop_duplicates(subset="id", keep="last")
    return df.reset_index(drop=True)


def read_envelope(path: Path) -> list[dict]:
    with open(path) as f:
        payload = json.load(f)
    if isinstance(payload, dict):
        return list(payload.get("transactions") or [])
    return list(payload or [])


def load_stage(stage: Stage, data_dir: Path | str) -> tuple[pd.DataFrame, date]:
    """Raise FileNotFoundError when a stage's file is missing so the route can 404."""
    if stage not in STAGES:
        raise KeyError(f"unknown stage {stage!r}")
    files, as_of = STAGES[stage]
    data_dir = Path(data_dir)
    transactions: list[dict] = []
    for name in files:
        path = data_dir / name
        if not path.exists():
            raise FileNotFoundError(f"data file {name} not found for stage {stage!r} in {data_dir}")
        transactions.extend(read_envelope(path))
    return frame_from_transactions(transactions), as_of
