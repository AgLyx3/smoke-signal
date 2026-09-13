# Smoke Signal

*Instead of "a charge crossed $1,000," it tells you when a charge is unusual for that vendor, material to your runway, and why. Before you ask.*

**Smoke Signal** is a demo of a cost-signal layer for Rho. It learns each vendor's normal spend trajectory from transaction history, detects meaningful changes with deterministic statistics, classifies vendors by cost type (usage-scaling, fixed, headcount-scaling, annual, payroll), and explains each change in plain language. An alert fires only when a change is both unusual for that vendor and material relative to monthly spend, so the same rules work from seed through scale up. Claude classifies unknown vendors and writes the explanations; in this build it does not decide what fires.

Smoke Signal also reads cash position from Rho's own accounts and turns it into runway. Each material alert carries the weeks of runway it costs if the new rate holds, and the monthly report includes a cash card with runway, net burn, and idle balance. Runway is owner-level information, so by default it goes to the founder by direct message rather than the channel. Thresholds, vendor classification and the runway framing are all admin settings.

The trend detection is purely statistical over a few monthly points, so false positives are the main risk, and the first three V2 items below are the work that would reduce them.

It runs on synthetic data shaped like Rho's API schema for a fictional Series A company, Lumen Labs. The output is a web page that mimics Slack: alert cards as new charges arrive, a monthly report when the month closes, threadable follow-up questions on every finding, a transaction records view, and the settings page.

## Tech stack

**Frontend (demo only):** Next.js 16 App Router, React 19, TypeScript, Tailwind 4. State in localStorage. Types generated from the backend's OpenAPI with openapi-typescript.

**Backend:** FastAPI on Python 3.12, pandas, numpy, Pydantic, managed with uv. Anthropic SDK with claude-sonnet-5 for vendor classification, narration, and thread answers. Synthetic data from a seeded generator, committed as JSON.

**Hosting:** one Vercel project with two Vercel Services, `web` for Next.js and `api` for FastAPI, joined by rewrites.

**Testing:** pytest, Playwright, and a scenario evaluation script.

**In production:** the FastAPI pipeline and the Anthropic integration carry over unchanged. Around them, Slack Bolt for Python, Postgres via Neon or Supabase on the Vercel Marketplace, and Vercel Cron for the batch job.

## Features

What it takes to run this as an alert layer inside Rho, in build order. The demo at https://smoke-signal-app.vercel.app implements the detection, classification, narration, thread and runway logic against synthetic data; bullets marked *new* are the pieces the demo stands in for. Its presenter bar and transaction records view exist only to show the demo and are in neither list.

### V1 — build first

Ingest

- **Daily batch per business.** Pull the transactions and accounts APIs on incremental `initiated_after` windows, one job per business grant, inside the token rate limit. Idempotent: the same window twice produces no second alert. *(New: the demo reads committed JSON and runs on demand.)*
- **Spend filter.** Card, ACH, wire, check and fee debits only, settled only. Refunds and credits net against the vendor. Money movement, treasury, repayments and rewards excluded.
- **Merchant resolution.** Descriptor normalisation plus an alias table, so "ANTHROPIC* API" and "Anthropic PBC" are one vendor; anything unresolved is an unknown vendor.

Detect

- **Cost-type classification.** Usage-scaling, fixed, headcount-scaling, annual, payroll. Precedence: admin override, taxonomy, Claude, default. Unknown recurring vendors go to Claude in one batched call, only once their spend matters; a failure leaves the vendor unclassified rather than guessing.
- **Per-vendor baselines.** Log-linear growth trend for usage vendors, last price for fixed, cost per head for seat tools (headcount proxied by distinct cardholders), fitted on the months before the evaluated one.
- **Two-gate rule.** Gate 1, unusual for that vendor: trend break at 2σ, price change, a new vendor's second charge, a stopped vendor, a per-head rise, a renewal inside 30 days, a one-off spike. Gate 2, material: monthly impact at or above a per-cost-type share of trailing monthly spend, default 1%. Below that, a report floor of 0.25%. Both percentages are per-customer settings.
- **Routing, dedupe and escalation.** Alert, report or ignore. An open issue keyed by vendor and kind re-alerts only if its impact grows by half and clears the bar again; otherwise it rides along as ongoing.
- **Explanation facts.** Driver (price, volume, new, missing, who), contribution split, confidence. Computed before any model sees them.

