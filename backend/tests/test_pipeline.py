"""Scenario tests for the deterministic pipeline (DESIGN.md section 8), on inline synthetic fixtures.

Every scenario is a small company: semi-monthly Gusto payroll (context only) plus ten cardholders
with varying Uber charges, so trailing spend is ~100K and the 1% materiality gate is ~1K. Vendors
under test are added on top. as_of defaults to 2026-08-31, so August is the evaluated month and
Feb-Jul the six-month baseline window.
"""

import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import pytest

from models import DEFAULT_CONFIG, Classification, Config, OpenIssue, Override, TypeThreshold
from pipeline.filter import classify_type, filter_spend
from pipeline.load import frame_from_transactions, load_stage
from pipeline.run import run_pipeline

FIXTURES = Path(__file__).parent / "fixtures"
AS_OF = date(2026, 8, 31)


# --- stand-in taxonomy (the real one is backend/taxonomy.py from the data worktree) ---------


@dataclass(frozen=True)
class Vendor:
    name: str
    aliases: tuple[str, ...]
    category: str
    cost_type: str
    cadence: str


class StubTaxonomy:
    VENDORS = [
        Vendor("Anthropic", ("ANTHROPIC* API", "Anthropic PBC"), "AI infrastructure", "usage", "monthly"),
        Vendor("AWS", ("AMAZON WEB SERVICES",), "Cloud", "usage", "monthly"),
        Vendor("Figma", ("FIGMA INC",), "Software", "fixed", "monthly"),
        Vendor("Datadog", (), "Software", "fixed", "monthly"),
        Vendor("Slack", ("SLACK TECHNOLOGIES",), "Software", "headcount", "monthly"),
        Vendor("Notion", ("NOTION LABS",), "Software", "headcount", "monthly"),
        Vendor("Gusto", ("GUSTO PAYROLL",), "Payroll", "payroll", "semi-monthly"),
        Vendor("Carta", (), "Legal & finance", "annual", "annual"),
    ]

    def normalize(self, name: str) -> str:
        return " ".join(str(name or "").upper().replace("*", " ").split())

    def resolve(self, name: str) -> str | None:
        key = self.normalize(name)
        for v in self.VENDORS:
            if key == v.name.upper() or key in {self.normalize(a) for a in v.aliases}:
                return v.name
        return None


# --- fixture builders ------------------------------------------------------------------------

_seq = 0


def tx(d: date, usd: float, name: str, *, type="card_debit", status="settled", user="u01",
       user_name=None, card_name=None, memo=None, tx_id=None) -> dict:
    global _seq
    _seq += 1
    sign = 1 if type in ("card_refund", "card_credit", "ach_return") else -1
    when = f"{d.isoformat()}T10:00:00Z"
    row = {
        "id": tx_id or f"t{_seq}",
        "amount": {"amount": sign * round(usd * 100), "currency": "USD"},
        "counterparty_name": name,
        "transaction_type": type,
        "status": status,
        "initiated_at": when,
        "posted_at": when if status == "settled" else None,
        "card_id": "c1" if type.startswith("card") else None,
        "card_name": card_name,
        "user_id": user if type.startswith("card") else None,
        "user_full_name": (user_name or user.upper()) if type.startswith("card") else None,
    }
    if memo is not None:
        row["memo"] = memo
    return row


def month_end(y: int, m: int) -> date:
    return date(y, m, calendar.monthrange(y, m)[1])


def company(months=range(1, 9), year=2026, users=10, extra_users: dict[int, int] | None = None,
            payroll=50_000.0, payroll_step_month=None, payroll_step=1.0) -> list[dict]:
    """Payroll twice a month plus `users` cardholders each with one varying Uber charge a month;
    `extra_users` adds cardholders in given months (a hiring step)."""
    rows = []
    for m in months:
        p = payroll * (payroll_step if payroll_step_month and m >= payroll_step_month else 1.0)
        rows.append(tx(date(year, m, 15), p, "Gusto", type="ach_debit"))
        rows.append(tx(month_end(year, m), p, "Gusto", type="ach_debit"))
        n = users + (extra_users or {}).get(m, 0)
        for i in range(n):
            rows.append(tx(date(year, m, 3 + i % 20), 20 + (m * 7 + i * 3) % 11, "UBER *TRIP", user=f"u{i + 1:02d}"))
    return rows


