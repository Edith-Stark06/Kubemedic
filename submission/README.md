# Submission — IBM Bob 2.0 Hackathon

**Project:** KubeMedic — evidence-driven Kubernetes incident response with a
human in the loop

## Deliverables

| Deliverable | Where | Status |
|---|---|---|
| Public code repository | this repository | **Make public before submitting** |
| Problem and solution statement (≤ 500 words) | [`PROBLEM_AND_SOLUTION.md`](PROBLEM_AND_SOLUTION.md) | Written |
| IBM Bob usage statement (≤ 500 words) | [`HOW_WE_USED_IBM_BOB.md`](HOW_WE_USED_IBM_BOB.md) | Written |
| IBM Bob task-session summary screenshots, each member | [`bob-report/`](bob-report/) | **Not yet captured** |
| Video demonstration (≤ 3 min, ≥ 90 s of the solution running) | script: [`VIDEO_SCRIPT.md`](VIDEO_SCRIPT.md) | **Script ready; not yet recorded** |
| Demo application platform and URL | — | **Not yet hosted** |
| Cover image, slide deck, tags | — | **Not yet made** |

## Evidence

Everything in [`evidence/`](evidence/) was produced by running the code.

| File | What it shows |
|---|---|
| `pytest-run.txt` | The suite at the time of an earlier run. Re-run `python -m pytest` for the current count |
| `validate-run-runbook.txt` | **34 assertions, 0 failures, live kind cluster, IBM Bob citing a real operational runbook** |
| `INC-20260926T213503-001.json` | The audit record from that run. `analysis_source: "ibm-bob"` |
| `validate-run.txt` | An earlier live-cluster run, same engine, no runbook |
| `INC-20260926T205136-001.json` | The audit record from that earlier run |
| `INC-20260926T192815-001.json` | An earlier record, same engine, against the fixture cluster |
| other `INC-*.json` | Earlier records; `analysis_source` reads `unavailable` or `fixture` |

### Document understanding: the headline record

`INC-20260926T213503-001.json` is `scripts/validate_incident.py` end to end
against a real cluster (kind), fallback disabled — plus one addition:
`docs/RUNBOOK_TICKET_BOOKING.md`, a real operational playbook naming known
failure classes and which of the three allowed actions the team prefers for
each, handed to Bob in its own fenced prompt section (`agent/runbook.py`,
`agent/providers/prompt.py`) alongside the cluster evidence.

Bob's `reason` field in that record:

> "The playbook explicitly names this failure class (Failure Class 1: readiness
> regression immediately following a deployment) and mandates
> rollback_deployment rather than restart_deployment, because a restart would
> recreate pods on the same broken image and reproduce the identical probe
> failures."

That is Bob naming the document and its specific rule, not just describing
what the cluster evidence shows. The rest of the loop is unchanged from the
earlier live run: watcher-filed tickets, an unapproved-execution refusal, a
reasonless rejection refused, a rejection with a reason recorded and answered,
approval, a real rollback restoring the full pod template, both recovery
signals passing on a re-read of the cluster.

**What it does not show:** Bob's proposal was already correct both before and
after the human's rejection here, so this run does not show the objection
changing the recommended action. `INC-20260926T192815-001.json` (fixture
cluster, no runbook) shows that instead, with a scripted objection naming a
specific alternative that Bob's revised plan follows.

## Prior work disclosure

KubeMedic was started on 2026-08-28 for an earlier hackathon and its git history
shows that. This event's window added: target validation, authentication and
roles, durable state with a hash-chained audit trail, full-template rollback,
prompt fencing, deployment manifests with least-privilege RBAC, and the Bob 2.0
headless integration. We are flagging this rather than leaving it to be found.
Confirm with the organizers that resubmission is permitted.

## Reproducing

```bash
git clone <this repository> && cd Kubemedic
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest        # no cluster or credentials needed
python scripts/dry_run.py --non-interactive
```

A live cluster run is `bash scripts/validate.sh`.
