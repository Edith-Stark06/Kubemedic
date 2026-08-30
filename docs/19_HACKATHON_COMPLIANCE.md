# 19 — Hackathon Compliance

**Source:** `IBM TechXchange 2026 Pre-conference Dev Day Hackathon OFFICIAL
RULES`, 15 pages, read from
`Desktop/Devops/opspilot/33893b2e0869f45c5249d408.pdf`. Quotations below are
from that document. Only requirements the rules actually state are listed.

Status values: `COMPLIANT` · `PARTIAL` · `GAP` · `NEEDS VERIFICATION`.

---

## The finding that outranks every other item in this repository

> "The Contest begins on or about 10:00 AM ET on August 28, 2026, and ends
> approximately 10:00 AM ET on August 30, 2026... Last call for submission of
> a team's entry must be received by the Sponsors on or before **10:00 AM ET
> on August 30, 2026**, or the Participant's entire team entry may be
> disqualified."

**Today is 2026-08-29.** Roughly one working day remains.

Approximately **19:30 IST on 2026-08-30** — *conversion, verify against your
own clock; the rules state the Sponsors' clock is the official timekeeper.*

Status: **NEEDS VERIFICATION** — confirm the exact local deadline and the
submission mechanism now, before writing any more code.

`14_INTEGRATION_PLAN.md` estimates 22-25 hours of work for full integration.
That does not fit. `16_TASK_BACKLOG.md` carries the triage.

---

## Requirements

### Team size — **COMPLIANT**

> "Participants may participate in the Contest individually or in teams up to
> five (5) people."

Three members: Ramana, Verona, Shivraj. Within the limit. Note also
*"Participant(s) may only work on one team"* and that a Team Lead may be
required as primary point of contact — **NEEDS VERIFICATION**: has one been
assigned?

### Required submission deliverables

> "Each Submission must include the following deliverables:
> 1. Video demonstration of the team's solution, including how IBM Bob was used
> 2. Written problem and solution statements
> 3. Written statement on how IBM Bob was utilized
> 4. Working code repository or evidence of technology proof-of-concept
>    solution, including exported IBM Bob report of all relevant tasks/sessions
>    used for the contest"

| # | Deliverable | Status | Notes |
|---|---|---|---|
| 1 | Demo video incl. how Bob was used | **GAP** | Not produced. Must not be recorded against the mocked dashboard — see `18_DEMO_RUNBOOK.md` |
| 2 | Problem and solution statements | **GAP** | Not written. `SUB-001` |
| 3 | How IBM Bob was utilised | **GAP** | Not written. `SUB-002` |
| 4a | Working code repository | **PARTIAL** | Real, tested `agent/`; but `main` is an empty README, the dashboard is mocked, and no end-to-end path runs |
| 4b | **Exported IBM Bob report of all relevant tasks/sessions** | **GAP** | Not present. Explicitly required. `SUB-003` |

Deliverable 4b is easy to overlook and is stated as mandatory. `AGENTS.md`
already anticipates it (`submission/bob-report/`) and warns that it must
contain no credentials or absolute local paths.

### English — **NEEDS VERIFICATION**

> "Submissions must be in English."

Repository content is in English. The video and statements do not exist yet.

### Free availability — **NEEDS VERIFICATION**

> "Participants must make the Submission available free of charge and without
> any restriction..."

The repository is currently **private** (`Edith-Stark06/Kubemedic`, and a push
from a non-collaborator account was refused with 403). Confirm what visibility
the Sponsors require and when.

### One entry per team — **COMPLIANT**, assuming a single submission.

### IBM technology — **PARTIAL**

> "Participants will be required... to **establish an IBM Bob account** and
> **optionally** establish an IBM Cloud Account with access to watsonx services
> provided by IBM for the sole purposes of participation in the Contest..."

Note carefully: an **IBM Bob account is required**; a watsonx-enabled IBM Cloud
account is **optional**. That is narrower than the framing circulating in the
team's planning notes.

But the winner-selection section adds a real risk:

> "Sponsors reserve the absolute right in their sole discretion to disqualify
> as ineligible Submissions (in Sponsors sole determination) that **do not
> provide a credible or feasible use of watsonx technology**, were developed in
> a substantive form/format prior to the Contest, appear not to have been
> submitted honestly and in good faith, or are otherwise lacking or
> non-compliant."

So watsonx is optional to *establish* but its credible or feasible use is a
stated disqualification criterion. Both things are true; do not quote only one.

**Current position:** the theme is *"Build with purpose using IBM Bob 2.0"*,
and `agent/bob.py` is a genuine, single-boundary Bob integration with an honest
failure policy. But `analysis_source: "ibm-bob"` has **never been produced** —
no live analysis has been observed. Task `BOB-001` is therefore the highest
compliance priority in the project.

### Gemini — **COMPLIANT, with cosmetic residue**