def monthly(name: str, amounts: dict[int, float], day=3, year=2026, **kw) -> list[dict]:
    return [tx(date(year, m, day), a, name, **kw) for m, a in amounts.items()]


def trend(base: float, growth: float, months=range(1, 9)) -> dict[int, float]:
    return {m: round(base * (1 + growth) ** (m - 1), 2) for m in months}


def run(rows, as_of=AS_OF, **kw):
    return run_pipeline(frame_from_transactions(rows), as_of, taxonomy=StubTaxonomy(), **kw)


def find(result, vendor, kind=None):
    return [f for f in result.findings if f.vendor == vendor and (kind is None or f.kind == kind)]


def threshold(result, cost_type="usage", config=DEFAULT_CONFIG):
    return config.thresholds[cost_type].alert_pct * result.trailing_monthly_spend


# --- growth (usage) ---------------------------------------------------------------------------


def test_steady_growth_on_trend_is_not_a_finding():
    r = run(company() + monthly("ANTHROPIC* API", trend(1000, 0.15)))
    assert find(r, "Anthropic") == []
    v = next(v for v in r.vendors if v.vendor == "Anthropic")
    assert v.cost_type == "usage" and v.cost_type_source == "taxonomy" and v.cadence == "monthly"
    assert v.growth_pct == pytest.approx(0.15, abs=0.005)


def test_small_deviation_on_a_smooth_history_is_not_unusual():
    # Residual sigma is floored at 0.08: a near-perfect history (about 1% noise) must not make a
    # +10% month "unusual" (2 x 0.08 = 0.16 in log terms).
    amounts = trend(1000, 0.15)
    wobble = {1: 1.01, 2: 0.99, 3: 1.01, 4: 0.99, 5: 1.01, 6: 0.99, 7: 1.01}
    amounts = {m: round(a * wobble.get(m, 1.0), 2) for m, a in amounts.items()}
    amounts[8] = round(amounts[8] * 1.10, 2)
    r = run(company() + monthly("ANTHROPIC* API", amounts))
    assert find(r, "Anthropic") == []


def test_growth_break_material_alerts():
    amounts = trend(1000, 0.15)
    expected_aug = amounts[8]
    amounts[8] = round(1.6 * expected_aug, 2)
    r = run(company() + monthly("Anthropic PBC", amounts))
    (f,) = find(r, "Anthropic")
    assert f.kind == "growth_break" and f.route == "alert"
    assert f.baseline.expected_monthly == pytest.approx(expected_aug, rel=0.01)
    assert f.impact_monthly == pytest.approx(amounts[8] - expected_aug, rel=0.01)
    assert abs(f.impact_monthly) >= threshold(r)
    assert f.baseline.n_obs == 6 and f.confidence == "high"
    assert f.ask_cost_type is False
    assert f.id == "anthropic:growth_break:2026-08-31" and f.month == "2026-08"
    assert [d.driver for d in f.drivers] == ["volume"]


def test_growth_break_below_materiality_reports():
    # Impact lands between the report floor (0.25%) and the alert bar (1%): a report line.
    amounts = trend(300, 0.15)
    amounts[8] = round(1.6 * amounts[8], 2)
    r = run(company() + monthly("ANTHROPIC* API", amounts))
    (f,) = find(r, "Anthropic")
    assert f.kind == "growth_break" and f.route == "report"
    assert DEFAULT_CONFIG.report_floor_pct * r.trailing_monthly_spend <= f.impact_monthly < threshold(r)


def test_growth_break_under_the_report_floor_is_dropped():
    amounts = trend(100, 0.15)  # the same break at a third of the size is under 0.25% of spend
    amounts[8] = round(1.6 * amounts[8], 2)
    r = run(company() + monthly("ANTHROPIC* API", amounts))
    assert find(r, "Anthropic") == []


