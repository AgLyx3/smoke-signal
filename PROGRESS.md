# Progress

Session log. Read at session start alongside `DESIGN.md`, `CLAUDE.md`, `FAILURES.md`, and
`node scripts/features.mjs`. Update at session end.

---

## 2026-09-12 — Repo setup

- Project setup: `CLAUDE.md` rules, `.claude/settings.json`, `check-auditor` and
  `features-auditor` subagents, `FEATURES.json` + `scripts/features.mjs`, `FAILURES.md` format.
- Git: `main` holds setup; every feature is built in its own worktree under
  `../rho-cost-signal-worktrees/`.
- `DESIGN.md` written and confirmed section by section (understanding, data, detection, UI,
  eval, plan). A5 (Vercel Services for Next.js + FastAPI) checked against Vercel docs, not yet
  exercised.
- Build approved. GitHub remote created: https://github.com/AgLyx3/rho-cost-signal (private),
  `main` pushed. Standing permission: push `main` after each approved merge. Vercel deploys are
  CLI-only (no Git integration), each production deploy asked for separately.

## 2026-09-12 — Scaffold (worktree `scaffold`)

- `frontend/`: Next.js 16.3.5 (App Router, TS, Tailwind v4, `src/`), `npm run types` dumps
  FastAPI's OpenAPI and generates `src/lib/api-types.ts` via `openapi-typescript`. Probe page at
  `/` calls `/api/health` and `/api/config/default` and shows latency.
- `backend/`: FastAPI 0.141 on Python 3.12 via uv (`pyproject.toml` + `uv.lock`); `models.py`
  holds the Pydantic contract (`RunRequest` → `Findings`, `NarrateRequest` → `NarrateResponse`,
  `Config`, `Override`, `OpenIssue`); `main.py` has stub routes at `/api/health`,
  `/api/config/default`, `/api/run`, `/api/narrate`. All routes carry the `/api` prefix because
  Services does not strip it.
- `vercel.json`: Services `web` (frontend/) + `api` (backend/, `main:app`), rewrites
  `/api/(.*)` → api, `/(.*)` → web.
