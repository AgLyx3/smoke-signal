# Cost Signals — Design

Status: draft, 2026-09-12. Source PRD: "Cost Signal Layer for Rho — PRD & Implementation Plan"
(https://claude.ai/code/artifact/b89551bd-2396-41fa-af60-1b7d197aee1e). This doc narrows the PRD
to a demo build and records what changed.

## 1. Understanding summary

- **What:** a cost-signal layer for Rho. It learns each vendor's normal spend trajectory from
  transaction history, detects meaningful changes, classifies vendors by cost type, and explains
  each change. Runs on synthetic data in Rho's API schema.
- **Why:** founders see every transaction but not what changed or why. The argument is judgment
  quality and restraint: detect and route, never recommend savings.
- **Who:** VC-backed startups from seed through Series B, including scale-ups (hiring waves,
  growing vendor count, several teams). The demo company is a Series A scale-up.
- **Demo flow:** load history → report over history; new charges arrive → alerts; month closes →
  monthly report. Thresholds are editable on a settings page.
- **Non-goals:** savings or model-switch recommendations (permanent), spend controls, runway
  math in the build, real Slack, email, recipient routing, provider API-key unlock, mute learning,
  a database, auth.

## 2. Assumptions

| # | Assumption | Status |
|---|---|---|
| A1 | Rho transactions carry no MCC or category; merchant is `counterparty_name` only; `memo` is optional | Verified (`rho-api.md`, sandbox) |
| A2 | Usage APIs at Series A scale bill monthly on card/ACH, so surges arrive as invoices | Unverified; reasonable |
| A3 | Headcount ≈ distinct cardholders (`user_id`) in the window | Proxy, stated in the UI |
| A4 | Claude model `claude-sonnet-5` for classification and narration | Default |
| A5 | Next.js + FastAPI in one Vercel project works via **Vercel Services** (`frontend/` + `backend/`, `vercel.json` `services` + rewrites). Python 3.12 default; `pyproject.toml` + uv supported; 500 MB uncompressed limit; median Python cold start ~1.3 s; Fluid compute pre-warms production only; max duration 300 s (Hobby). Services' beta status is inconsistent across Vercel docs | Verified from Vercel docs 2026-09-12, not yet exercised. pandas+numpy size and cold start unmeasured. Deploy once early to confirm |
| A6 | Performance: each demo step completes in < ~10 s including live Claude calls | Target |
| A7 | Scale: one company, ~6 months, low thousands of transactions | Demo |
| A8 | Security: synthetic data only; `ANTHROPIC_API_KEY` server-side only | Rule |
| A9 | Reliability: live Claude calls first; add a cached fallback only if rehearsal shows failures | Decided |
| A10 | Ownership: single owner; demo code, but stack and boundaries chosen for production use | Decided |

## 3. Decision log

| Decision | Alternatives | Why |
|---|---|---|
| Demo build plan | Plan for Rho eng; both | < 24 h; the demo tests PRD open question #2 (non-obvious insight) |
| No runway in the build | Minimal runway calc | Time. Runway stays in the pitch as Rho's structural advantage |
| No first-run feature | Dedicated first-run message | The report pipeline over history already covers it |
| Two-gate alert rule, per cost type, configurable | Global $1K + 2%; $ floor only; runway filter | Per-vendor unusualness is automatic; materiality is a share of monthly spend so it scales seed → Series B |
| No item cap in reports | Top 3 | The materiality rule sets length; grouping keeps it scannable |
| Web page mimicking Slack + separate `/settings` page | Real Slack bot | Setup risk on demo day |
| Bot label "Cost Signals" | "Rho · Cost Signals (concept)" | User choice |
| Live Claude calls, fallback only if needed | Cached first; no LLM | User choice; keeps the live AI story |
| Vendor tags live; prepaid detection static (annotated) | Both live; both static | Tags are core; saves 2–3 h |
| Synthetic data in Rho schema | + live sandbox; source-agnostic | Sandbox has 8 card rows, too thin for baselines |
| Architecture C: Python (FastAPI, pandas) + Next.js | TS-only pipeline; precompute | User: choose the stack for production use. Cost: two languages, cold starts, +2–3 h |
| FastAPI in the same Vercel project via **Services** | Legacy `/api` directory (Vercel: existing projects only); community `/api/py` rewrite starter; separate host; local only | One deploy; Services is Vercel's documented path for Python + frontend (A5) |
| Demo from the production URL, warmed once beforehand | Demo from a preview URL | Previews are not pre-warmed |
| Pydantic is the contract source; TS types generated via `openapi-typescript` | Hand-written TS types | The two sides cannot drift |
| pandas + numpy only | statsmodels, Prophet | 6 monthly points per vendor; lighter cold start |
| State in `localStorage`; Postgres specified in §9, not built | Postgres now | Keeps the build lean |
| Worktree per feature | One branch | Parallel streams |
| 12 months of history, not 6 | 6 months | So an annual renewal (Vanta, Oct) falls inside the demo window; the generator cost is nil |
| Pinecone $2.5K → $6.5K (not $1.0K → $2.4K) | PRD's $2.4K example | At $500K/mo spend, $2.4K is 0.5%, below the 1% materiality bar; the demo needs it to alert |
| No prepaid purchases in the synthetic data | Include a $50K credit purchase | Prepaid detection is static in this build; a round prepaid charge would make the live pipeline false-alert |
| Cardholders 34 → 42, tracking headcount 38 → 46 | 15 cardholders | The headcount proxy (A3) is only honest if most employees hold cards |
| Parallel feature agents do not edit `FEATURES.json` / `PROGRESS.md`; the integrator records their evidence | Each agent edits the scoreboard | Four branches editing one JSON array conflict on every merge |

## 4. Architecture

```
frontend/  Next.js (App Router, TS)          backend/  FastAPI (Python 3.12), service "api"
  /           Slack look-alike + presenter bar     POST /api/run      {stage, config, overrides} -> Findings
  /settings   thresholds, vendor overrides         POST /api/narrate  {findings} -> texts   (Claude)
  localStorage: stage, config, overrides           pipeline/  pure functions over pandas
                                                   data/      seeded generator -> history, inject-1, inject-2
vercel.json: services {web: frontend/, api: backend/ main:app}; rewrite /api/(.*) -> api, /(.*) -> web
```

- Vercel does not strip the prefix: FastAPI routes are declared with the full `/api/...` path.
- Local dev: `vercel dev` runs both services.

- `run` executes the pipeline for the requested stage. Unknown vendors are classified by one
  batched Claude call; the taxonomy and user overrides take precedence.
- `narrate` turns `Findings` (facts and numbers only) into alert and report text. Claude never
  decides what fires.
- Pydantic models define `Findings`, `Config`, `Override`; `openapi-typescript` generates the
  front-end types from FastAPI's OpenAPI.

## 5. Data and scenarios

- **Company:** Lumen Labs, Series A AI company. Headcount 38 → 46 (hiring wave in June 2026),
  ~$500K/mo spend (~65% payroll), ~40 vendors, cardholders 34 → 42 (most employees hold a Rho
  card, so the headcount proxy tracks headcount), 3 teams. Operating checking + Rho credit.
- **History (12 months, 2025-09-01 → 2026-08-31;** 12 rather than 6 so an annual renewal falls
  inside the demo window): semi-monthly Gusto payroll ACH stepping up with the hiring wave; usage
  vendors (Anthropic, OpenAI, AWS, Modal) on smooth growth; fixed SaaS; seat-based tools that
  grow with headcount; annual contracts; employee card spend; one offsite spike that reverts;
  descriptor variants ("ANTHROPIC* API" / "Anthropic PBC"); excluded money movement
  (repayments, internal transfers, treasury). Pinecone's first invoice lands in the last month.
- **Inject 1 (alerts, 2026-09-01 → 09-05):** Anthropic's monthly invoice ~60% above its
  ~15%/mo trend (Aug ≈ $22K, so the impact ≈ $10K ≈ 2% of spend); Pinecone's second invoice
  ($2.5K → $6.5K, ≈ 1.3% of spend) confirms recurrence and triggers the ask. No prepaid credit
  purchases anywhere in the data: prepaid handling is shown statically, and a round prepaid
  charge in the data would make the live pipeline false-alert.
- **Stage semantics:** `history` = history.json, as of 2026-08-31; `inject-1` = history +
  inject-1.json, as of 2026-09-05; `inject-2` = all three files, as of 2026-09-30. Each file is a
  Rho-style envelope `{"transactions": [...]}`.
- **Inject 2 (monthly report):** rest of the month. Both issues show as ongoing, not re-alerted;
  plus Figma price creep, a seat tool growing faster than headcount, a stopped vendor, an
  upcoming renewal.
- Generated by a seeded script; outputs are committed JSON so every run is identical.

## 6. Detection logic

1. **Filter:** spend = `card_debit`, `ach_debit`, `wire_out`, `international_wire_out`,
   `check_payment`, fees. Offsets (`card_refund`, `card_credit`, `ach_return`) net against the
   vendor. Money movement, rewards, treasury, repayments excluded. Only `settled` counts.
2. **Merchant resolution:** normalise `counterparty_name` (case, `*`, legal suffixes), then an
   alias table.
3. **Series and cadence:** group by vendor; median gap → monthly / annual / irregular; recurring
   = ≥ 2 charges at a regular interval.
4. **Baseline** per cost type: usage-scaling → log-linear trend (growth rate) over trailing
   months; fixed → last price; headcount-scaling → cost per head.
5. **Gate 1, unusual:** usage → log residual ≥ 2σ of the vendor's own residuals; fixed → price
   change > 1%; new → second regular charge; stopped → overdue by cadence + grace;
   headcount → cost per head above its own range.
6. **Gate 2, material:** monthly impact (actual − expected) ≥ `config[type].alert_pct` × trailing
   monthly spend.

   | Cost type | Alert default | Otherwise |
   |---|---|---|
   | Usage-scaling | 1% of monthly spend | Report |
   | Fixed | 1% | Report; price creep always listed |
   | Headcount-scaling | 1% | Report |
   | Annual / one-off | Never alerts; renewal notice | Report |
   | Payroll | Context only | Report |

7. **Route:** gate 1 + gate 2 → alert; gate 1 only → report "Worth knowing"; else ignore. An open
   issue re-alerts only on material escalation.
8. **Explanation facts:** driver (price / volume / new / missing / who), contribution split,
   confidence High / Med / Low from observation count and volatility.
9. **Ask when it matters:** the first time an unconfirmed vendor is about to appear in an alert,
   the card asks its cost type. The answer re-runs detection with the override.

## 7. UI

- `/`: Slack look-alike, channel `#spend-signals`, bot "Cost Signals". Presenter bar: *Load
  history*, *New charges*, *Month closes*.
- **Alert card:** headline ($/mo impact, share of spend) → what moved → why (driver,
  confidence) → cost-type tag marked "inferred" → inline question when applicable → reactions
  (expected / investigating / not useful).
- **Report:** "Needs attention" first, then "Worth knowing" grouped by category, each sorted by
  $ impact. No cap.
- `/settings`: per-type threshold table, vendor classification overrides, *Reset demo*. Save
  returns to `/` and re-runs.

## 8. Evaluation

**Proposed — pending confirmation.**

- `pytest` harness over labelled fixture scenarios, each a small Rho-schema transaction set with
  expected outcomes per (vendor, kind): `should_alert` / `should_digest` / `should_ignore`.
- Scenarios: growth-rate jump (alert); steady growth on trend (ignore); new vendor, material
  (alert + ask); new vendor, small (digest); fixed price creep (digest); vendor stopped (digest);
  one-off spike that reverts (ignore); hiring step change with flat cost per head (ignore); cost
  per head rising (digest or alert by size); two unrelated problems in one run (two alerts); same
  problem next run (no re-alert); annual renewal (notice, no alert).
- Classification in the harness is taxonomy-only, so it is pure, free, and mutation-testable.
  Exits 1 on any mismatch and on missing or empty fixtures.
- `check-auditor` proves it bites (e.g. dropping the trajectory term must fail "steady growth").
- Opt-in `eval:live` (costs money, asks first): Claude classification run 5× on unknown vendors,
  reporting agreement rate (variance, per PRD §7.1).
- Future shape, presented not built: backtest with persistence labels, recall on top-N moves,
  blind panel rubric, online reaction signals, calibration of impact estimates.

## 9. Production shape (specified, not built)

- A scheduled batch job per customer (daily) over the transaction store, not on-demand runs.
- Postgres tables: `vendor_overrides`, `thresholds`, `open_issues` (natural key vendor + kind,
  for dedupe and escalation), `alerts` (with the predicted impact, for calibration), `reactions`.
- Idempotent under rerun: the same window produces no new alerts.
- Multi-tenant: one job per business grant; Rho API rate limits (~60 req/min per token) handled by
  incremental `initiated_after` windows.
- Delivery through Rho's own Slack app, which today is Owner/Admin-only.

## 10. Implementation plan

Phase 0 on its own worktree, then parallel worktrees.

| # | Worktree | Work | Depends on | Est. |
|---|---|---|---|---|
| 0 | `scaffold` | `frontend/` + `backend/` skeleton, `vercel.json` Services, Pydantic contract, TS type generation; one early deploy (with permission) to exercise A5, incl. pandas import cold start | Build approval | 1.5 h |
| 1 | `data` | Seeded generator, `history` / `inject-1` / `inject-2` JSON | 0 | 2 h |
| 2 | `pipeline` | Filter → resolve → series → classify (taxonomy) → baseline → gates → route; unit tests | 0 | 4 h |
| 3 | `ui` | Slack page, alert card, report, presenter bar, `/settings`, against mock `Findings` | 0 | 4 h |
| 4 | `llm` | Claude classification of unknowns + narration route and prompts | 0 | 2 h |
| 5 | `eval` | Fixture scenarios + harness + check-auditor pass | 2 | 1.5 h |
| 6 | `integrate` | Wire UI to API, deploy preview, rehearse the three steps | 1–4 | 2 h |

About 17 h of work; 1–4 run in parallel after 0. **Cut order if behind:** eval scenarios 12 → 6;
`/settings` re-run → read-only table; report grouping → flat list. The two live scenarios and
the ask-when-it-matters card are not cut.