def test_growth_break_in_partial_month_uses_the_invoice_that_arrived():
    amounts = trend(1000, 0.15, range(1, 10))
    expected_sep = amounts[9]
    amounts[9] = round(1.6 * expected_sep, 2)
    rows = company() + monthly("ANTHROPIC* API", amounts) + monthly("Figma", {m: 500 for m in range(1, 9)}, day=10)
    r = run(rows, as_of=date(2026, 9, 5))
    (f,) = find(r, "Anthropic")
    assert f.kind == "growth_break" and f.route == "alert" and f.month == "2026-09"
    assert f.baseline.expected_monthly == pytest.approx(expected_sep, rel=0.01)
    assert find(r, "Figma") == []  # its 10th-of-month charge has not arrived: not stopped, not evaluated
    assert r.window_end == date(2026, 9, 5)


def test_partial_month_skips_vendors_whose_month_is_not_in_yet():
    # Semi-monthly fixed vendor: 250 on the 1st and 16th. On 5 Sep only the first half is in.
    rows = company()
    for m in range(1, 10):
        rows.append(tx(date(2026, m, 1), 250, "Datadog"))
        if m < 9:
            rows.append(tx(date(2026, m, 16), 250, "Datadog"))
    r = run(rows, as_of=date(2026, 9, 5))
    assert find(r, "Datadog") == []
    assert next(v for v in r.vendors if v.vendor == "Datadog").cadence == "semi-monthly"
    assert next(v for v in r.vendors if v.vendor == "Datadog").monthly_spend == 500  # last complete month


# --- fixed price ------------------------------------------------------------------------------


def test_fixed_price_up_22pct_reports_when_small_and_alerts_when_material():
    small = monthly("Figma", {**{m: 500 for m in range(1, 8)}, 8: 610})
    r = run(company() + small)
    (f,) = find(r, "Figma")
    assert f.kind == "price_change" and f.route == "report"
    assert f.impact_monthly == pytest.approx(110)
    assert f.baseline.last_price == 500 and f.drivers[0].driver == "price"

    big = monthly("Datadog", {**{m: 10_000 for m in range(1, 8)}, 8: 12_200})
    r = run(company() + big)
    (f,) = find(r, "Datadog")
    assert f.kind == "price_change" and f.route == "alert" and f.impact_monthly == pytest.approx(2200)
    assert f.confidence == "high"


def test_fixed_price_up_half_pct_is_nothing():
    r = run(company() + monthly("Figma", {**{m: 500 for m in range(1, 8)}, 8: 502.5}))
    assert find(r, "Figma") == []


def test_fixed_vendor_with_no_stable_price_has_no_baseline():
    r = run(company() + monthly("Figma", {m: 500 + 7 * m for m in range(1, 9)}))
    assert find(r, "Figma") == []


# --- new vendor -------------------------------------------------------------------------------


def test_new_unknown_vendor_material_alerts_and_asks_cost_type():
    r = run(company() + monthly("PINECONE SYSTEMS", {7: 1000, 8: 2400}))
    (f,) = find(r, "Pinecone Systems")
    assert f.kind == "new_vendor" and f.route == "alert"
    assert f.impact_monthly == pytest.approx(2400) and f.baseline.expected_monthly == 0
    assert f.cost_type_source == "default" and f.ask_cost_type is True
    assert [d.driver for d in f.drivers] == ["new"] and f.confidence == "low"


def test_new_vendor_small_reports_without_ask():
    r = run(company() + monthly("PINECONE SYSTEMS", {7: 300, 8: 500}))  # 0.45% of spend: floor < impact < alert bar
    (f,) = find(r, "Pinecone Systems")
    assert f.kind == "new_vendor" and f.route == "report" and f.ask_cost_type is False


