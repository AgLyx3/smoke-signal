# CLAUDE.md

## Scope

These instructions apply to the whole repository. Once Next.js is installed, `next dev` writes
an `AGENTS.md` with framework rules for the installed version. Read it, and read the relevant
guide in `node_modules/next/dist/docs/` before writing framework code: recent Next.js versions
break conventions most training data assumes.

## Project Context

A demo of a cost-signal layer for Rho: it learns each vendor's normal spend trajectory from
transaction history, detects meaningful changes, classifies vendors, and explains the change.
It runs on **synthetic data shaped like Rho's API schema**. Output is a web page showing
Slack-style alert cards and a periodic report. Target customers are VC-backed startups from seed
through Series B, including companies in their scale-up phase.

- **PRD:** the "Cost Signal Layer for Rho — PRD & Implementation Plan" artifact,
  https://claude.ai/code/artifact/b89551bd-2396-41fa-af60-1b7d197aee1e
- **Research:** `~/Desktop/rho-idea-investigate/docs/research/`. Especially `rho-api.md`,
  `rho-sandbox-findings.md`, `rho-openapi.json`, `learned-trend-alerts.md`, `rho-slack-app.md`.
- **Design doc:** `DESIGN.md`. Read it before any architecture, data-shape, detection-logic, or
  prompt change. It carries the understanding summary, assumptions, decision log, and scope.

## Hard Rules

- **Write or update `DESIGN.md` before implementing.** A data shape, a detection rule, an API
  route, or a prompt contract is written down and confirmed before the code exists. If a
  decision changes mid-build, amend the decision log in the same change.
- **Never implement ahead of confirmation.** Present the plan, wait for explicit approval
  ("go ahead", "build it"). An interrupted or ambiguous approval is not approval.
- **Never commit without asking first.** Show what will be committed, then wait.
- **Never push, deploy, or publish without explicit permission.** Includes `git push`,
  `vercel deploy`, and promoting a preview to production.
- **Work in a git worktree, never directly on `main`.** Each feature or parallel stream starts
  with `git worktree add ../smoke-signal-worktrees/<name> -b <branch>`. One worktree per
  feature, so parallel work never shares a tree. Merging back to `main` needs explicit
  permission.
- **Never copy a secret file into a worktree.** A fresh worktree has no `.env*`. Once the Vercel
  project exists, use `npx vercel env pull .env.local` inside the worktree. Before that, rely on
  `ANTHROPIC_API_KEY` exported in the user's shell. Delete a worktree's env files before
  removing the worktree.
- **Never run destructive commands** (`rm -rf`, `git reset --hard`, deleting a Vercel project)
  without explicit instruction.
- **Never expose secrets.** `ANTHROPIC_API_KEY` is server-side only: never prefix it with
  `NEXT_PUBLIC_`, never log it, never commit it, never read it into a transcript. `.env*` is
  gitignored; keep it that way.
- **Live Claude calls cost money.** Never call the API in a loop, on a timer, or from a check
  script without saying so. The demo calls Claude only on explicit demo steps.
- **`.claude/settings.json` enforces part of the above; the prose still governs.** It denies
  reading `.env*` and asks before commit, push, merge, deploy, and `rm -rf`. It is incomplete by
  construction: `cat` bypasses a Read deny, and every `ask` matches a command shape. Never read
  a command going through unprompted as permission.

## Data Rules

- All transaction data is **synthetic**. Never add real company or personal financial data.
- What reaches Claude: vendor names, amounts, dates, and computed statistics from the synthetic
  dataset. Do not widen that without saying so in `DESIGN.md`.
- **Stats detect, the LLM narrates.** Detection is deterministic. Claude classifies vendors and
  writes explanations grounded in computed facts; it never decides whether something fires.

## Working Style

- **Push back.** If an idea, assumption, or direction looks weak, say so plainly, with
  evidence, and recommend an alternative.
- **Do not stop at the first constraint.** If a data source lacks a field, check whether
  another source has it before designing around the absence.
- **Verify instead of assuming.** Probe payload shapes, API contracts, and library versions.
  Checked assumptions go in `DESIGN.md`; unchecked ones are marked unverified.
- **Parallelize independent work.** Independent tool calls in one block; independent features
  in separate worktrees.
- **State uncertainty once, in the right place.** Flag a blocker, keep working on everything
  that does not depend on it, and do not re-litigate a settled decision.
- **Report outcomes faithfully.** Show failing output. Say which steps were skipped and why.
  Never describe partial work as finished.
- **Keep scope tight.** No bonus features, no speculative abstraction. Out-of-scope items in
  `DESIGN.md` are deferred on purpose.

## Giving Suggestions

For every realistic option give pros and cons, including the downsides of the one you
recommend. Still end with a clear recommendation and say what would change it. Skip options
that are not genuinely on the table.

## Long-Running Task Protocol

**Context does not survive; files do.**

### Session start, before writing code

1. Read `DESIGN.md`, this file, `PROGRESS.md`, and `FAILURES.md`. Run
   `node scripts/features.mjs`; that tally, not memory, is the state of the build.
2. `git log --oneline -10`, `git status`, and `git worktree list`.
3. Build once before changing anything, so a pre-existing break is not mistaken for yours.
4. Pick **one** item per worktree.

### During the session

- One unit of work at a time per worktree. Never one-shot the whole remaining plan.
- Write findings down as they happen: into `DESIGN.md` or `FAILURES.md`, not at the end.

### Session end

- Leave every tree clean and buildable.
- Update `PROGRESS.md` and `FEATURES.json`: what landed, what is next, what is half-done.
- Ask to commit, with a descriptive message.
- Never leave a feature half-implemented and undocumented. Finish the smallest coherent slice
  or revert it, and say which.

## Verification

`FEATURES.json` is the scoreboard.

- **End to end beats unit tests.** Drive the real dev server and the real page the way a
  presenter would. Desktop viewport first: the demo is presented on a laptop.
- **A feature becomes `passing` only after its `verify` steps were executed and observed to
  pass.** If a step cannot be run, set `blocked` with a `blocked_by` key. Never guess a status.
- **A check is not evidence until you have watched it fail.** Break the property it guards,
  confirm exit 1, restore, confirm it passes. The recurring bug is asserting something adjacent
  to the property (a count, a constant, a substring). See `FAILURES.md` #2.
- Update `FEATURES.json` in the same change that implements the feature.
- Report completion as the tally, never as an impression.
- Before handing back work: `npm run build`, `npx tsc --noEmit`, and `/code-review` with an
  explicit worktree path target. Confirm the review names the files you changed.

## Subagents

- **`check-auditor`** proves a check script or eval scenario can actually fail. Run it on every
  new or changed check, and on any check cited as evidence for a `passing` row.
- **`features-auditor`** checks that `passing` rows have verify steps that were executed and
  could fail. Run it before reporting a phase complete.

A subagent that finds nothing should say so. A clean report on your own work is a weak signal.

## Code Style

- Match the surrounding code's naming, comment density, and idiom.
- No comments unless the reason is non-obvious.
- Prefer editing an existing file over creating a new one.
- Detection logic lives in `src/lib/` as pure functions; route handlers and components stay thin.
