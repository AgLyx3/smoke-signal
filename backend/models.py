"""API contract. Pydantic is the source of truth; frontend types are generated from
FastAPI's OpenAPI (see `npm run types` in frontend/). Change here first, then regenerate."""

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field

Stage = Literal["history", "inject-1", "inject-2"]
CostType = Literal["usage", "fixed", "headcount", "annual", "payroll"]
CostTypeSource = Literal["taxonomy", "llm", "user", "default"]  # default = unknown vendor, no hook result
Cadence = Literal["semi-monthly", "monthly", "annual", "irregular"]
Kind = Literal[
    "growth_break",  # usage vendor off its own trajectory
    "price_change",  # fixed vendor, same plan, new price
    "new_vendor",  # second regular charge confirms recurrence
    "stopped",  # expected charge overdue
    "per_head",  # cost per head above its own range
    "renewal",  # annual charge coming up; never alerts
    "spike",  # one-off, no recurrence; context only
]
Route = Literal["alert", "report", "ignore"]
Driver = Literal["price", "volume", "new", "missing", "who"]
Confidence = Literal["high", "medium", "low"]


class TypeThreshold(BaseModel):
    alert_pct: float = Field(description="Alert when monthly impact >= this share of trailing monthly spend")
    alerts: bool = Field(default=True, description="False for types that never alert (annual, payroll)")


class Config(BaseModel):
    thresholds: dict[CostType, TypeThreshold]
    report_floor_pct: float = Field(
        default=0.0025,
        description="Below this share of trailing monthly spend a change is dropped from the report, unless it is "
        "a price change, per-head rise or renewal on a vendor whose cost type is confirmed or classified",
    )
    buffer_months: float = Field(default=3.0, description="Months of net burn to keep in operating checking")
    treasury_apy: float = Field(default=0.038, description="Assumed Rho Treasury yield, for the cash position")


DEFAULT_CONFIG = Config(
    thresholds={
        "usage": TypeThreshold(alert_pct=0.01),
        "fixed": TypeThreshold(alert_pct=0.01),
        "headcount": TypeThreshold(alert_pct=0.01),
        "annual": TypeThreshold(alert_pct=0.01, alerts=False),
        "payroll": TypeThreshold(alert_pct=0.01, alerts=False),
    }
)


class Override(BaseModel):
    vendor: str
    cost_type: CostType


class OpenIssue(BaseModel):
    """An issue already alerted on; carried by the client so reruns dedupe against it."""

    id: str
    vendor: str
    kind: Kind
    impact_monthly: float


InflowKind = Literal["customer", "funding", "refund", "transfer", "other"]


class InflowOverride(BaseModel):
    """The founder's answer to "what was this inflow?". Only customer payments count as cash in."""

    id: str
    kind: InflowKind


class RunRequest(BaseModel):
    stage: Stage
    config: Config | None = None
    overrides: list[Override] = []
    open_issues: list[OpenIssue] = []
    inflow_overrides: list[InflowOverride] = []


class DriverShare(BaseModel):
    driver: Driver
    share: float = Field(ge=0, le=1)


class Baseline(BaseModel):
    n_obs: int
    expected_monthly: float
    growth_pct: float | None = Field(default=None, description="Fitted month-over-month growth, usage vendors")
    sigma: float | None = Field(default=None, description="Std dev of the vendor's own residuals")
    last_price: float | None = None
    cost_per_head: float | None = None
    headcount_proxy: int | None = Field(default=None, description="Cardholder proxy used for the evaluated month")


class Finding(BaseModel):
    id: str
    vendor: str
    category: str
    cost_type: CostType
    cost_type_source: CostTypeSource
    kind: Kind
    route: Route
    actual_monthly: float
    impact_monthly: float = Field(description="actual - expected; negative for decreases")
    impact_pct_of_spend: float
    baseline: Baseline
    drivers: list[DriverShare]
    confidence: Confidence
    ask_cost_type: bool = Field(default=False, description="Ask the user to confirm cost_type before showing")
    escalation_of: str | None = Field(default=None, description="OpenIssue id this re-alert escalates")
    cardholders: list[str] = []
    month: str | None = Field(default=None, description="Evaluated calendar month, YYYY-MM")
    runway_weeks_delta: float | None = Field(
        default=None, description="Weeks of runway lost (positive) or gained (negative) if this monthly change persists; None without a cash position or for one-offs"
    )


class VendorFacts(BaseModel):
    """What the classifier hook sees for an unknown vendor: facts only, no decision."""

    vendor: str
    monthly_amounts: dict[str, float] = Field(description="YYYY-MM -> settled net spend")
    cadence: Cadence
    charge_count: int
    sample_descriptors: list[str] = Field(default=[], description="Raw counterparty_name variants")
    sample_memos: list[str] = []
    sample_card_names: list[str] = []


class Classification(BaseModel):
    cost_type: CostType
    category: str
    confidence: Confidence


class VendorSummary(BaseModel):
    vendor: str
    category: str
    cost_type: CostType
    cost_type_source: CostTypeSource
    cadence: Cadence
    monthly_spend: float
    growth_pct: float | None = None