def test_new_vendor_only_fires_the_month_the_second_charge_lands():
    # Second charge landed in July; an August charge must not re-raise "new vendor".
    r = run(company() + monthly("PINECONE SYSTEMS", {6: 1000, 7: 2400, 8: 2400}))
    assert find(r, "Pinecone Systems", "new_vendor") == []
    assert next(v for v in r.vendors if v.vendor == "Pinecone Systems").monthly_spend == 2400
    r = run(company() + monthly("PINECONE SYSTEMS", {8: 2400}))
    assert find(r, "Pinecone Systems", "new_vendor") == []


# --- stopped ------------------------------------------------------------------------------------


def test_stopped_vendor_reports_with_negative_impact():
    r = run(company() + monthly("Datadog", {m: 800 for m in range(1, 8)}, day=10))
    (f,) = find(r, "Datadog")
    assert f.kind == "stopped" and f.route == "report"
    assert f.impact_monthly == pytest.approx(-800) and f.actual_monthly == 0
    assert [d.driver for d in f.drivers] == ["missing"]


def test_stopped_needs_grace_beyond_cadence():
    r = run(company() + monthly("Datadog", {m: 800 for m in range(1, 8)}, day=28))
    assert find(r, "Datadog", "stopped") == []  # due 28 Aug + 5 days grace = 2 Sep, not yet


def test_stopped_material_vendor_still_only_reports():
    r = run(company() + monthly("Datadog", {m: 20_000 for m in range(1, 8)}, day=10))
    (f,) = find(r, "Datadog", "stopped")
    assert f.route == "report" and abs(f.impact_monthly) > threshold(r, "fixed")


# --- spike --------------------------------------------------------------------------------------


def test_one_off_spike_reverts_and_never_alerts():
    rows = company() + [tx(date(2026, 5, 12), 8000, "GRAND HOTEL OFFSITE", user="u03")]
    assert find(run(rows), "Grand Hotel Offsite") == []
    (f,) = find(run(rows, as_of=date(2026, 5, 31)), "Grand Hotel Offsite")
    assert f.kind == "spike" and f.route == "report" and f.impact_monthly == 8000
    assert f.cardholders == ["U03"]
    assert find(run(company() + [tx(date(2026, 8, 12), 40, "CORNER CAFE")]), "Corner Cafe") == []


# --- headcount ----------------------------------------------------------------------------------


def test_hiring_step_with_flat_cost_per_head_is_not_a_finding():
    rows = company(extra_users={8: 2}, payroll_step_month=8, payroll_step=1.2)
    rows += monthly("Slack", {**{m: 500 for m in range(1, 8)}, 8: 600})
    r = run(rows)
    assert r.headcount_proxy == 12
    assert find(r, "Slack", "per_head") == []
    assert find(r, "Gusto") == []
    assert next(v for v in r.vendors if v.vendor == "Gusto").cost_type == "payroll"


def test_cost_per_head_rising_25pct_is_per_head():
    r = run(company() + monthly("Notion", {**{m: 500 for m in range(1, 8)}, 8: 625}))
    (f,) = find(r, "Notion")
    assert f.kind == "per_head" and f.route == "report"
    assert f.baseline.cost_per_head == pytest.approx(50) and f.baseline.headcount_proxy == 10
    assert f.impact_monthly == pytest.approx(125)

    r = run(company() + monthly("Notion", {**{m: 10_000 for m in range(1, 8)}, 8: 12_500}))
    (f,) = find(r, "Notion", "per_head")
    assert f.route == "alert" and f.impact_monthly == pytest.approx(2500)


# --- routing, dedupe, config --------------------------------------------------------------------


def two_breaks():
    a = trend(1000, 0.15)
    a[8] = round(1.6 * a[8], 2)
    return company() + monthly("Anthropic PBC", a) + monthly("Datadog", {**{m: 10_000 for m in range(1, 8)}, 8: 12_200})


def test_two_unrelated_breaks_give_two_alerts():
    r = run(two_breaks())
    alerts = [f for f in r.findings if f.route == "alert"]
    assert {(f.vendor, f.kind) for f in alerts} == {("Anthropic", "growth_break"), ("Datadog", "price_change")}
    assert r.findings[:2] == alerts and abs(alerts[0].impact_monthly) >= abs(alerts[1].impact_monthly)