- **A5 exercised.** `vercel dev -L` runs both services locally (after upgrading uv from 0.6.16 to
  0.12.13, Vercel's CLI requires ≥ 0.9.25). Production deploy `rho-cost-signal` → Ready in 47 s.
  https://rho-cost-signal.vercel.app: first `/api/health` 200 in 0.23 s (pandas 3.0.5 imported),
  warm ~0.10 s; page and config 200. The `*-projects.vercel.app` alias 302s to SSO (deployment
  protection); use the public alias.
- `vercel link` wrote a `.env.local` (gitignored) into the worktree; treat it like any secret
  file and delete it before removing the worktree.
- Merged to `main` (`d2a2bb8`), scaffold worktree removed (its `.env.local` deleted first).

## 2026-09-12 — Parallel feature worktrees (`data`, `pipeline`, `ui`, `llm`)

Four agents, one per worktree, all branched from `d2a2bb8`. They do not commit or edit this file
or `FEATURES.json`; the integrator reviews, re-runs their tests, records evidence, and merges.

- **data — merged.** `backend/taxonomy.py` (42 vendors + aliases, `normalize`/`resolve`,
  `KNOWN_UNKNOWN`), `backend/data/` (generator, 3 JSON files, README with the planted-scenario
  table), `tests/test_data.py` (38 tests). Deviations accepted: usage noise ±3% (±1.5% in Sep) so
  no unplanted September charge crosses the 2σ gate; two Gusto vendors (payroll vs fee); wire fees
  carry the wire's counterparty; Cooley LLP is `usage`/`irregular` quarterly wires. Key numbers:
  Anthropic Aug $21,625.54 → Sep $34,600.86 (1.60×); Pinecone $2,487.30 → $6,512.80; trailing Aug
  spend ≈ $486K so 1% ≈ $4.9K. The pipeline must not fit growth on `irregular` vendors.
- Design amended on `main`: 12-month history, cardholders 34 → 42, Pinecone amounts, no prepaid in
  the data, integrator owns the scoreboard (decision log).
- **pipeline — merged** (`48297f7`, 33 tests, 9 mutations). **llm — merged** (`6df24bf`, 34 tests,
  3 mutations; live smoke blocked, key unset). **ui — merged** (`71cc0bd`, browser-verified on mock).
  The llm merge reconciled the contract (one `VendorFacts`, month-keyed; `Classification.confidence`
  is the Literal) but was pushed with one pipeline test still red because the test command was
  piped through `tail` (FAILURES.md #3). Fixed in `integrate`.

## 2026-09-12 — Integration (worktree `integrate`)

- Wired `classify_unknown` into `/api/run`; classifier results cached per process; on any failure it
  returns `{}` so unknown vendors keep `cost_type_source = "default"` and still get asked.
  `MAX_RETRIES = 0`, timeout 20 s, budget 60 calls/process.
- Detection tuning from the first real-data run: renewal lookahead 45 → 30 days (Vanta now appears
  only in the monthly report); `stopped` stays visible for 2 cycles (Loom reaches the Sep 30
  report); new `Config.report_floor_pct = 0.001` drops sub-0.1% noise (Costco stopped, Lyft/Delta
  growth, O'Reilly price) while price/per-head/renewal on classified vendors always report; unknown
  vendors are title-cased for display ("Pinecone Systems"). `Findings.last_monthly_spend` added so
  the report intro compares two full months, not the trailing mean against a month.
- Frontend: `USE_MOCK = false`; types regenerated (`CostTypeSource` gained `default`,
  `Config.report_floor_pct`); alert marker shows `unclassified` for `default`; report matches open
  issues by `issueKey` (vendor slug + kind) because finding ids carry the stage date — without this
  the monthly report showed "Nothing needs attention" while the intro counted 2; tiny shares render
  as `<0.1%`.
- Backend suite: 106 passed. `scripts/eval_scenarios.py` labels every planted scenario per stage
  and checks the real data (see run below).
- Local rehearsal against `vercel dev -L` (browser pane): history → Loom + Notion; new charges →
  Anthropic +$9.6K (2.0%) and Pinecone Systems $6.5K (1.4%) with the ask; "No, it's usage-based" →
  override, re-run, tag CONFIRMED; month closes → both under Needs attention "Open since Sep 5",
  Vanta / Loom / Figma / Notion under Worth knowing. Narration was `template` throughout (no key).
- Merged to `main` (`3ea4bca`), pushed, deployed: https://rho-cost-signal.vercel.app. Production
  probes: `/api/health` 0.24 s cold / 0.10 s warm; `POST /api/run inject-1` 0.81 s cold / 0.63 s
  warm with the expected five findings. Production rehearsal in the browser pane: all three steps,
  the ask → override → re-run, and "Open since Sep 5" on both issues in the monthly report. The
  main checkout is now `vercel link`ed (`.vercel/` and a `.env.local`, both gitignored).
## 2026-09-12 — Live Claude and polish (worktree `polish`)

- Key exported by the user (`~/.zshrc`; note the agent's shell is non-interactive zsh, so
  `source ~/.zshrc` is needed before a command that must see it) and added to the Vercel project.
  `smoke_llm.py`: 3 calls, classify 3.4 s, alerts 8.3 s, report 12.2 s, every number grounded.
  Redeployed; production `/api/narrate` → `X-Narration: claude` in 6.3 s.
- **Found on production:** `/api/run` took 20.9 s and classified nothing — all 26 unknown small
  merchants went to Claude in one batch and hit the 20 s timeout. Fix: only unknown recurring
  vendors whose spend has reached the report floor in some month go to the hook
  (`apply_classifications(min_monthly_spend=report_floor_pct × trailing)`). Pinecone qualifies;
  coffee shops do not. Same rule as the ask: classify when it starts to matter. Test added (a $6/mo
  tool never reaches the hook).
- Narration prompt: taxonomy is a rule, not an inference — Claude was writing "inferred from
  taxonomy". Prompt now distinguishes taxonomy / inferred / not yet classified / confirmed.
- **Playwright e2e** (`frontend/e2e/demo.spec.ts`, `npm run test:e2e`, base URL from
  `E2E_BASE_URL`, default production): two tests, 2 passed on prod in 1.1 min. First run caught
  a real problem: an LLM-classified "O Reilly Media" $49 price change appeared next to Figma's,
  because "always report price changes on classified vendors" plus classify-everything = noise.
  The classification floor removes it.
- Merged and deployed (`2a93691`); e2e 2 passed on prod. **But `/api/run` still took 21 s and
  classified nothing.** Reproduced locally with the key: the 10-vendor batch hit `APITimeoutError`
  at 20 s. Timing matrix: 4 vendors 3.9 s; 5 → 10.8 s; 10 → 20.5 s; 10 with trimmed facts 20.3 s;
  10 with thinking disabled 21.1 s; **10 without `strict` on the tool → 4.4 s.** Strict
  (grammar-constrained) decoding was the cost, and it scales with output size. Removed `strict`
  from the classify and both narrate tools; Pydantic validation and the grounding check were
  already the real guard. Smoke after: classify 2.6 s, alerts 5.4 s, report 8.1 s, all grounded.
- Merged and deployed (`70e049e`, 2026-09-13). Production verified: `POST /api/run inject-1`
  5.1 s cold with live classification (10 vendors classified; Pinecone Systems → `usage/llm`,
  "Data & tooling", ask shown), 0.57 s warm; `/api/narrate` → `X-Narration: claude` in 5.7 s;
  Playwright e2e 2 passed in 1.0 min. Polish worktree removed; no worktrees remain.

## Demo runbook

1. Open https://rho-cost-signal.vercel.app once a few minutes before presenting (warms the
   functions and fills the classification cache); `/settings` → Reset demo.
2. Load history (~7 s: pipeline + report narration) → New charges (~11 s: classification, two
   alerts, Claude prose) → answer the Pinecone question → Month closes (~9 s).
3. If Claude is slow or down, cards still render from templates (`X-Narration: template`); the
   detection never depends on it.
4. `cd frontend && npm run test:e2e` re-checks the whole flow on production in about a minute.
