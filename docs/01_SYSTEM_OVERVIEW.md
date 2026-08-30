# 01 — System Overview

## What is OpsPilot / KubeMedic?

Both names are in use for one project. `AGENTS.md`, `.bob/`, `agent/` and the
tests say **KubeMedic**. `orchestrator/evidence.py`, the `opspilot` namespace,
`dashboard/app.py` and `scripts/` say **OpsPilot**. Pick one before
submission — see `20_KNOWN_GAPS.md`.

From `AGENTS.md`, which is the clearest statement in the repository:

> A Kubernetes incident-response proof of concept. It gathers operational
> evidence through an MCP server, uses IBM Bob to correlate multiple symptoms
> into a single incident and reason about the cause, proposes an impact-aware
> remediation, **pauses for a human decision**, executes only an allowlisted
> action after approval, and independently verifies that the service actually
> recovered.
>
> It is not an autonomous healing platform. Do not describe it as one.

The distinguishing claim is not automation. It is **discipline**: evidence is
never fabricated, inference is labelled as inference, no mutation happens
without a recorded human approval, and no recovery is claimed without
re-reading the cluster.

---

## The intended flow, and what actually implements it

| Stage | Implementation | Status |
|---|---|---|
| Problem | `ticket-booking` deployment on Kubernetes goes bad | `k8s/`, `workload/` |
| Inputs | Bad image `ticketbooking:1.1` shipped by `scripts/inject_incident.sh` | Present |
| Evidence collection | `orchestrator/evidence.py` via `mcp_server/tools.py` | Present, misnamed |
| Ticket generation | `mcp_server/watcher.py` polls and opens tickets | Present, untested |
| Correlation | `agent/correlation.py` — deterministic, N tickets to 1 incident | Present, tested |
| Reasoning | `agent/reasoning.py` to `agent/bob.py` to IBM Bob REST | Present, never observed live |
| Remediation proposal | `plan_remediation()` in `agent/pipeline.py` | Present, tested |
| Human review | `agent/audit.py:record_decision()` | Model-layer only |
| Execution | `agent/executor.py` | Present, tested against fakes only |
| Verification | `agent/verification.py`, two signals | Present, tested against fakes only |
| Closure | `agent/audit.py:write_record()` to `records/*.json` | Present, tested |

**Everything above describes `agent/`.** The dashboard implements none of it —
see `02_ARCHITECTURE.md`.

---

## The failure scenario the project is built around

`k8s/deployment.yaml` is deliberately designed so the demo failure is clean
and reversible. Comments in the manifest state the reasoning:

- `maxUnavailable: 0` — old healthy pods keep serving when a new revision is
  bad, so a regression appears as a *stuck rollout*, not an outage.
- The readiness probe hits the app's `/health`; the bad image bakes
  `HEALTHY=false` so `/health` returns 503 and the pod goes NotReady.
- Liveness is a plain TCP check, so a bad `/health` does **not** crash-loop the
  pod. It stays Running-but-NotReady — a clean readiness regression.

`scripts/inject_incident.sh` ships `ticketbooking:1.1` and annotates the
change cause. `scripts/reset_healthy.sh` reverses it.

> **Note the inconsistency:** the manifest produces a *readiness regression*.
> `dashboard/app.py:149` fabricates a *CrashLoopBackOff* storm across three
> services (`ticket-booking`, `payment-service`, `frontend-gateway`), two of
> which do not exist in `k8s/`. The demo the UI shows and the demo the cluster
> produces are different incidents.

---

## What a new engineer should read first

1. `AGENTS.md` — the four rules and the AI boundary.
2. `agent/models.py` — every contract in the system.
3. `agent/pipeline.py` — the stage sequence in 155 lines.
4. `tests/test_lifecycle.py` — the behaviour that is actually guaranteed.
5. This documentation set, starting at `00_PROJECT_STATUS.md`.
