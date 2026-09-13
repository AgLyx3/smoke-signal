"""API contract. Pydantic is the source of truth; frontend types are generated from
FastAPI's OpenAPI (see `npm run types` in frontend/). Change here first, then regenerate."""

from datetime import date
from typing import Literal

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


class RunRequest(BaseModel):
    stage: Stage
    config: Config | None = None
    overrides: list[Override] = []
    open_issues: list[OpenIssue] = []


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


class Findings(BaseModel):
    stage: Stage
    window_start: date = Field(description="Start of the baseline (fitting) window, not the reporting period")
    window_end: date
    period: Period | None = None
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
