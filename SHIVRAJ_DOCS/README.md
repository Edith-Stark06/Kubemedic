# SHIVRAJ_DOCS

Shivraj's working directory: the next actions, the handoffs, and the drafts of
the deliverables I own.

Project documentation lives in [`docs/`](../docs/) — that describes the system.
This describes what still has to happen before 19:30 IST today.

| File | What it is | Read when |
|---|---|---|
| [`00_NEXT_TODO.md`](00_NEXT_TODO.md) | **Start here.** Time-boxed action list to the deadline | Now |
| [`01_MERGE_AND_RELEASE.md`](01_MERGE_AND_RELEASE.md) | Merge `ramana` to `main`, PR body, branch protection, secret sweep, fresh-clone test, tag | Tonight |
| [`02_BOB_REPORT_EXPORT.md`](02_BOB_REPORT_EXPORT.md) | `SUB-003` — the exported IBM Bob report the rules require | Morning |
| [`03_SUBMISSION_CHECKLIST.md`](03_SUBMISSION_CHECKLIST.md) | All four deliverables, compliance status, what to claim and what not to | Throughout |
| [`04_HANDOFF_VERONA.md`](04_HANDOFF_VERONA.md) | API reference for the dashboard; paste-ready chat message | Send tonight |
| [`05_HANDOFF_RAMANA.md`](05_HANDOFF_RAMANA.md) | `BOB-001` and the statements; paste-ready chat message | Send tonight |
| [`06_DEMO_SCRIPT.md`](06_DEMO_SCRIPT.md) | `SUB-004` — video script, two versions, with narration | Before recording |
| [`07_WORK_INSIDE_IBM_BOB.md`](07_WORK_INSIDE_IBM_BOB.md) | **What must be done in the Bob application itself** — the part no code can do | Morning, first |
| [`SUB-001_PROBLEM_AND_SOLUTION.md`](SUB-001_PROBLEM_AND_SOLUTION.md) | Draft, ready for review | Ramana reviews |
| [`SUB-002_HOW_WE_USED_IBM_BOB.md`](SUB-002_HOW_WE_USED_IBM_BOB.md) | Draft with two variants — pick after `BOB-001` | Ramana reviews |

---

## Where the project actually is

**Code: done.** 206 tests pass. `bash scripts/validate.sh` passes every check
against the live cluster — real failure injected, real tickets correlated, an
unapproved execution refused with the cluster asserted unchanged, a reasonless
rejection refused, a real rollback executed, recovery verified on two
independent signals, audit record written.

**Two things are not done, and neither is code:**

1. **IBM Bob has never returned a live analysis.** No credentials. `BOB-001`,
   Ramana's.
2. **The dashboard still fabricates verification results.** `DASH-001`,
   Verona's.

**The four required deliverables** — video, problem/solution statements, Bob
utilisation statement, and the exported Bob report — are what the entry is
actually judged on. Two are drafted here; two are not started.

---

## If you read one thing

`00_NEXT_TODO.md`, Block A. Five tasks, thirty minutes, all of them unblock
someone else. Then sleep — the video and the Bob statement both get worse when
written tired, and there is time for them in the morning.
