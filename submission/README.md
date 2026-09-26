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
| Video demonstration (≤ 3 min, ≥ 90 s of the solution running) | — | **Not yet recorded** |
| Demo application platform and URL | — | **Not yet hosted** |
| Cover image, slide deck, tags | — | **Not yet made** |

## Evidence

Everything in [`evidence/`](evidence/) was produced by running the code.

| File | What it shows |
|---|---|
| `pytest-run.txt` | The suite at the time of an earlier run. Re-run `python -m pytest` for the current count |
| `validate-run.txt` | **34 assertions, 0 failures, against a live kind cluster, reasoned by IBM Bob** |
| `INC-20260926T205136-001.json` | The audit record from that run. `analysis_source: "ibm-bob"` |
| `INC-20260926T192815-001.json` | An earlier record, same engine, against the fixture cluster |
| other `INC-*.json` | Earlier records; `analysis_source` reads `unavailable` or `fixture` |

### What the live record shows, and does not

`INC-20260926T205136-001.json` is `scripts/validate_incident.py` end to end
against a real cluster (kind), fallback disabled: the watcher observes the
injected failure and files real tickets, IBM Bob reasons over the live evidence
and proposes `rollback_deployment`, a human rejects it without a reason (refused),
rejects it with one (recorded, cluster unchanged), Bob is asked again and
proposes the same action, a human approves, the executor performs a real
rollback restoring the full pod template, and both recovery signals pass on a
re-read of the cluster.

**What it does not show:** in this run Bob's first proposal was already the
correct one, so the human's objection did not change the recommended action —
only that the loop executes and Bob answers again. It is not evidence that a
rejection can steer Bob toward a different action; the earlier fixture-cluster
record (`INC-20260926T192815-001.json`) shows that instead, with a scripted
objection that names a specific alternative.

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