def test_open_issue_downgrades_repeat_to_report_unless_escalated():
    base = run(two_breaks())
    anth = find(base, "Anthropic")[0]
    issue = OpenIssue(id="prev", vendor="Anthropic", kind="growth_break", impact_monthly=anth.impact_monthly)
    r = run(two_breaks(), open_issues=[issue])
    f = find(r, "Anthropic")[0]
    assert f.route == "report" and f.escalation_of is None
    assert find(r, "Datadog")[0].route == "alert"

    # Escalation needs both: >= 1.5x the open issue's impact AND growth of at least one threshold.
    small = OpenIssue(id="old", vendor="anthropic", kind="growth_break", impact_monthly=anth.impact_monthly / 4)
    f = find(run(two_breaks(), open_issues=[small]), "Anthropic")[0]
    assert f.impact_monthly - small.impact_monthly >= threshold(base)
    assert f.route == "alert" and f.escalation_of == "old"
    ratio_only = OpenIssue(id="old", vendor="anthropic", kind="growth_break", impact_monthly=600)
    assert anth.impact_monthly >= 1.5 * 600 and anth.impact_monthly - 600 < threshold(base)
    f = find(run(two_breaks(), open_issues=[ratio_only]), "Anthropic")[0]
    assert f.route == "report" and f.escalation_of is None


def test_thresholds_from_config_change_routing():
    strict = Config(thresholds={**DEFAULT_CONFIG.thresholds, "usage": TypeThreshold(alert_pct=0.05)})
    r = run(two_breaks(), config=strict)
    assert find(r, "Anthropic")[0].route == "report"
    assert find(r, "Datadog")[0].route == "alert"
    muted = Config(thresholds={**DEFAULT_CONFIG.thresholds, "fixed": TypeThreshold(alert_pct=0.01, alerts=False)})
    assert find(run(two_breaks(), config=muted), "Datadog")[0].route == "report"


# --- annual -------------------------------------------------------------------------------------


def test_annual_vendor_30_days_before_anniversary_is_a_renewal_notice():
    rows = company() + [tx(AS_OF - timedelta(days=335), 12_000, "Carta", type="ach_debit")]
    (f,) = find(run(rows), "Carta")
    assert f.kind == "renewal" and f.route == "report" and f.impact_monthly == 12_000
    assert f.ask_cost_type is False and f.drivers == []
    far = company() + [tx(AS_OF - timedelta(days=200), 12_000, "Carta", type="ach_debit")]
    assert find(run(far), "Carta") == []


# --- filtering ----------------------------------------------------------------------------------


def test_refunds_net_against_the_same_vendor():
    rows = company() + monthly("Figma", {m: 500 for m in range(1, 9)})
    doubled = rows + [tx(date(2026, 8, 20), 500, "Figma")]
    assert find(run(doubled), "Figma")[0].kind == "price_change"
    netted = doubled + [tx(date(2026, 8, 22), 500, "Figma", type="card_refund")]
    r = run(netted)
    assert find(r, "Figma") == []
    assert next(v for v in r.vendors if v.vendor == "Figma").monthly_spend == 500


def test_money_movement_inflows_and_unknown_types_are_excluded():
    rows = company()
    clean = run(rows)
    noisy = rows + [
        tx(date(2026, 7, 20), 60_000, "Rho", type="credit_repayment", user="u01"),
        tx(date(2026, 7, 21), 30_000, "Rho Treasury", type="treasury_deposit"),
        tx(date(2026, 7, 22), 5_000, "Rho", type="internal_transfer"),
        tx(date(2026, 7, 23), 900, "Rho Rewards", type="rewards_accrual"),
        tx(date(2026, 7, 24), 250_000, "Investor LP", type="wire_in"),
        tx(date(2026, 7, 25), 1_234, "Future Rail", type="hyperloop_debit"),
        tx(date(2026, 7, 26), 700, "Figma", status="reversed"),
    ]
    r = run(noisy)
    assert r.trailing_monthly_spend == clean.trailing_monthly_spend
    assert {v.vendor for v in r.vendors} == {v.vendor for v in clean.vendors}
    assert classify_type("hyperloop_debit") == "unknown" and classify_type("treasury_fee") == "fee"


