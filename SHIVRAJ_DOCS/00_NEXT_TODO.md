# Shivraj — Next TODO

**Written:** 2026-08-30 00:34 IST · **Deadline:** 2026-08-30 10:00 ET =
**19:30 IST today** · **~18.9 hours left**

You are awake at half past midnight with a deadline this evening. The honest
plan assumes you sleep. Everything below is ordered so that if you stop at any
point, what you have already done is still the most valuable thing you could
have done by then.

**Your code work is finished.** 206 tests pass, `bash scripts/validate.sh`
passes every check against the live cluster, and the branch is pushed.
Everything left is coordination, packaging and the four deliverables the rules
actually name.

---

## The one-line summary of where the project is

The system works and is provably safe; **IBM Bob has never once reasoned**, and
the only screen a judge would click is still fake. Those two facts are the
entire remaining risk.

---

## Block A — tonight, before you sleep (30 minutes, do not skip)

These are all unblocking-other-people tasks. They cost minutes and they let
Ramana and Verona start the moment they wake up.

- [ ] **A1 · Send the two handoffs.** `04_HANDOFF_VERONA.md` and
  `05_HANDOFF_RAMANA.md` are written and ready to paste into WhatsApp. Verona
  cannot start `DASH-001` without knowing the API exists; Ramana cannot start
  `BOB-001` without knowing it is the top blocker. **5 min.**

- [ ] **A2 · Ask Ramana for the Bob credentials now, not in the morning.**
  Message: *"Do you have `KUBEMEDIC_BOB_API_KEY` and `KUBEMEDIC_BOB_AGENT_ID`
  from the IBM Bob cloud console? Everything else is done and this is the last
  blocker."* If they are asleep, the message is waiting for them. **2 min.**

- [ ] **A3 · Merge `ramana` into `main`.** `main` is still a one-line README.
  A judge cloning the default branch today sees nothing. Steps are in
  `01_MERGE_AND_RELEASE.md`. **10 min.**

- [ ] **A4 · Open your PR.** `shivraj/mcp-repo-ci` → `main`, body already
  drafted in `01_MERGE_AND_RELEASE.md`. Even if nobody reviews it before
  merge, the PR is the artifact that shows the work. **5 min.**

- [ ] **A5 · Confirm the deadline and the submission mechanism yourself.**
  I read 10:00 AM ET on 2026-08-30 out of the Official Rules PDF, and the
  rules say the Sponsors' clock is the official timekeeper. Confirm the
  BeMyApp submission portal link and whether the repo must be public.
  **5 min.** This is the cheapest way to avoid losing everything.

Then sleep. Genuinely — the remaining work needs judgement, and the two hardest
items (the video and the Bob statement) are worse when written tired.

---

## Block B — morning, first thing (~2 hours)

- [ ] **B1 · Chase `BOB-001` until it is settled, one way or the other.**
  *Owner: Ramana, but you should not let it drift.* Detail in
  `05_HANDOFF_RAMANA.md`.
  - **If Bob works:** run `bash scripts/validate.sh` again with the keys set.
    It will assert `analysis_source == "ibm-bob"` and exercise the real
    revision loop. Save the resulting `records/*.json` — that file is your
    single best piece of evidence.
  - **If Bob cannot be reached by ~11:00 IST, stop trying.** Write the
    submission around what is true instead. `SUB-002` has a draft for both
    outcomes. Sinking four hours into an endpoint that may not be the
    sanctioned one is how the whole entry gets lost.

- [ ] **B1a · Run a real incident analysis inside IBM Bob, using our own MCP
  server.** `07_WORK_INSIDE_IBM_BOB.md` B1. **Do this before anything else in
  the morning.** It does not depend on the unverified REST endpoint: open the
  repo as a Bob workspace, Bob launches our evidence server itself, inject the
  incident, and work it in `KubeMedic Analyst` mode. That converts "Bob is the
  reasoning layer" from a design claim into something a judge watched happen,
  and it produces both the session to export and the footage for the video.
  **45 min.**

