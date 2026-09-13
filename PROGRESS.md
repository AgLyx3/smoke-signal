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
- **Next:** merge `scaffold` → `main` (ask), then start worktrees `data`, `pipeline`, `ui`,
  `llm` in parallel (DESIGN.md §10).