def test_pending_rows_are_visible_but_not_in_baselines():
    rows = company() + monthly("Figma", {m: 500 for m in range(1, 8)}) + [tx(date(2026, 8, 3), 900, "Figma", status="pending")]
    spend = filter_spend(frame_from_transactions(rows))
    assert (~spend["settled"]).sum() == 1
    r = run(rows)
    assert find(r, "Figma", "price_change") == []
    assert next(v for v in r.vendors if v.vendor == "Figma").monthly_spend == 0


def test_fees_are_context_only():
    rows = company() + [tx(date(2026, m, 5), 25, None, type="wire_fee") for m in range(1, 8)] + [tx(date(2026, 8, 5), 75, None, type="wire_fee")]
    r = run(rows)
    assert find(r, "Rho fees") == []
    assert r.category_totals["Fees & other"] == 75


# --- classification precedence ------------------------------------------------------------------


def test_unknown_vendor_defaults_until_hook_or_override():
    rows = (
        company()
        + monthly("PINECONE SYSTEMS", {6: 800, 7: 1000, 8: 2400}, memo="vector db")
        + monthly("TINY TOOL", {m: 6 for m in range(1, 9)})  # recurring but far below the report floor
    )
    v = next(v for v in run(rows).vendors if v.vendor == "Pinecone Systems")
    assert (v.cost_type, v.category, v.cost_type_source) == ("fixed", "Software", "default")

    seen = {}

    def hook(facts):
        seen.update({f.vendor: f for f in facts})
        return {"Pinecone Systems": Classification(cost_type="usage", category="AI infrastructure", confidence="high")}

    r = run(rows, classify_unknown=hook)
    v = next(v for v in r.vendors if v.vendor == "Pinecone Systems")
    assert (v.cost_type, v.category, v.cost_type_source) == ("usage", "AI infrastructure", "llm")
    facts = seen["Pinecone Systems"]
    assert facts.monthly_amounts == {"2026-06": 800, "2026-07": 1000, "2026-08": 2400}
    assert facts.cadence == "monthly" and facts.sample_memos == ["vector db"]
    # Only unknown recurring vendors that have reached the report floor (0.25% of trailing spend,
    # ~$280 here) in some month go to the hook: Pinecone does, Uber (peaks near $300) does, a
    # $6/mo tool does not, and Anthropic is known. Those below the floor stay at "default".
    assert "Anthropic" not in seen and "Uber Trip" in seen and "Tiny Tool" not in seen
    assert next(v for v in r.vendors if v.vendor == "Tiny Tool").cost_type_source == "default"
    assert r.recurring_vendor_count is not None and r.recurring_vendor_count < len(r.vendors)

    r = run(rows, classify_unknown=hook, overrides=[Override(vendor="pinecone systems", cost_type="headcount")])
    v = next(v for v in r.vendors if v.vendor == "Pinecone Systems")
    assert (v.cost_type, v.cost_type_source) == ("headcount", "user")


def test_override_wins_over_taxonomy():
    amounts = trend(1000, 0.15)
    amounts[8] = round(1.6 * amounts[8], 2)
    r = run(company() + monthly("Anthropic PBC", amounts), overrides=[Override(vendor="Anthropic", cost_type="fixed")])
    assert find(r, "Anthropic", "growth_break") == []
    v = next(v for v in r.vendors if v.vendor == "Anthropic")
    assert v.cost_type == "fixed" and v.cost_type_source == "user"
    assert find(r, "Anthropic", "price_change") == []  # never two identical prices on a growth curve


# --- explanation --------------------------------------------------------------------------------