class Period(BaseModel):
    """What a report is about. `first_run` spans all the history read on the first run; `month`
    is the calendar month that closed (or is in progress). Distinct from the baseline window,
    which is the fitting range and lives in `Findings.window_start/end`."""

    kind: Literal["first_run", "month"]
    label: str = Field(description='"Sep 2025 – Aug 2026" or "September 2026"')
    start: date
    end: date


class InflowItem(BaseModel):
    id: str
    date: date
    amount: float
    counterparty: str
    kind: InflowKind | Literal["unclassified"] = "unclassified"
    counted: bool = Field(description="Counted as cash in (customer or unclassified); funding, refunds and transfers are not")


class CashPosition(BaseModel):
    """What the bank can say without asking: runway from total cash and net burn, and what the
    operating balance allows. All arithmetic, assumptions stated. Inflows are cash receipts, not
    revenue: a large unclassified one is asked about (`inflow_ask`), and the answer changes net burn."""

    as_of: date
    operating_balance: float
    treasury_balance: float
    total_cash: float
    monthly_inflows: float = Field(description="Average settled inflows over the 3 complete months before the evaluated month")
    net_burn_monthly: float = Field(description="Trailing monthly spend minus monthly inflows, floored at 0")
    runway_months: float | None
    operating_months_of_burn: float | None
    buffer_months: float
    recommended_operating: float = Field(description="buffer_months × net burn")
    sweep_to_treasury: float = Field(description="Operating balance above the buffer, 0 if none")
    shortfall_from_treasury: float = Field(description="Top-up needed to reach the buffer, 0 if none")
    treasury_apy: float
    treasury_upside_monthly: float = Field(description="sweep × APY / 12")
    inflows: list[InflowItem] = Field(default=[], description="Settled inflows in the averaging window")
    inflow_ask: list[InflowItem] = Field(default=[], description="Unclassified inflows large enough to ask about")


class Findings(BaseModel):
    stage: Stage
    window_start: date = Field(description="Start of the baseline (fitting) window, not the reporting period")
    window_end: date
    period: Period | None = None
    cash: CashPosition | None = None
    transaction_count: int | None = Field(default=None, description="Settled spend rows read, through window_end")
    recurring_vendor_count: int | None = Field(
        default=None, description="Recurring vendors whose spend reached the report floor in some month (the ones the reports talk about)"
    )
    data_start: date | None = Field(default=None, description="Earliest transaction date in the data")
    trailing_monthly_spend: float
    last_monthly_spend: float | None = Field(default=None, description="Total spend in the last full month")
    prior_monthly_spend: float | None = Field(
        default=None, description="Total spend in the month before the last full month, for the report intro"
    )
    headcount_proxy: int = Field(description="Distinct cardholders in the window")
    findings: list[Finding]
    vendors: list[VendorSummary]
    category_totals: dict[str, float]


class NarrateRequest(BaseModel):
    findings: Findings
    mode: Literal["alerts", "report"]
    open_issues: list[OpenIssue] = Field(
        default=[], description="Issues already alerted on; their vendors go under 'Needs attention' in reports"
    )


class AlertText(BaseModel):
    finding_id: str
    headline: str
    what_moved: str
    why: str


class ReportItemText(BaseModel):
    finding_id: str
    text: str


class ReportText(BaseModel):
    intro: str
    needs_attention: list[ReportItemText]
    worth_knowing: dict[str, list[ReportItemText]] = Field(description="Grouped by category")


class NarrateResponse(BaseModel):
    alerts: list[AlertText] = []
    report: ReportText | None = None


class AskTurn(BaseModel):
    role: Literal["user", "bot"]
    text: str


class AskRequest(BaseModel):
    """A clarifying question in the thread under one alert or report item. The answer is
    grounded in an evidence pack built server-side for that finding: its facts, the vendor's
    monthly series, and the individual charges in the evaluated and prior month."""

    stage: Stage
    finding_id: str
    question: str = Field(min_length=1, max_length=500)
    thread: list[AskTurn] = Field(default=[], description="Earlier turns in this thread, oldest first")
    config: Config | None = None
    overrides: list[Override] = []
    open_issues: list[OpenIssue] = []


class AskResponse(BaseModel):
    answer: str
    source: Literal["claude", "template"]
    evidence_used: list[str] = Field(default=[], description="Which parts of the evidence pack were available")


class TransactionsResponse(BaseModel):
    """Raw Rho-shaped rows for the records page, untouched (amounts stay signed minor units)."""

    stage: Stage
    as_of: date
    total: int = Field(description="Rows in the stage before filtering")
    matched: int = Field(description="Rows matching the filters")
    by_beat: dict[str, int] = Field(description="Rows each demo beat added: history, inject-1, inject-2")
    transactions: list[dict[str, Any]] = Field(description="Raw rows plus a `_beat` key naming the file that added each")


class AccountsResponse(BaseModel):
    stage: Stage
    as_of: date
    accounts: list[dict[str, Any]] = Field(description="Rho /accounts shape: id, name, account_type, balance{amount, currency}")
