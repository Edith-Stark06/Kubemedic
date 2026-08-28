---
name: track-consolidation
description: >-
  Plans and executes the merge of a legacy orchestrator into the current agent
  architecture without losing working logic. Activates on consolidating two
  architectures, merging orchestrator into agent, removing a duplicate code
  path, or deciding which of two implementations to keep.
user-invocable: true
---

# Track 1 to Track 2 consolidation

Two competing architectures in one submission reads as an unfinished project.
The goal is one coherent path, with the legacy code mined for anything worth
keeping rather than deleted on sight.

## Order of operations — do not skip step 1

**1. Inventory before touching anything.** For every module in `orchestrator/`,
record: what it does, whether an equivalent exists in `agent/`, which
implementation is better and why, whether tests cover it, and whether the
demo path depends on it. Write this to `docs/consolidation-inventory.md` and
commit it before making a single change. It is your rollback map and it is
also honest evidence of deliberate engineering.

**2. Classify each module.**

- **PORT** — legacy is better or the only implementation. Move it across.
- **KEEP** — Track 2 already has the better version. Legacy is redundant.
- **MERGE** — each has something. Take the better half of each, deliberately.
- **DROP** — dead in both. Note it and move on.

**3. Port in dependency order,** leaves first. Models, then correlation, then
planning, then executor, then verification, then audit, then the entry point.
Run the tests after each one.

**4. Archive, do not delete, until the end.** Move `orchestrator/` to
`archive/orchestrator/` with a README explaining what it was and where its
logic went. Delete only after the end-to-end flow has run clean twice.

## Rules while porting

- **Never break a passing test to tidy the tree.** If a test in `orchestrator/`
  covers behavior you are keeping, port the test with the code.
- **Keep interfaces stable** where anything else imports them. Verona and
  Shivraj are working against these — a signature change mid-hackathon costs
  someone else an hour.
- **One module per commit,** with the test output in the commit message. This
  is the git history a reviewer reads.
- If a legacy module is better but depends on legacy infrastructure, port the
  logic and rewrite the seam. Do not drag the dependency across with it.

## Definition of done

The end-to-end flow runs from `agent/` alone with `archive/` removed from the
import path entirely, tests pass, and no module in the live tree imports
anything under `archive/`. Verify that last one with a grep, not by reasoning
about it.