Explain

- **Grounded narration.** Claude writes the alert and report text from the facts, every number is checked against them, and a deterministic template takes over on failure or timeout. Detection never waits on the model.
- **Ask when it matters.** An alert on a vendor Rho has not classified carries the cost-type question inline; the answer is stored as an override and re-runs detection.
- **Follow-up questions in thread.** Each finding answers from an evidence pack built for it alone: its facts, the vendor's monthly series, the individual charges, cardholder totals, the thresholds in force, and an explicit list of what is not visible. Out-of-scope questions are declined, not guessed.

The Rho-only part

- **Cash position and runway.** From the operating and treasury balances and the settled credits: cash in, net burn, runway, a buffer, and idle cash with its yield. Producing it asks the founder for nothing, no budget and no plan. The one exception is a large unclassified inflow, where an investor wire and a customer wire are indistinguishable, so it asks once and remembers the answer.
- **Runway on alerts, rationed.** Weeks of runway lost per material alert, only when the delta is at least a week. The treasury paragraph appears on the first run and afterwards only on news. Everything else gets a one-line status.

Deliver and control

- **Slack delivery.** Rho's own Slack app, Owner and Admin only today, or a Bolt app: Block Kit alert cards, the monthly report, threads on the Events API, and a founder DM for anything runway-level. *(New: the demo is a web page that mimics Slack.)*
- **Persistence.** Postgres for vendor overrides, thresholds, open issues, alerts with their predicted impact, and reactions. The predicted impact is what makes calibration possible later. *(New: the demo keeps state in localStorage.)*
- **Admin settings.** Thresholds per cost type with dollar equivalents, vendor reassignment, the runway toggle and its destination, buffer months and assumed yield. In Slack, a Home tab modal.
- **Reactions.** Expected, investigating, not useful on every card. They cost nothing to collect and are the training signal three V2 items depend on.

Proof

- **Scenario suite and mutation checks.** Every detection rule carries a test that has been watched to fail, and a labelled suite runs the whole pipeline against known cases, each one marked alert, report or ignore. Thresholds get tuned constantly; the labels are what stop a tuning change from silently deleting an alert.

### V2 — next

- **A model in the firing decision.** Today stats decide and the model explains, because a model given only a vendor's monthly totals judges materiality no better than the two gates do. The open problem is context, not capability: give it what a founder would use (what the company is doing this quarter, which vendors are load-bearing, how the last alerts were reacted to) and let it propose or suppress a firing against the deterministic baseline, with the gates as the floor and every call auditable.
- **Calibration.** Predicted against realised impact, a backtest with persistence labels, recall on the top moves. This is what turns the thresholds from a guess into a setting.
- **Better modelling.** Deceleration, just-started vendors, and business-wide shifts that should fire once rather than eight times.
- **Learned classification.** Cost types learned from admin overrides and reactions instead of a static taxonomy.
- **Mute and recipient rules.** Team leads see their own vendors; a muted vendor stays muted.
- **Provider usage keys wired in.** The opt-in read-only Anthropic or OpenAI admin key feeding a real per-model and per-key breakdown on usage alerts.
- **Recognised revenue.** Rho's invoicing endpoints, so receipts stop being the only inflow signal.

### Out of scope

- Savings or model-switch recommendations, and spend controls. Permanent non-goals: the product detects and routes, it does not tell a founder what to cut.

## Working docs

- `DESIGN.md`: assumptions, decision log, detection logic, production shape.
- `PROGRESS.md`, `FEATURES.json`, `FAILURES.md`: build state and verification.
- `CLAUDE.md`: repository rules.
