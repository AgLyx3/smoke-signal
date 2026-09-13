# Lessons

**This is a learning file, not a diary.** Each entry is a *rule to follow*, with the failure
that earned it kept underneath as evidence. Read it at session start, before writing code.

### Maintaining it

- **Lead with the rule, not the incident.** A reader should get the takeaway in one line.
- **Same class of failure again? Sharpen the existing rule**, add the new evidence. Do not
  append a near-duplicate.
- **Delete entries that stop applying.** A file too long to read teaches nothing.
- **If a rule keeps getting violated, promote it** to Hard Rules in `CLAUDE.md`.
- Skip anything a compiler catches in seconds. This file is for what costs *time*.

---

## 1. Don't design around a missing field until you've checked another source

**Rule:** When a data source lacks something you need, the next question is "does a different
source have it?", not "how do I work around its absence?"

**Earned by (carried over from a previous project):** a payload lacked funding
data, so a field was designed as fuzzy inference over profile text, when a direct lookup on the
company answered it far better. The first design was not just weaker, it was differently shaped.

**Applies here:** Rho transactions have no MCC or category field, but card controls carry MCC
allow/block lists, and `memo` exists in the spec even though the sandbox omits it. Check those
before building inference around the gap.

## 2. A check must be able to fail — prove it by breaking the property first

**Rule:** A new check is not evidence until you have made the thing it guards wrong and watched
it exit 1. Break the property, confirm red, restore, confirm green.

**The shape, every time: asserting something adjacent to the property.** A count, a constant, a
substring, a flag. Adjacent things correlate with the property right up until they stop.

**Earned by (carried over from a previous project):** five instances in one phase,
including a row count that could not distinguish a limit of 25 from 300 because the fixture had
13 rows, and a substring check that stayed green after the clause it guarded was deleted. Four of
the five were caught by `/code-review`, not the author. Treat "my new check passed first try" as
a smell.

## 3. Anything piped through `tail` has no exit code — never put it in a `&&` chain

**Rule:** Never chain `<command> | tail -n && <next step>` when the next step must not run on
failure. The pipeline's status is `tail`'s, so a red test suite commits and a conflicted
`git merge` pushes and deploys. Run the gating command on its own, or `set -o pipefail` and check
`$pipestatus`, and read its output before the next command runs. This applies to **every**
gating command — tests, merges, builds — not only pytest.

**Earned by:** the `llm` merge (2026-09-12) was committed and pushed to `main` with
`test_unknown_vendor_defaults_until_hook_or_override` failing (104 passed, 1 failed) because the
merge changed `Classification.confidence` to a Literal and a pipeline test still passed a float.
The failure was on screen; the `&&` chain never saw it.

**Earned again (2026-09-13, same author, rule already written):** `git merge records | tail -1 &&
git push && vercel deploy --prod` hit a `PROGRESS.md` conflict; `tail` returned 0, the push sent
only the preceding docs commit, and production was deployed from a half-merged working tree.
Knowing the rule did not prevent it; the fix is mechanical — no pipe on a gating command.
