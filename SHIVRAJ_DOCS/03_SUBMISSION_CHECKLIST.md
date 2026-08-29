# Submission Checklist

**Deadline: 2026-08-30 10:00 ET = 19:30 IST.** The rules state the Sponsors'
clock is the official timekeeper and that a late entry "may be disqualified".
Target 16:00 IST.

---

## The four required deliverables

Quoted from ENTRY REQUIREMENTS. Every one is mandatory.

| # | Deliverable | Owner | Status | Where |
|---|---|---|---|---|
| 1 | Video demonstration of the solution, **including how IBM Bob was used** | Verona | ☐ TODO | `06_DEMO_SCRIPT.md` |
| 2 | Written problem and solution statements | Ramana | ☐ DRAFTED | `SUB-001_PROBLEM_AND_SOLUTION.md` |
| 3 | Written statement on how IBM Bob was utilised | Ramana | ☐ DRAFTED | `SUB-002_HOW_WE_USED_IBM_BOB.md` |
| 4a | Working code repository | Shivraj | ☑ DONE | `github.com/Edith-Stark06/Kubemedic` |
| 4b | **Exported IBM Bob report of all relevant tasks/sessions** | Shivraj | ☐ TODO | `02_BOB_REPORT_EXPORT.md` |

Deliverable 4b sits inside another bullet and is the one teams miss.

---

## Compliance

| Requirement | Status | Note |
|---|---|---|
| Team ≤ 5 | ☑ | Three: Ramana, Verona, Shivraj |
| Team Lead named | ☐ | **Confirm** — rules allow Sponsors to require one |
| Submitted before 10:00 ET 2026-08-30 | ☐ | Target 16:00 IST |
| All materials in English | ☑ | Confirm the video narration too |
| One entry per team | ☑ | |
| Free and unrestricted availability | ☐ | **Repo is private.** Confirm whether it must be public |
| IBM Bob account established | ☐ | Ramana |
| Credible or feasible use of watsonx | ⚠ | See below |
| Affiliations disclosed | ☐ | Each member states employer or university |
| No infringing content | ☑ | Deps: fastapi, uvicorn, jinja2, pydantic, kubernetes, mcp, pytest |
| Not substantively developed pre-contest | ⚠ | See below |
| Honest and good faith | ⚠ | See below |

---

## The three ⚠ items, honestly

### watsonx

The rules say two things and both are true:

> "establish an IBM Bob account and **optionally** establish an IBM Cloud
> Account with access to watsonx services"

> "Sponsors reserve the absolute right in their sole discretion to disqualify
> as ineligible Submissions that **do not provide a credible or feasible use of
> watsonx technology**"

So watsonx is optional to *set up*, but its credible or feasible use is a
stated disqualification ground. Our position: IBM Bob is the single reasoning
boundary, `agent/bob.py` is the only module that calls a model, and the
architecture puts Bob at the centre by design. The weakness is that **no live
Bob analysis has been observed**. `BOB-001` is the fix; if it does not land,
`SUB-002` says so plainly rather than implying otherwise.

### Pre-contest development

Contest began 2026-08-28 10:00 ET. Some archive files carry 2026-08-25
timestamps. All six commits on `ramana` and all ten on `shivraj/mcp-repo-ci`
fall inside the window.

**Disclose it.** Suggested wording for the submission form:

> Early exploratory work on the Kubernetes evidence layer predates the contest
> window. The submitted architecture — the agent, the MCP contract, the human
> review loop, the API and the test suite — was built during the contest and
> the git history shows it. We are flagging this rather than leaving it to be
> discovered.

### Honest and good faith

The live risk is `dashboard/app.py:_decide()`, which writes an audit record
asserting six named verification checks passed, derived from whether the user
clicked Approve. Nothing is checked; no cluster is contacted.

**If `DASH-001` does not land, do not show the dashboard in the video.**
Demonstrating a fabricated verification as a real one is the clearest way to
trip this clause. `06_DEMO_SCRIPT.md` has a fully real terminal alternative.

---

## Evidence to attach

| Artifact | Command | Status |
|---|---|---|
| Test output | `python -m pytest \| tee submission/evidence/pytest-run.txt` | ☐ |
| End-to-end run | `bash scripts/validate.sh \| tee submission/evidence/validate-run.txt` | ☐ |
| Real audit record | copy one `records/INC-*.json` into `submission/evidence/` | ☐ |
| Bob analysis record | a record with `analysis_source: "ibm-bob"` — **only if `BOB-001` lands** | ☐ |
| Fresh-clone proof | `01_MERGE_AND_RELEASE.md` §5 | ☐ |

---

## Final sequence

- [ ] `ramana` merged to `main`
- [ ] `shivraj/mcp-repo-ci` merged to `main`
- [ ] `verona` merged to `main` (if `DASH-001` lands)
- [ ] `python -m pytest` on `main` — record the number
- [ ] `bash scripts/validate.sh` on `main` — record the outcome
- [ ] Fresh clone passes
- [ ] Secret sweep over full history clean
- [ ] `submission/` complete
- [ ] Repo visibility correct
- [ ] Tag `v1.0-submission` pushed
- [ ] Video uploaded, link works **when logged out**
- [ ] Submission form completed and **submitted**

---

## What to claim, and what not to

**Claim — all verified:**

- Many tickets correlate into one incident, from real observations
- Nothing mutates the cluster without a recorded human approval; the refusal is
  demonstrated live, and the cluster is asserted unchanged afterwards
- A rejected plan is structurally incapable of executing
- Rejection requires a reason, and that reason becomes reasoning context
- Recovery is confirmed on two independent signals and never inferred
- 206 tests; end-to-end harness passes against a live cluster

**Do not claim, unless `BOB-001` lands:**

- That IBM Bob produced a diagnosis in a live run
- That the revision loop has been exercised with a real model round-trip
- Anything about the dashboard, unless `DASH-001` lands

The strongest thing about this project is that it refuses to overstate itself.
The submission should sound the same way.
