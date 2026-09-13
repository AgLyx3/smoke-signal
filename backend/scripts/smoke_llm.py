"""Manual live smoke test for the LLM layer. COSTS MONEY: up to 6 Claude calls.

Run from backend/: `uv run python scripts/smoke_llm.py`. Refuses to run without
ANTHROPIC_API_KEY. Prints only text outputs, per-call latency and grounding results."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from llm import client as llm_client  # noqa: E402
from llm.classify import classify_unknown  # noqa: E402
from llm.narrate import narrate_result  # noqa: E402
from models import VendorFacts  # noqa: E402
from sample_findings import sample_findings  # noqa: E402

SMOKE_CALL_LIMIT = 6


def main() -> int:
    if not os.environ.get(llm_client.API_KEY_ENV):
        print(f"blocked: {llm_client.API_KEY_ENV} unset")
        return 2
    # Hard stop below the module default so this script alone can never exceed the smoke budget.
    llm_client.MAX_CALLS_PER_PROCESS = SMOKE_CALL_LIMIT
    client = llm_client.get_client()

    facts = [
        VendorFacts(vendor="Pinecone", monthly_amounts={"2026-08": 2487.3, "2026-09": 6512.8}, cadence="monthly",
                    charge_count=2, sample_descriptors=["PINECONE SYSTEMS INC"], sample_memos=[],
                    sample_card_names=["Eng — API & Infra"]),
        VendorFacts(vendor="Datadog", monthly_amounts={"2026-05": 3100.0, "2026-06": 3350.0, "2026-07": 3600.0, "2026-08": 3900.0},
                    cadence="monthly", charge_count=4, sample_descriptors=["DATADOG INC"], sample_memos=["observability"]),
        VendorFacts(vendor="Twilio", monthly_amounts={"2026-05": 820.0, "2026-06": 790.0, "2026-07": 1210.0, "2026-08": 860.0},
                    cadence="monthly", charge_count=4, sample_descriptors=["TWILIO* USAGE"], sample_memos=[]),
        VendorFacts(vendor="NIMBLEWAY LTD", monthly_amounts={"2026-06": 450.0, "2026-07": 450.0, "2026-08": 450.0},
                    cadence="monthly", charge_count=3, sample_descriptors=["NIMBLEWAY LTD LONDON GB"], sample_memos=[]),
    ]

    t0 = time.perf_counter()
    classes = classify_unknown(facts, client=client)
    print(f"\n== classify ({time.perf_counter() - t0:.1f}s, calls so far {llm_client.calls_made()})")
    for v, c in classes.items():
        print(f"  {v:15s} {c.cost_type:10s} {c.category:22s} {c.confidence}")

    fs = sample_findings()
    for mode in ("alerts", "report"):
        t0 = time.perf_counter()
        before = llm_client.calls_made()
        result = narrate_result(fs, mode, client=client)
        dt = time.perf_counter() - t0
        print(f"\n== narrate {mode} ({dt:.1f}s over {result.calls} call(s), total calls {llm_client.calls_made()})")
        print(f"   source={result.source} templated={result.templated}")
        if mode == "alerts":
            for a in result.response.alerts:
                print(f"\n  [{a.finding_id}]\n  {a.headline}\n  {a.what_moved}\n  {a.why}")
        else:
            r = result.response.report
            print(f"\n  intro: {r.intro}\n  needs attention:")
            for i in r.needs_attention:
                print(f"    - [{i.finding_id}] {i.text}")
            for cat, items in r.worth_knowing.items():
                print(f"  worth knowing / {cat}:")
                for i in items:
                    print(f"    - [{i.finding_id}] {i.text}")
        assert llm_client.calls_made() - before <= 2
    print(f"\ntotal live calls: {llm_client.calls_made()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
