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
- **Next:** user reviews the A5 result and says "build". Then worktree `scaffold` (§10 row 0),
  and `FEATURES.json` rows with verify steps in the same change.
