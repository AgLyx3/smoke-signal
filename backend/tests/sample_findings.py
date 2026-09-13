"""A realistic `Findings` for tests and the smoke script: Lumen Labs, inject-1 shape."""

from datetime import date

from models import Baseline, DriverShare, Finding, Findings, VendorSummary

SPEND = 500_000.0


def sample_findings() -> Findings:
    findings = [
        Finding(
            id="anthropic-growth_break",
            vendor="Anthropic",
            category="AI & inference",
            cost_type="usage",
            cost_type_source="taxonomy",
            kind="growth_break",
            route="alert",
            actual_monthly=26_500.0,
            impact_monthly=10_000.0,
            impact_pct_of_spend=10_000 / SPEND,
            baseline=Baseline(n_obs=6, expected_monthly=16_500.0, growth_pct=0.15, sigma=0.08),
            drivers=[DriverShare(driver="volume", share=1.0)],
            confidence="high",
        ),
        Finding(
            id="pinecone-new_vendor",
            vendor="Pinecone",
            category="Data & tooling",
            cost_type="usage",
            cost_type_source="llm",
            kind="new_vendor",
            route="alert",
            actual_monthly=6_500.0,
            impact_monthly=6_500.0,
            impact_pct_of_spend=6_500 / SPEND,
            baseline=Baseline(n_obs=2, expected_monthly=0.0),
            drivers=[DriverShare(driver="new", share=1.0)],
            confidence="low",
            ask_cost_type=True,
        ),
        Finding(
            id="figma-price_change",
            vendor="Figma",
            category="Software",
            cost_type="fixed",
            cost_type_source="taxonomy",
            kind="price_change",
            route="report",
            actual_monthly=1_875.0,
            impact_monthly=375.0,
            impact_pct_of_spend=375 / SPEND,
            baseline=Baseline(n_obs=6, expected_monthly=1_500.0, last_price=1_500.0),
            drivers=[DriverShare(driver="price", share=1.0)],
            confidence="high",
        ),
        Finding(
            id="loom-stopped",
            vendor="Loom",
            category="Software",
            cost_type="fixed",
            cost_type_source="taxonomy",
            kind="stopped",
            route="report",
            actual_monthly=0.0,
            impact_monthly=-480.0,
            impact_pct_of_spend=-480 / SPEND,
            baseline=Baseline(n_obs=5, expected_monthly=480.0, last_price=480.0),
            drivers=[DriverShare(driver="missing", share=1.0)],
            confidence="medium",
        ),
        Finding(
            id="vanta-renewal",
            vendor="Vanta",
            category="Software",
            cost_type="annual",
            cost_type_source="taxonomy",
            kind="renewal",
            route="report",
            actual_monthly=0.0,
            impact_monthly=0.0,
            impact_pct_of_spend=0.0,
            baseline=Baseline(n_obs=1, expected_monthly=1_500.0, last_price=18_000.0),
            drivers=[],
            confidence="medium",
        ),
    ]
    vendors = [
        VendorSummary(
            vendor=f.vendor,
            category=f.category,
            cost_type=f.cost_type,
            cost_type_source=f.cost_type_source,
            cadence="annual" if f.kind == "renewal" else "monthly",
            monthly_spend=f.actual_monthly,
            growth_pct=f.baseline.growth_pct,
        )
        for f in findings
    ]
    return Findings(
        stage="inject-1",
        window_start=date(2026, 3, 1),
        window_end=date(2026, 8, 31),
        trailing_monthly_spend=SPEND,
        last_monthly_spend=SPEND,
        prior_monthly_spend=482_000.0,
        headcount_proxy=46,
        findings=findings,
        vendors=vendors,
        category_totals={"AI & inference": 88_000.0, "Data & tooling": 9_500.0, "Software": 41_200.0},
    )
