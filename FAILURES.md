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
