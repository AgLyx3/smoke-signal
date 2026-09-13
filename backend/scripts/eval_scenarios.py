"""Scenario eval on the real demo data: every planted scenario in data/README.md carries a label
(should_alert / should_report / should_ignore) and this script checks the pipeline's verdict per
stage, prints the table, and exits 1 on any mismatch. Deterministic: taxonomy only, no Claude.

    cd backend && uv run python scripts/eval_scenarios.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import taxonomy  # noqa: E402
from models import DEFAULT_CONFIG, OpenIssue  # noqa: E402
from pipeline import load_stage, run_pipeline  # noqa: E402

DATA = Path(__file__).resolve().parents[1] / "data"

# (stage, vendor, kind, expected route). `ignore` means: no finding of that kind for that vendor.
SCENARIOS: list[tuple[str, str, str, str]] = [
    # history, as of 2026-08-31: nothing alerts, two quiet report items
    ("history", "Loom", "stopped", "report"),
    ("history", "Notion", "per_head", "report"),
    ("history", "Anthropic", "growth_break", "ignore"),
    ("history", "Vanta", "renewal", "ignore"),  # renewal is 6 weeks out, outside the 30-day lookahead
    ("history", "Pinecone Systems", "new_vendor", "ignore"),  # only one charge so far
    # inject-1, as of 2026-09-05: the two alerts, plus price creep
    ("inject-1", "Anthropic", "growth_break", "alert"),
    ("inject-1", "Pinecone Systems", "new_vendor", "alert"),
    ("inject-1", "Figma", "price_change", "report"),
    ("inject-1", "Loom", "stopped", "report"),
    ("inject-1", "Notion", "per_head", "report"),
    ("inject-1", "OpenAI", "growth_break", "ignore"),  # on trend
    ("inject-1", "AWS", "growth_break", "ignore"),
    ("inject-1", "Gusto Payroll", "growth_break", "ignore"),  # payroll is context only
    # inject-2, as of 2026-09-30, with inject-1's alerts carried as open issues
    ("inject-2", "Anthropic", "growth_break", "report"),  # still open, not re-alerted
    ("inject-2", "Pinecone Systems", "new_vendor", "report"),
    ("inject-2", "Vanta", "renewal", "report"),
    ("inject-2", "Loom", "stopped", "report"),
    ("inject-2", "Figma", "price_change", "report"),
    ("inject-2", "Notion", "per_head", "report"),
    ("inject-2", "Airbnb", "spike", "ignore"),  # April offsite never recurs
    ("inject-2", "Carta", "renewal", "ignore"),
    ("inject-2", "Costco Whse", "stopped", "ignore"),  # unknown small vendor, under the report floor
]

# Beyond the named rows: the only findings allowed per stage. Anything else is noise.
ALLOWED = {
    "history": {("Loom", "stopped"), ("Notion", "per_head")},
    "inject-1": {("Anthropic", "growth_break"), ("Pinecone Systems", "new_vendor"), ("Figma", "price_change"),
                 ("Loom", "stopped"), ("Notion", "per_head")},
    "inject-2": {("Anthropic", "growth_break"), ("Pinecone Systems", "new_vendor"), ("Vanta", "renewal"),
                 ("Loom", "stopped"), ("Figma", "price_change"), ("Notion", "per_head")},
}


def main() -> int:
    results: dict[str, dict[tuple[str, str], str]] = {}
    open_issues: list[OpenIssue] = []
    asks: dict[str, bool] = {}
    for stage in ("history", "inject-1", "inject-2"):
        df, as_of = load_stage(stage, DATA)
        out = run_pipeline(df, as_of, DEFAULT_CONFIG, [], open_issues, taxonomy=taxonomy, stage=stage)
        results[stage] = {(f.vendor, f.kind): f.route for f in out.findings}
        asks.update({f"{stage}:{f.vendor}": f.ask_cost_type for f in out.findings if f.route == "alert"})
        if stage == "inject-1":
            open_issues = [OpenIssue(id=f.id, vendor=f.vendor, kind=f.kind, impact_monthly=f.impact_monthly)
                           for f in out.findings if f.route == "alert"]

    failures = 0
    print(f"{'stage':9} {'vendor':18} {'kind':13} {'expected':9} {'got':9} verdict")
    for stage, vendor, kind, expected in SCENARIOS:
        got = results[stage].get((vendor, kind), "ignore")
        ok = got == expected
        failures += not ok
        print(f"{stage:9} {vendor:18} {kind:13} {expected:9} {got:9} {'PASS' if ok else 'FAIL'}")

    for stage, allowed in ALLOWED.items():
        extra = set(results[stage]) - allowed
        for vendor, kind in sorted(extra):
            failures += 1
            print(f"{stage:9} {vendor:18} {kind:13} {'ignore':9} {results[stage][(vendor, kind)]:9} FAIL (unplanned)")

    ask = asks.get("inject-1:Pinecone Systems")
    print(f"{'inject-1':9} {'Pinecone Systems':18} {'ask_cost_type':13} {'True':9} {str(ask):9} {'PASS' if ask else 'FAIL'}")
    failures += not ask
    ask_anthropic = asks.get("inject-1:Anthropic")
    print(f"{'inject-1':9} {'Anthropic':18} {'ask_cost_type':13} {'False':9} {str(ask_anthropic):9} {'PASS' if ask_anthropic is False else 'FAIL'}")
    failures += ask_anthropic is not False

    print(f"\n{len(SCENARIOS) + 2} checks, {failures} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
