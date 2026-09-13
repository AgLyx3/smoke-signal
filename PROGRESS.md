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
