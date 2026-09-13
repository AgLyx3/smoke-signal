"""Cash position: runway and the treasury arithmetic are plain and checkable."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

import taxonomy
from models import DEFAULT_CONFIG
from pipeline import load_stage, run_pipeline
from pipeline.cash import cash_position, load_accounts, monthly_inflows, runway_weeks_delta
from pipeline.load import frame_from_transactions

DATA = Path(__file__).resolve().parents[1] / "data"


def _accounts(operating: float, treasury: float) -> dict:
    return {
        "as_of": "2026-08-31",
        "accounts": [
            {"account_type": "checking", "balance": {"amount": int(operating * 100)}},
            {"account_type": "investment", "balance": {"amount": int(treasury * 100)}},
            {"account_type": "credit", "balance": {"amount": -500_000}},  # card balance is not cash
        ],
    }


def _inflow(day: str, usd: float, kind: str = "wire_in", status: str = "settled") -> dict:
    return {"id": f"in-{day}-{usd}", "transaction_type": kind, "status": status, "initiated_at": f"{day}T10:00:00Z", "amount": {"amount": int(usd * 100), "currency": "USD"}}


def test_runway_and_sweep_arithmetic():
    # As of Aug 31 the evaluated month is August; inflows, like trailing spend, average the three
    # complete months before it (May–Jul).
    df = frame_from_transactions([_inflow("2026-05-10", 30_000), _inflow("2026-06-10", 30_000), _inflow("2026-07-10", 30_000)])
    cash = cash_position(df, date(2026, 8, 31), 480_000, _accounts(2_350_000, 7_400_000), buffer_months=3.0, treasury_apy=0.038)
    assert cash is not None
    assert cash.monthly_inflows == 30_000 and cash.net_burn_monthly == 450_000
    assert cash.total_cash == 9_750_000 and cash.runway_months == pytest.approx(21.7, abs=0.05)
    assert cash.operating_months_of_burn == pytest.approx(5.2, abs=0.05)
    assert cash.recommended_operating == 1_350_000 and cash.sweep_to_treasury == 1_000_000 and cash.shortfall_from_treasury == 0
    assert cash.treasury_upside_monthly == pytest.approx(1_000_000 * 0.038 / 12, abs=0.01)


def test_shortfall_when_operating_is_thin_and_no_sweep():
    df = frame_from_transactions([])
    cash = cash_position(df, date(2026, 8, 31), 400_000, _accounts(600_000, 5_000_000), buffer_months=3.0, treasury_apy=0.04)
    assert cash is not None
    assert cash.sweep_to_treasury == 0 and cash.shortfall_from_treasury == 600_000 and cash.treasury_upside_monthly == 0


def test_inflows_use_only_the_three_complete_months_before_eval_and_only_settled():
    df = frame_from_transactions([
        _inflow("2026-05-01", 900_000),  # outside the window
        _inflow("2026-06-15", 60_000),
        _inflow("2026-08-20", 30_000),
        _inflow("2026-08-25", 999_999, status="pending"),  # not settled
        _inflow("2026-09-02", 500_000),  # the evaluated month itself
    ])
    assert monthly_inflows(df, eval_month=2026 * 12 + 8) == pytest.approx(30_000)


def test_large_unclassified_inflow_is_asked_about_and_funding_is_not_counted():
    from models import InflowOverride

    df = frame_from_transactions([_inflow("2026-06-10", 30_000), _inflow("2026-07-15", 200_000)])
    cash = cash_position(df, date(2026, 8, 31), 480_000, _accounts(2_350_000, 7_400_000), 3.0, 0.038)
    assert cash is not None
    assert [i.amount for i in cash.inflow_ask] == [200_000, 30_000]  # both clear 5% of $480K ($24K); largest first
    assert cash.monthly_inflows == pytest.approx((30_000 + 200_000) / 3)
    wire_id = cash.inflow_ask[0].id
    answered = cash_position(
        df, date(2026, 8, 31), 480_000, _accounts(2_350_000, 7_400_000), 3.0, 0.038, [InflowOverride(id=wire_id, kind="funding")]
    )
    assert answered is not None and [i.amount for i in answered.inflow_ask] == [30_000]  # answered ones are not re-asked
    assert answered.monthly_inflows == pytest.approx(10_000)  # only the customer-sized $30K counts now
    assert answered.net_burn_monthly > cash.net_burn_monthly and (answered.runway_months or 0) < (cash.runway_months or 0)
    assert next(i for i in answered.inflows if i.id == wire_id).counted is False


def test_runway_weeks_delta_sign_and_size():
    # $9.75M cash, $450K burn: 21.67 months. +$9,578/mo -> 21.21 months: about 2.0 weeks lost.
    lost = runway_weeks_delta(9_750_000, 450_000, 9_578.47)
    assert lost is not None and 1.9 < lost < 2.1
    gained = runway_weeks_delta(9_750_000, 450_000, -1_440)
    assert gained is not None and gained < 0
    assert runway_weeks_delta(9_750_000, 0.0, 1_000) is None


def test_pipeline_attaches_runway_to_findings_but_not_to_renewals():
    df, as_of = load_stage("inject-2", DATA)
    accounts = load_accounts(DATA, "inject-2")
    out = run_pipeline(df, as_of, DEFAULT_CONFIG, [], [], taxonomy=taxonomy, stage="inject-2", accounts=accounts)
    assert out.cash is not None and out.cash.runway_months and 15 < out.cash.runway_months < 30
    by = {(f.vendor, f.kind): f for f in out.findings}
    assert by[("Anthropic", "growth_break")].runway_weeks_delta and by[("Anthropic", "growth_break")].runway_weeks_delta > 1
    assert by[("Loom", "stopped")].runway_weeks_delta and by[("Loom", "stopped")].runway_weeks_delta < 0
    assert by[("Vanta", "renewal")].runway_weeks_delta is None


def test_no_accounts_means_no_cash_block():
    df, as_of = load_stage("history", DATA)
    out = run_pipeline(df, as_of, DEFAULT_CONFIG, [], [], taxonomy=taxonomy, stage="history", accounts=None)
    assert out.cash is None and all(f.runway_weeks_delta is None for f in out.findings)
