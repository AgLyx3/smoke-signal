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
- **Accounts (added 2026-09-13):** `accounts.json` holds one balance snapshot per stage in Rho's
  `/accounts` shape: Operating Checking ($2.35M → $1.905M), Rho Treasury (investment, $7.40M →
  $7.42M) and the card balance (not cash). Only the bank can compute runway without asking the
  founder anything; this is where that claim is demonstrated.
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
3. **Series and cadence:** group by vendor; median gap → semi-monthly / monthly / annual /
   irregular; recurring = ≥ 2 charges at a regular interval, or present in ≥ 3 distinct months.
   Unknown vendors keep their normalised descriptor, title-cased, as the key.
4. **Baseline** per cost type, using only months strictly before the evaluated month (the month
   containing `as_of`; complete iff `as_of` is its last day), window = 6 prior months, months with
   no spend skipped: usage-scaling → log-linear trend over ≥ 3 observations, `growth_pct =
   exp(slope) − 1`, σ = RMS of log residuals floored at 0.08; fixed → last price, only when ≥ 2
   identical monthly totals exist; headcount-scaling → cost per head over ≥ 3 months, headcount
   proxy = distinct cardholders with a settled card charge in the month (a partial month uses the
   last complete month's).
5. **Gate 1, unusual:** usage → upward log residual ≥ 2σ (partial months: only monthly-cadence
   vendors whose charge has already posted); fixed → price change > 1%; new → the second regular
   charge lands, first charge inside the window; stopped → overdue by median gap + 5 days grace,
   visible for 2 cycles; headcount → cost per head above mean + max(2σ, 5%) with ≥ 4 observations,
   else +15%; renewal → annual vendor whose anniversary is within 30 days after `as_of`; spike →
   non-recurring vendor above its type's materiality this month.
6. **Gate 2, material:** monthly impact (actual − expected; `new_vendor` expected = 0; `stopped`
   impact = −expected) ≥ `config[type].alert_pct` × trailing monthly spend, where trailing = mean
   of the last 3 complete months before the evaluated month (so inject-1 and inject-2 share a bar).
   `stopped`, `renewal` and `spike` never alert. Below the alert bar, a change must still clear
   `config.report_floor_pct` (default 0.25% of monthly spend, ≈ $1.2K at Lumen Labs; 0.1% let
   $600 office-supply "trend breaks" through once Claude classified them) to appear in the report, except price
   changes, per-head rises and renewals on vendors whose cost type is confirmed or classified,
   which are always listed. Fees and payroll are context only, never findings.

   | Cost type | Alert default | Otherwise |
   |---|---|---|
   | Usage-scaling | 1% of monthly spend | Report |
   | Fixed | 1% | Report; price creep always listed |
   | Headcount-scaling | 1% | Report |
   | Annual / one-off | Never alerts; renewal notice | Report |
   | Payroll | Context only | Report |

7. **Route:** gate 1 + gate 2 → alert; gate 1 only → report "Worth knowing"; else ignore. An open
   issue (same vendor + kind, matched by `issueKey`, not by the dated finding id) re-alerts only
   when |impact| grew by ≥ 50% and by at least the materiality bar again; otherwise it stays a
   report line marked ongoing.
8. **Explanation facts:** driver (price / volume / new / missing / who), contribution split
   (volume = charge-count component, price = mean-charge component, `who` when one cardholder
   carries ≥ 60% of the increase), confidence High (≥ 6 obs, σ ≤ 0.15) / Med (≥ 3) / Low.
9. **Classification precedence:** user override > taxonomy > Claude hook > default (`fixed`,
   "Software", source `default`). The hook sees only unknown recurring vendors whose spend has
   reached the report floor in some month (classification, like the ask, happens when a vendor
   starts to matter, and it keeps one batch inside the request timeout: 26 small merchants in one
   call took > 20 s on Vercel), is called once per batch, caches per process, and returns `{}` on
   any failure so the vendor stays `default`.
10. **Ask when it matters:** an alert on a vendor whose source is not `taxonomy` or `user` carries
    the cost-type question. The answer re-runs detection with the override; narration text is not
    re-requested (facts and chips update, prose stays).
11. **Claude settings:** `claude-sonnet-5`, tool-schema structured output **without `strict`**
    (strict decoding made latency scale with batch size: 4 vendors 3.9 s, 5 → 10.8 s, 10 → 20 s,
    the same 10 non-strict 4.4 s; Pydantic validates every entry instead), 20 s timeout, no
    retries; the SDK's `messages.create` exposes no `temperature`, so determinism rests on the
    schema, the prompt and the grounding check.
12. **Thread questions (added 2026-09-13).** Every alert card and report item has a Slack-style
    thread. A question goes to `POST /api/ask {stage, finding_id, question, thread[], config,
    overrides, open_issues}` and is answered from an **evidence pack** built server-side for that
    finding only (`pipeline/evidence.py`): the card's facts, the vendor's last 8 monthly totals
    and charge counts, the individual charges in the evaluated and prior month (date, amount,
    cardholder, card name, memo, raw descriptor; largest 40), cardholder totals for the month, the
    thresholds in force, and an explicit list of what is not visible (per-model usage, invoice
    lines, plan or seat count, other vendors). Claude answers with the card rules plus three of
    its own: answer only from the pack, say what is not visible instead of guessing, and redirect
    general spend questions to `@Rho` in one sentence. The reply goes through the same grounding
    check as the cards (every number in the pack may be quoted); an ungrounded reply is
    regenerated once, then a deterministic template answers from the pack. One call per
    question, 2–4 s; `X-Narration` reports `claude` or `template`. Threads persist per finding in
    `localStorage`; cardholder names are allowed in answers (synthetic data here; in production
    the thread lives in Rho's Owner/Admin-only Slack surface).
13. **Cash position and runway (added 2026-09-13, the CFO seat).** From Rho's own accounts, no
    input from the founder: inflows = average settled credits (`ach_credit`, `wire_in`,
    `check_deposit`) over the three complete months before the evaluated month, the same window
    as trailing spend; net burn = trailing spend − inflows; runway = (operating + treasury) ÷ net
    burn; buffer = `buffer_months` (3) × net burn; idle cash = operating − buffer; treasury upside
    = idle × APY (3.8%, stated assumption) ÷ 12; a shortfall is the top-up needed from treasury.
    Every finding except renewals and spikes gets `runway_weeks_delta` = weeks of runway lost (or
    gained) if its monthly change persists. All arithmetic, no LLM.
    **Fatigue rules** (user, 2026-09-13: "these will create fatigue so they can't be on
    everything"): runway appears on an alert only when the framing toggle is on **and** the delta
    is ≥ 1 week, never on report lines; the treasury paragraph appears on the first look
    (orientation) and afterwards only on news — a buffer shortfall, or idle cash ≥ 2 months of
    net burn — otherwise a monthly report carries a one-line runway status. Delivery follows the
    Settings choice (founder DM by default) and is shown as a label on the demo cards.
    **Cash in is not revenue.** A `wire_in` from an investor and one from a customer look the
    same in the transaction type, so an unclassified inflow ≥ 5% of monthly spend gets one
    question in the cash message ("We're counting the $200,000 from Globex Industries on Jul 15
    as cash in, a customer payment. Right?" — customer / funding / refund or transfer). Only
    customer payments (and unanswered ones) count toward cash in; the answer is stored by
    transaction id, re-runs net burn and runway, and is never re-asked. Recognised revenue would
    need Rho's invoicing endpoints on top.
    **Delivery (user, 2026-09-13: "the DM is with the Cost Signals bot").** With "Direct message
    to the founder" (the default), runway detail leaves the channel entirely: alert cards stay
    dollars-only with a one-line "Runway impact sent by direct message to Dana K.", reports carry
    no cash section, and the **Cost Signals app DM** (Apps → Cost Signals, unread badge) carries
    the cash position and one line per material alert ("≈ 2.3 weeks of runway · Anthropic · Off
    its trend · +$9.6K/mo"). With "the channel", everything appears inline. DM messages are
    derived from the loaded stages, not stored twice.

## 7. UI

- `/`: Slack look-alike, channel `#spend-signals`, bot "Cost Signals". Presenter bar: *Load
  history*, *New charges*, *Month closes*, links to *Records* and *Settings*.
- `/transaction-records` (added 2026-09-13, bare on purpose): the raw rows the pipeline reads, in
  Rho's `/transactions` shape, plus the `/accounts` balance strip for the same beat. It follows
  the presenter: the beat defaults to whatever the channel has loaded, every row carries the beat
  that added it (`_beat`: history / inject-1 / inject-2), rows added by the current beat are
  highlighted, and "Only what this beat added" shows the delta (2,484 / 51 / 181 rows). Filters:
  account (click a balance), type, free text over counterparty, memo, cardholder, card, id; 100
  rows a page, newest first; a click opens the raw JSON with signed minor units untouched.
  Served by `GET /api/transactions` and `GET /api/accounts`.
- **Alert card:** headline ($/mo impact, share of spend) → what moved → why (driver,
  confidence) → cost-type tag marked "inferred" → inline question when applicable → reactions
  (expected / investigating / not useful).
- **Report:** "Needs attention" first, then "Worth knowing" grouped by category, each sorted by
  $ impact. No cap.
- **Thread panel:** *Reply in thread* on every alert card (shows the reply count once there is
  one) and a *Reply* link on every report item open a right-hand panel: the finding's summary, the
  conversation, four suggested questions as chips ("Show me the charges", "Which cardholders?",
  "Why now and not last month?" / "Why isn't this an alert?", "What don't you know here?"), and a
  composer. Bot turns carry a source marker ("via Claude, grounded in this vendor's data" or
  "template answer").
- **Runway and cash (Settings → Runway framing on):** alert headline gains "≈ 2.2 weeks of
  runway" with "If this rate holds. Runway detail → DM to Dana K."; reports gain the cash card
  (runway months, total cash = operating + treasury, net burn = spend − inflows, what the
  operating balance above the buffer could earn in Rho Treasury) on the first look and on news,
  else a one-line runway status. Buffer months and APY are editable next to the toggle. With the
  default "DM to the founder", all of that appears in the **Cost Signals direct message**
  (sidebar → Apps → Cost Signals, with an unread count) and the channel shows only a one-line
  pointer on each affected alert. The cash message also carries the cash-in question for any
  large unclassified inflow.
- `/settings`: per-type threshold table, vendor classification overrides, *Reset demo*. Save
  returns to `/` and re-runs.
- `/settings` → **Connections** (added 2026-09-13; the PRD's progressive-disclosure ladder made
  visible): two opt-ins, each stating the capability it unlocks. *Provider usage keys*: a
  read-only Anthropic or OpenAI admin key, per vendor, unlocking a per-model / per-key breakdown
  in that vendor's alerts; only the masked tail (`••••1234`) is ever stored, never the key.
  *Runway framing*: a toggle to state alerts in weeks of runway, with its own destination
  (direct message to a named founder by default, or the channel) because runway is owner-level
  information. Both persist immediately and clear on Reset. **Not wired** into detection or
  narration in this build: alerts keep their current wording; the destination choice is
  recorded, not acted on.

## 8. Evaluation

**Proposed — pending confirmation.**

- Two layers, both built: `tests/test_pipeline.py` (compact Rho-shaped fixtures, one property per
  test, mutation-checked) and `scripts/eval_scenarios.py`, which runs the real Lumen Labs data
  through all three stages and checks every planted scenario against its label
  (`alert` / `report` / `ignore`) plus an allow-list per stage so unplanned findings fail the run.
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