The rules do **not** prohibit Gemini, or name any competing model provider.
Nothing here says using Gemini is forbidden.

Repository facts:

- **No Google or Gemini SDK is used anywhere.** No `google-genai`, no
  `google.generativeai`, no `GOOGLE_API_KEY`, no `vertexai` import. Verified by
  `git grep`.
- No requirements file lists a Google dependency.
- The reasoning path is IBM Bob only.
- Remaining references are strings, in two categories:
  - **Legitimate:** `.bob/skills/gemini-audit/` and `.bob/agents/gemini-auditor.md`
    are the *auditor that searches for* Gemini. Keep them.
  - **Cosmetic residue, must go:** `dashboard/app.py:202,299,389` stamp
    `"source": "gemini"` on fabricated data; `templates/index.html:263` reads
    *"Gemini LLM for hypothesis generation"*; line 834 colours a chip on
    `rep.source === 'gemini'`.

The risk is not rule-breaking; it is a judge reading `index.html:263` and
concluding the Bob integration is decorative. Task `DASH-003`.

> `docs/consolidation-inventory.md` states that no dashboard template contains
> a Gemini reference. That was accurate when written, before `dashboard/` was
> on this branch. It is now inaccurate and should be corrected (task `DOC-001`).

### Pre-existing work — **NEEDS VERIFICATION, and it is a real risk**

The rules allow disqualification of Submissions that "were developed in a
substantive form/format prior to the Contest".

The contest began **2026-08-28 10:00 ET**. Several archive files carry earlier
modification times — `README.md` and `DEMO.md` at Aug 25 21:08,
`33893b2e...pdf` at Aug 25 18:40, and `orchestrator/` predates the
consolidation.

This is a judgement call the team must make honestly, not one to paper over.
The strongest position is transparency: state in the submission what existed
before 2026-08-28 and what was built during the contest window. The git
history on `ramana` (all six commits dated within the contest period) supports
the claim that the submitted architecture was built during the contest.

### Honest and good faith — **AT RISK**

The rules permit disqualification of Submissions that "appear not to have been
submitted honestly and in good faith".

`dashboard/app.py:_decide()` writes an audit record asserting that six named
verification checks passed, derived entirely from whether the user clicked
Approve. Nothing is checked and no cluster is contacted. If that dashboard is
what the demo video shows, the video demonstrates verified recovery that did
not occur.

**This is the single strongest argument for `DASH-001` being P0.** It is not
only an engineering defect; it is a submission-integrity risk. Either wire the
dashboard to the real agent, or demo the manual fallback and state the
limitation.

### Intellectual property, privacy, publicity — **NEEDS VERIFICATION**

The rules require that the Submission not infringe any rights, that all
contributors consented, and that participants disclose their employer or
educational affiliation. Sponsors may use the Submission for promotional
purposes. The repository has a `LICENSE` — confirm it is compatible with the
required free availability, and that all three members have disclosed
affiliation.

`AGENTS.md` calls for a `THIRD_PARTY_NOTICES.md`; none exists. Dependencies
are `fastapi`, `uvicorn`, `jinja2`, `pydantic`, `kubernetes`, `mcp`, `pytest`.

### Judging criteria — context for triage

> "Completeness and feasibility (5 points) · Effectiveness and efficiency
> (5 points) · Design and usability (5 points) · Creativity and innovation
> (5 points). A Submission must receive a minimum score of 12.5 points for
> prize consideration."

Read against this repository:

| Criterion | Current standing |
|---|---|
| Completeness and feasibility | Hurt most by the disconnect: `main` is empty, and no path runs end to end |
| Effectiveness and efficiency | The agent's safety model is genuinely strong and tested — lead with it |
| Design and usability | Currently the weakest, because the dashboard is a mock |
| Creativity and innovation | Many-to-one correlation and the mandatory-reason rejection loop are the differentiators — and the loop is not implemented |

---

## Compliance summary

| Item | Status |
|---|---|
| Team size ≤ 5 | COMPLIANT |
| Team Lead assigned | NEEDS VERIFICATION |
| Submission by 2026-08-30 10:00 ET | **AT RISK — under one day remains** |
| 1. Demo video | GAP |
| 2. Problem/solution statements | GAP |
| 3. IBM Bob utilisation statement | GAP |
| 4a. Working repository | PARTIAL |
| 4b. Exported IBM Bob report | GAP |
| English | NEEDS VERIFICATION |
| Free availability / repo visibility | NEEDS VERIFICATION |
| IBM Bob account established | NEEDS VERIFICATION |
| Credible or feasible watsonx use | **PARTIAL — no live Bob analysis observed** |
| Gemini | COMPLIANT (not prohibited; no SDK present); cosmetic strings to remove |
| Pre-Contest development | NEEDS VERIFICATION — disclose honestly |
| Honest and good faith | **AT RISK — the mocked dashboard fabricates verification results** |
| IP / affiliation disclosure | NEEDS VERIFICATION |
