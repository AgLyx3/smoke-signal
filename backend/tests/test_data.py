"""Guards the committed synthetic dataset: reproducibility, planted scenarios, Rho schema sanity.

    cd backend && uv run pytest tests/test_data.py
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import get_args

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import models  # noqa: E402
import taxonomy  # noqa: E402
from data import generate as gen  # noqa: E402

DATA_DIR = BACKEND / "data"
STAGES = ("history", "inject-1", "inject-2")

TX_TYPES = {
    "card_credit", "card_debit", "card_refund", "credit_repayment", "credit_repayment_refund", "credit_cashback",
    "ach_credit", "ach_debit", "ach_return", "wire_in", "wire_out", "wire_fee", "international_wire_in",
    "international_wire_out", "check_deposit", "check_payment", "internal_transfer", "savings_deposit",
    "savings_withdrawal", "savings_interest", "treasury_deposit", "treasury_withdrawal", "treasury_fee",
    "treasury_interest", "treasury_maturity", "treasury_sale", "treasury_market_value_adjustment",
    "rewards_accrual", "rewards_cashback_redemption", "adjustment_credit", "adjustment_debit",
    "international_wire_fee", "international_wire_fee_refund",
}
STATUSES = {"pending", "settled", "failed", "awaiting_approval"}
DEBIT_TYPES = {"card_debit", "ach_debit", "wire_out", "wire_fee", "check_payment", "internal_transfer_out"}
CREDIT_TYPES = {"card_refund", "ach_credit", "wire_in", "rewards_accrual", "credit_repayment"}
SPEND_TYPES = {"card_debit", "ach_debit", "wire_out", "international_wire_out", "check_payment", "wire_fee"}
FIELDS = {
    "id", "money_movement_id", "account_id", "account_name", "account_type", "amount", "counterparty_name",
    "counterparty_logo_url", "card_id", "card_name", "user_id", "user_full_name", "initiated_at", "posted_at",
    "transaction_type", "status", "memo", "note", "attachments", "tracking_number", "lines",
}
ISO_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")


@pytest.fixture(scope="module")
def files() -> dict[str, list[dict]]:
    out = {}
    for stage in STAGES:
        doc = json.loads((DATA_DIR / f"{stage}.json").read_text(encoding="utf-8"))
        assert set(doc) == {"transactions"}, f"{stage}: envelope must be exactly {{'transactions': [...]}}"
        out[stage] = doc["transactions"]
    return out


@pytest.fixture(scope="module")
def rows(files) -> list[dict]:
    return [r for stage in STAGES for r in files[stage]]


def usd(r: dict) -> float:
    return -r["amount"]["amount"] / 100


def day(r: dict) -> date:
    return date.fromisoformat(r["initiated_at"][:10])


def series(rows, vendor: str, *, types=SPEND_TYPES) -> list[dict]:
    out = [r for r in rows if r["transaction_type"] in types and taxonomy.resolve(r["counterparty_name"]) == vendor]
    return sorted(out, key=lambda r: r["initiated_at"])


def monthly(rows, vendor: str) -> dict[str, float]:
    out: dict[str, float] = defaultdict(float)
    for r in series(rows, vendor):
        if r["status"] == "settled":
            out[r["initiated_at"][:7]] += usd(r)
    return dict(out)


# ---- reproducibility ------------------------------------------------------------------------


def test_regenerated_files_are_byte_identical(tmp_path):
    gen.write(tmp_path)
    for stage in STAGES:
        fresh = (tmp_path / f"{stage}.json").read_bytes()
        committed = (DATA_DIR / f"{stage}.json").read_bytes()
        assert fresh == committed, f"{stage}.json differs from a fresh `python -m data.generate`; regenerate and commit"


def test_two_runs_are_identical():
    assert gen.render(gen.generate()["inject-1"]) == gen.render(gen.generate()["inject-1"])


# ---- schema --------------------------------------------------------------------------------


def test_stage_windows_and_ordering(files):
    for stage, (start, end) in gen.STAGES.items():
        stamps = [r["initiated_at"] for r in files[stage]]
        assert stamps == sorted(stamps), f"{stage} not sorted by initiated_at"
        assert all(start <= day(r) <= end for r in files[stage]), f"{stage} has rows outside {start}..{end}"
    assert gen.STAGES["history"] == (date(2025, 9, 1), date(2026, 8, 31))
    assert gen.STAGES["inject-1"] == (date(2026, 9, 1), date(2026, 9, 5))
    assert gen.STAGES["inject-2"] == (date(2026, 9, 6), date(2026, 9, 30))


def test_row_shape(rows):
    assert 2000 <= len(rows) <= 5000, len(rows)
    ids = [r["id"] for r in rows]
    assert len(set(ids)) == len(ids), "duplicate transaction ids"
    accounts = {}
    for r in rows:
        assert set(r) == FIELDS, set(r) ^ FIELDS
        assert UUID.match(r["id"]) and UUID.match(r["money_movement_id"]) and UUID.match(r["account_id"])
        assert r["transaction_type"] in TX_TYPES, r["transaction_type"]
        assert r["status"] in STATUSES
        assert r["account_type"] in {"checking", "credit"}
        accounts.setdefault(r["account_id"], (r["account_name"], r["account_type"]))
        assert accounts[r["account_id"]] == (r["account_name"], r["account_type"])
        amt = r["amount"]
        assert set(amt) == {"amount", "currency"} and amt["currency"] == "USD"
        assert isinstance(amt["amount"], int) and not isinstance(amt["amount"], bool) and amt["amount"] != 0
        assert ISO_UTC.match(r["initiated_at"]), r["initiated_at"]
        assert (r["posted_at"] is None) == (r["status"] == "pending"), (r["status"], r["posted_at"])
        if r["posted_at"] is not None:
            assert ISO_UTC.match(r["posted_at"]) and r["posted_at"] >= r["initiated_at"]
        assert r["counterparty_logo_url"] is None and r["note"] is None and r["tracking_number"] is None
        assert r["attachments"] == [] and r["lines"] == []
        is_card = r["transaction_type"].startswith("card_")
        assert is_card == (r["account_type"] == "credit" and r["card_id"] is not None), r["transaction_type"]
        if is_card:
            assert UUID.match(r["card_id"]) and r["card_name"] and UUID.match(r["user_id"]) and r["user_full_name"]
        else:
            assert r["card_id"] is None and r["card_name"] is None
        assert (r["user_id"] is None) == (r["user_full_name"] is None)
    assert sorted(accounts.values()) == [("Operating Checking", "checking"), ("Rho Card", "credit")]


def test_amount_signs(rows):
    for r in rows:
        t, a = r["transaction_type"], r["amount"]["amount"]
        if t in {"card_debit", "ach_debit", "wire_out", "wire_fee", "treasury_deposit"}:
            assert a < 0, (t, a)
        elif t in CREDIT_TYPES:
            assert a > 0, (t, a)
        elif t == "internal_transfer":
            assert a < 0, (t, a)  # checking side of the card autopay
        else:
            pytest.fail(f"unexpected type in dataset: {t}")


# ---- planted scenarios ---------------------------------------------------------------------


def test_anthropic_september_invoice_breaks_trend(rows, files):
    s = series(rows, "Anthropic")
    assert [day(r).strftime("%Y-%m") for r in s] == [
        "2025-12", "2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06", "2026-07", "2026-08", "2026-09",
    ]
    aug, sep = usd(s[-2]), usd(s[-1])
    assert 21_000 <= aug <= 23_000, aug
    assert 1.55 <= sep / aug <= 1.65, sep / aug
    for prev, cur in zip(s[:-2], s[1:-1]):
        assert 1.08 <= usd(cur) / usd(prev) <= 1.22, (prev["initiated_at"], usd(cur) / usd(prev))
    assert day(s[-1]) == date(2026, 9, 2) and s[-1] in files["inject-1"]
    assert {r["counterparty_name"] for r in s} == {"ANTHROPIC* API", "Anthropic PBC", "ANTHROPIC PBC SAN FRANCISCO CA"}
    assert all(r["status"] == "settled" for r in s)


def test_pinecone_new_vendor(rows, files):
    s = sorted((r for r in rows if r["counterparty_name"] == "PINECONE SYSTEMS INC"), key=lambda r: r["initiated_at"])
    assert [day(r) for r in s] == [date(2026, 8, 4), date(2026, 9, 3)]
    assert abs(usd(s[0]) - 2_500) <= 75 and abs(usd(s[1]) - 6_500) <= 195, [usd(r) for r in s]
    assert all(r["transaction_type"] == "card_debit" and r["status"] == "settled" for r in s)
    assert s[0] in files["history"] and s[1] in files["inject-1"]
    assert taxonomy.resolve("PINECONE SYSTEMS INC") is None and "Pinecone" in taxonomy.KNOWN_UNKNOWN


def test_notion_seats_outgrow_headcount(rows):
    seats = {m: round(v / 16.00) for m, v in sorted(monthly(rows, "Notion").items())}
    assert all(seats[m] == 40 for m in seats if m < "2026-07"), seats
    assert (seats["2026-07"], seats["2026-08"], seats["2026-09"]) == (46, 52, 58), seats
    assert all(abs(v / 16.00 - round(v / 16.00)) < 1e-6 for v in monthly(rows, "Notion").values()), "price per seat moved"


def test_figma_price_creep(rows):
    m = monthly(rows, "Figma")
    assert all(v == 990.00 for k, v in m.items() if k < "2026-09"), m
    assert m["2026-09"] == 1_210.00
    assert abs(m["2026-09"] / m["2026-08"] - 55 / 45) < 1e-9
    sep = series(rows, "Figma")[-1]
    assert day(sep) == date(2026, 9, 1) and "22 seats" in sep["memo"]


def test_loom_stops(rows):
    s = series(rows, "Loom")
    assert len(s) == 11 and all(usd(r) == 1_440.00 and day(r).day == 6 for r in s)
    assert day(s[0]) == date(2025, 9, 6) and day(s[-1]) == date(2026, 7, 6)
    assert not [r for r in rows if taxonomy.resolve(r["counterparty_name"]) == "Loom" and day(r) > date(2026, 7, 6)]


def test_annual_vendors_charge_once(rows):
    for vendor, d, amount in [("Vanta", date(2025, 10, 12), 18_000.00), ("Carta", date(2026, 2, 10), 9_200.00),
                              ("Vouch Insurance", date(2026, 1, 15), 14_400.00)]:
        s = series(rows, vendor)
        assert len(s) == 1, (vendor, len(s))
        assert day(s[0]) == d and usd(s[0]) == amount and s[0]["transaction_type"] == "ach_debit", vendor
    assert day(series(rows, "Vanta")[0]) + timedelta(days=365) == date(2026, 10, 12)  # renewal inside inject-2's horizon


def test_payroll_semi_monthly_and_steps_with_headcount(rows):
    s = series(rows, "Gusto Payroll")
    dates = sorted({day(r) for r in s})
    assert len(dates) == 26 and all(d.day == 15 or (d + timedelta(days=1)).day == 1 for d in dates)
    assert all(r["transaction_type"] == "ach_debit" and r["user_id"] is None for r in s)
    m = monthly(rows, "Gusto Payroll")
    assert abs(m["2026-08"] / m["2026-05"] - 46 / 38) < 0.03, m["2026-08"] / m["2026-05"]
    assert m["2026-05"] < m["2026-06"] < m["2026-07"]
    assert 300_000 <= m["2026-08"] <= 350_000, m["2026-08"]
    assert {r["counterparty_name"] for r in s} == {"GUSTO PAYROLL", "GUSTO"}
    fee = monthly(rows, "Gusto (fee)")
    assert fee["2026-05"] == 268.00 and fee["2026-08"] == 316.00


def test_headcount_proxy_and_hiring_wave(rows):
    by_month: dict[str, set] = defaultdict(set)
    first_swipe: dict[str, date] = {}
    for r in rows:
        if r["transaction_type"] == "card_debit":
            by_month[r["initiated_at"][:7]].add(r["user_id"])
            first_swipe[r["user_full_name"]] = min(first_swipe.get(r["user_full_name"], day(r)), day(r))
    assert len(by_month["2026-05"]) == 34 and len(by_month["2026-08"]) == 42 and len(by_month["2026-09"]) == 42
    for name, _, start in gen.JUNE_HIRES:
        assert date(2026, 6, 1) <= start <= date(2026, 6, 20)
        assert 7 <= (first_swipe[name] - start).days <= 21, (name, first_swipe[name], start)
    teams = Counter(r["card_name"].split(" — ")[0] for r in rows if r["transaction_type"] == "card_debit")
    assert set(teams) == {"Eng", "GTM", "Ops"}


def test_offsite_spike_once(rows):
    offsite = [r for r in rows if date(2026, 4, 13) <= day(r) <= date(2026, 4, 16)
               and r["user_full_name"] == "Rachel Stern" and r["transaction_type"] == "card_debit"]
    total = sum(usd(r) for r in offsite)
    assert 26_000 <= total <= 30_000, total
    airbnb = series(rows, "Airbnb")
    assert len(airbnb) == 1 and day(airbnb[0]) == date(2026, 4, 13)


def test_no_prepaid_credit_purchases(rows):
    for r in rows:
        if r["transaction_type"] not in SPEND_TYPES:
            continue
        v = taxonomy.resolve(r["counterparty_name"])
        if (v and taxonomy.vendor(v).category == "AI & inference") or "PINECONE" in r["counterparty_name"]:
            assert r["amount"]["amount"] % 10_000 != 0, ("round AI charge", r["counterparty_name"], usd(r))
        assert not (usd(r) >= 5_000 and r["amount"]["amount"] % 500_000 == 0), ("round large charge", r["counterparty_name"], usd(r))


def test_september_is_otherwise_normal(rows):
    growth = {key: g for key, _, g, *_ in gen.USAGE_VENDORS}
    names = {"openai": "OpenAI", "aws": "AWS", "modal": "Modal", "vercel": "Vercel", "twilio": "Twilio",
             "datadog": "Datadog", "fireworks": "Fireworks AI", "googleads": "Google Ads", "posthog": "PostHog"}
    for key, name in names.items():
        m = monthly(rows, name)
        assert len(m) == 13, name
        ratio = m["2026-09"] / m["2026-08"]
        assert abs(ratio - growth[key]) <= 0.05, (name, ratio)
    for descriptors, price, *_ in gen.FIXED_VENDORS:
        name = taxonomy.resolve(descriptors[0])
        m = monthly(rows, name)
        assert len(m) == 13 and len(set(m.values())) == 1 and m["2026-09"] == price, name
    for descriptors, *_ in gen.SEAT_VENDORS:
        m = monthly(rows, taxonomy.resolve(descriptors[0]))
        assert m["2026-07"] == m["2026-08"] == m["2026-09"] and m["2026-05"] < m["2026-09"], descriptors[0]
    sep_spend = [r for r in rows if r["initiated_at"] >= "2026-09-06" and r["transaction_type"] in SPEND_TYPES]
    unresolved_big = [r for r in sep_spend if taxonomy.resolve(r["counterparty_name"]) is None and usd(r) > 1_000]
    assert unresolved_big == [], [(r["counterparty_name"], usd(r)) for r in unresolved_big]


# ---- noise the pipeline must exclude ---------------------------------------------------------


def test_money_movement_noise(rows, files):
    by_type = defaultdict(list)
    for r in rows:
        by_type[r["transaction_type"]].append(r)
    assert len(by_type["credit_repayment"]) == 12
    transfers = {r["money_movement_id"]: r for r in by_type["internal_transfer"]}
    for rep in by_type["credit_repayment"]:
        pair = transfers[rep["money_movement_id"]]
        assert pair["amount"]["amount"] == -rep["amount"]["amount"] and pair["account_type"] == "checking"
        assert rep["account_type"] == "credit"
    assert len(by_type["treasury_deposit"]) == 2 and min(usd(r) for r in by_type["treasury_deposit"]) >= 500_000
    assert len(by_type["rewards_accrual"]) == 12
    assert len(by_type["ach_credit"]) + len(by_type["wire_in"]) == 3
    assert len(by_type["card_refund"]) == 3
    fees = {r["money_movement_id"] for r in by_type["wire_fee"]}
    assert len(by_type["wire_out"]) == 4 and fees == {r["money_movement_id"] for r in by_type["wire_out"]}
    assert all(usd(r) == 25.00 for r in by_type["wire_fee"])
    failed = [r for r in rows if r["status"] == "failed"]
    assert len(failed) == 3 and all(r["transaction_type"] == "card_debit" for r in failed)
    for stage, (start, end) in gen.STAGES.items():
        pending = [r for r in files[stage] if r["status"] == "pending"]
        assert 3 <= len(pending) <= 4 and all(end - day(r) <= timedelta(days=1) for r in pending), stage


# ---- taxonomy --------------------------------------------------------------------------------


def test_taxonomy_contract():
    names = [v.name for v in taxonomy.VENDORS]
    assert len(names) == len(set(names)) and 38 <= len(names) <= 48
    for v in taxonomy.VENDORS:
        assert v.category in taxonomy.CATEGORIES, v
        assert v.cost_type in get_args(models.CostType), v
        assert v.cadence in get_args(models.Cadence), v
        for raw in (v.name, *v.aliases):
            assert taxonomy.resolve(raw) == v.name, raw
    for raw in taxonomy.KNOWN_UNKNOWN:
        assert taxonomy.resolve(raw) is None, raw
    assert set(taxonomy.CATEGORIES) == {
        "AI & inference", "Cloud & infra", "Data & tooling", "Software", "People & payroll", "Sales & marketing",
        "Office & travel", "Professional services", "Fees & other",
    }


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("ANTHROPIC* API", "Anthropic"), ("Anthropic PBC", "Anthropic"), ("ANTHROPIC PBC SAN FRANCISCO CA", "Anthropic"),
        ("AMAZON WEB SERVICES", "AWS"), ("AWS EMEA", "AWS"), ("Amazon Web Services, Inc.", "AWS"),
        ("GUSTO PAYROLL", "Gusto Payroll"), ("GUSTO", "Gusto Payroll"), ("GUSTO FEE", "Gusto (fee)"),
        ("GITHUB, INC.", "GitHub"), ("ZOOM.US 888-799-9666", "Zoom"), ("GOOGLE *ADS", "Google Ads"),
        ("GOOGLE *WORKSPACE", "Google Workspace"), ("notion labs, inc.", "Notion"), ("PINECONE SYSTEMS INC", None),
        ("CURSOR AI POWERED IDE", None), ("SWEETGREEN", None), ("CHIPOTLE 1234", None),
    ],
)
def test_resolve_examples(raw, expected):
    assert taxonomy.resolve(raw) == expected


def test_normalize_rules():
    assert taxonomy.normalize("ANTHROPIC PBC SAN FRANCISCO CA") == "anthropic"
    assert taxonomy.normalize("  Figma,  Inc. ") == "figma"
    assert taxonomy.normalize("UBER *TRIP") == "uber trip"
    assert taxonomy.normalize("STARBUCKS STORE 05421") == "starbucks store"
    assert taxonomy.normalize("1PASSWORD") == "1password"


def test_every_taxonomy_descriptor_in_data_resolves_and_unknowns_are_small(rows):
    spend_by_name: dict[str, float] = defaultdict(float)
    for r in rows:
        if r["transaction_type"] in SPEND_TYPES and r["status"] == "settled":
            spend_by_name[r["counterparty_name"]] += usd(r)
    unresolved = {k: v for k, v in spend_by_name.items() if taxonomy.resolve(k) is None}
    assert "PINECONE SYSTEMS INC" in unresolved
    per_month_cap = 2_000  # 13 months; anything bigger would sit near the 1 % materiality line
    too_big = {k: v for k, v in unresolved.items() if k != "PINECONE SYSTEMS INC" and v / 13 > per_month_cap}
    assert too_big == {}, too_big
    resolved_vendors = {taxonomy.resolve(k) for k in spend_by_name if taxonomy.resolve(k)}
    assert resolved_vendors == {v.name for v in taxonomy.VENDORS}, resolved_vendors ^ {v.name for v in taxonomy.VENDORS}