def test_driver_shares_sum_to_one_and_name_the_cardholder():
    rows = company()
    for m in range(1, 9):
        for u in ("u01", "u02", "u03"):
            rows.append(tx(date(2026, m, 6), 100, "AMAZON WEB SERVICES", user=u))
    rows += [tx(date(2026, 8, 20), 2000, "AMAZON WEB SERVICES", user="u02")]
    (f,) = find(run(rows), "AWS")
    assert f.kind == "growth_break"
    assert sum(d.share for d in f.drivers) == pytest.approx(1.0, abs=0.01)
    who = next(d for d in f.drivers if d.driver == "who")
    assert who.share >= 0.6 and f.cardholders[0] == "U02"
    assert f.confidence == "high"


def test_confidence_drops_with_fewer_observations():
    amounts = trend(1000, 0.15, range(4, 9))
    amounts[8] = round(1.6 * amounts[8], 2)
    (f,) = find(run(company() + monthly("ANTHROPIC* API", amounts)), "Anthropic")
    assert f.baseline.n_obs == 4 and f.confidence == "medium"


# --- summary fields -----------------------------------------------------------------------------


def test_findings_summary_fields():
    r = run(two_breaks(), stage="history")
    assert r.stage == "history" and r.window_start == date(2026, 2, 1) and r.window_end == AS_OF
    assert r.headcount_proxy == 10
    assert r.trailing_monthly_spend == pytest.approx(100_000 + 10_000 + 2_000 + 250, rel=0.02)
    assert r.category_totals["Payroll"] == 100_000
    assert "Uber Trip" in {v.vendor for v in r.vendors}  # unknown vendor keyed by taxonomy.normalize
    names = [v.vendor for v in r.vendors]
    assert names[0] == "Gusto" and names.index("Datadog") < names.index("Anthropic")


def test_reporting_period_is_first_run_for_history_and_the_month_otherwise():
    # The period is what the report is about; window_start stays the baseline fitting range.
    first = run(two_breaks(), stage="history")
    assert first.period is not None and first.period.kind == "first_run"
    assert first.period.start == first.data_start and first.data_start is not None and first.data_start.month == 1
    assert first.period.end == AS_OF and first.period.label == "Jan 2026 – Aug 2026"
    assert first.window_start == date(2026, 2, 1)  # baseline window, unchanged
    assert first.transaction_count is not None and 0 < first.transaction_count <= len(two_breaks())

    month = run(two_breaks(), stage="inject-2")
    assert month.period is not None and month.period.kind == "month"
    assert (month.period.label, month.period.start, month.period.end) == ("August 2026", date(2026, 8, 1), AS_OF)

    partial = run(two_breaks(), as_of=date(2026, 8, 5), stage="inject-1")
    assert partial.period is not None and partial.period.label == "August 2026 (through Aug 5)"


def test_empty_frame_gives_well_formed_empty_findings():
    r = run([], as_of=date(2026, 9, 5), stage="inject-1")
    assert r.findings == [] and r.vendors == [] and r.category_totals == {}
    assert r.trailing_monthly_spend == 0 and r.headcount_proxy == 0 and r.stage == "inject-1"


# --- loading ------------------------------------------------------------------------------------


def test_load_stage_tolerates_missing_fields_and_dedupes_by_id():
    df, as_of = load_stage("history", FIXTURES)
    assert as_of == date(2026, 8, 31) and len(df) == 6 and "memo" in df.columns
    df2, as_of2 = load_stage("inject-2", FIXTURES)
    assert as_of2 == date(2026, 9, 30) and len(df2) == 9  # h6 pending replaced by its settled version
    spend = filter_spend(df2)
    assert set(spend["transaction_type"]) == {"card_debit", "ach_debit", "card_refund"}
    r = run_pipeline(df2, as_of2, taxonomy=StubTaxonomy(), stage="inject-2")
    assert r.category_totals["Payroll"] == 50_000
    with pytest.raises(FileNotFoundError):
        load_stage("inject-1", FIXTURES / "nope")
