# Submission — IBM TechXchange 2026 Pre-conference Dev Day Hackathon

**Project:** KubeMedic — evidence-driven Kubernetes incident response with a
human in the loop
**Theme:** Build with purpose using IBM Bob 2.0
**Team:** Ramana, Verona, Shivraj (3 of a maximum 5)

---

## The four required deliverables

| # | Deliverable | Where | Status |
|---|---|---|---|
| 1 | Video demonstration, including how IBM Bob was used | *link to be added* | **TODO** |
| 2 | Written problem and solution statements | [`PROBLEM_AND_SOLUTION.md`](PROBLEM_AND_SOLUTION.md) | **DONE** |
| 3 | Written statement on how IBM Bob was utilised | [`HOW_WE_USED_IBM_BOB.md`](HOW_WE_USED_IBM_BOB.md) | **DONE** |
| 4a | Working code repository | [github.com/Edith-Stark06/Kubemedic](https://github.com/Edith-Stark06/Kubemedic) | **DONE** |
| 4b | Exported IBM Bob report of all relevant tasks/sessions | [`bob-report/`](bob-report/) | **DONE** — best-effort (Bob v1.126.0 has no export function; see bob-report/README.md) |

---

## Evidence

Everything in [`evidence/`](evidence/) was produced by running the submitted
code. Nothing is hand-written.

| File | What it shows |
|---|---|
| [`evidence/pytest-run.txt`](evidence/pytest-run.txt) | **221 passed** — the full suite at time of the validate run |
| [`evidence/validate-run.txt`](evidence/validate-run.txt) | **29 assertions, 0 failures** against a live k3s cluster |
| `evidence/INC-*.json` | A real audit record from that run |

### What the end-to-end run proves

`bash scripts/validate.sh` drives the whole loop against a real cluster and
exits non-zero on any failed assertion:

```
healthy 2/2 -> inject bad image -> rollout stalls 2/3
  -> watcher files 2 tickets from 2 distinct signals
  -> re-poll files 0 (deduplicated)
  -> both correlate into ONE incident, 0 excluded
  -> execute without approval        REFUSED, cluster asserted unchanged
  -> reject without a reason         REFUSED
  -> reject with a reason            recorded, cluster still unchanged
  -> approve
  -> rollback executed through the Kubernetes API
  -> verified on TWO independent signals
  -> RESOLVED, audit record written
  -> reset
```

The audit record in `evidence/` carries the two correlated ticket ids, the
rejection reason in `feedback_history`, `executed: true` and
`verification_outcome: PASS`.

---

## What we are not claiming

`analysis_source` in that record reads **`unavailable`**, not `ibm-bob`.

IBM Bob's runtime reasoning path is implemented, contract-tested and its
failure policy verified — but we did not complete a live model call before the
deadline. In our cluster runs the system reported `BOB_UNAVAILABLE`, produced
no diagnosis, and refused to build a plan; the harness substituted an
operator-specified rollback and **labelled it as operator-specified** in both
its output and the audit record, so the approval gate, executor and verifier
could still be exercised end to end.

We would rather say that plainly than imply otherwise. A system that invents a
diagnosis when its reasoner is unreachable is more dangerous than one that says
nothing — and ours refusing to is tested, not asserted.

See [`HOW_WE_USED_IBM_BOB.md`](HOW_WE_USED_IBM_BOB.md) for the full account.

## Prior work disclosure

Early exploratory work on the Kubernetes evidence layer predates the contest
window (files dated 2026-08-25; the contest opened 2026-08-28 10:00 ET). The
submitted architecture — the agent, the MCP contract, the human review loop,
the API, the dashboard and the test suite — was built during the contest, and
the git history shows it. We are flagging this rather than leaving it to be
found.

---

## Reproducing

```bash
git clone https://github.com/Edith-Stark06/Kubemedic.git
cd Kubemedic
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest                # 238 passed, no cluster or credentials needed
```

With a Kubernetes cluster, `README.md` has the demo steps and
`bash scripts/validate.sh` reproduces `evidence/validate-run.txt`.

Verified from a clean clone on 2026-08-30: 140 tracked files, no build
artifacts, 238 tests pass, and `mcp_server.server`, `agent.api` and
`dashboard.app` all import.