- [ ] **B2 · Export the IBM Bob report.** This is a **required deliverable**
  and the one teams forget. Procedure in `02_BOB_REPORT_EXPORT.md`. It is
  required whether or not B1 succeeds. **30 min.**

- [ ] **B3 · Secret sweep over full history**, not just the working tree.
  Command in `01_MERGE_AND_RELEASE.md`. **15 min.**

---

## Block C — midday (~3 hours, mostly other people)

- [ ] **C1 · Verona: `DASH-001`.** The dashboard is the biggest remaining risk
  to the entry and it is not your lane — but it is your problem if it does not
  land. Check in by 13:00 IST. If it will not be done, the fallback is in
  `06_DEMO_SCRIPT.md`: demo the terminal harness instead, which is real. A
  slower, honest demo beats a slick one whose audit record asserts six checks
  that never ran.

- [ ] **C2 · Ramana: `SUB-001` and `SUB-002`.** Drafts are written — they need
  Ramana's review and the truth about Bob filled in, not a rewrite.

- [ ] **C3 · Verona: record `SUB-004`, the video.** Script and shot list in
  `06_DEMO_SCRIPT.md`. Must state how IBM Bob was used. Must be in English.

---

## Block D — freeze, 16:00 IST at the latest (~1 hour)

Three and a half hours of buffer before the deadline is not padding. It is the
difference between submitting and discovering the portal wants a file format
you do not have.

- [ ] **D1 · Final `pytest` and `validate.sh`** on `main`, output pasted into
  `03_SUBMISSION_CHECKLIST.md`.
- [ ] **D2 · Fresh-clone test.** Clone into a new directory, follow the README
  exactly, confirm the suite passes. This is judging criterion
  "completeness and feasibility", measured directly.
- [ ] **D3 · Tag `v1.0-submission`** and push it.
- [ ] **D4 · Assemble the submission** using `03_SUBMISSION_CHECKLIST.md`.
- [ ] **D5 · Submit.** Do not wait for one more improvement. The rules say an
  entry cannot be enhanced once committed, so a late perfect entry is worth
  nothing and an on-time honest one is worth everything.

---

## What is already done (do not redo)

| | |
|---|---|
| MCP server | Names aligned, `--profile evidence` enforced, 18 contract tests |
| Ticket store | `NameError` fixed, one ticket per signal, 25 tests |
| Live remediation | Real rollback executed and verified on the cluster |
| Human review | `400 feedback_required`, refusal verified live |
| Feedback loop | Rejection reason reaches Bob's prompt, capped at 3 revisions |
| Agent API | 8 routes, 28 tests |
| Repo hygiene | Dependencies, CI, README, working `validate.sh` |
| Documentation | 23 docs in `docs/` |
| Tests | **206 passed** |
| End-to-end | **ALL CHECKS PASSED** on live k3s |

---

## If you only get three more things done

1. **Merge `ramana` to `main`** (A3) — otherwise the repository a judge opens
   is empty, and everything above is invisible.
2. **The exported IBM Bob report** (B2) — explicitly required; its absence can
   sink an otherwise complete entry.
3. **The video** (C3) — the first deliverable listed in the rules, and the only
   one that shows the system moving.

---

## The one judgement call I would push back on

If it reaches 15:00 IST and the dashboard is still mocked, **do not show it.**
`dashboard/app.py:_decide()` writes an audit record asserting that six named
verification checks passed, derived entirely from whether the user clicked
Approve. Nothing is checked and no cluster is contacted.

Showing that as a verified recovery is a false claim to a judge, and the rules
allow disqualification of submissions that "appear not to have been submitted
honestly and in good faith". `06_DEMO_SCRIPT.md` has a terminal-based demo that
is completely real and takes four minutes. Use it.
