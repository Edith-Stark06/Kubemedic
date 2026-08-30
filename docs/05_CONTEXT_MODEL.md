# 05 — Context Model

What context exists, where it is produced, and — critically — **whether the
implementation actually passes it on**. A field that exists in a model but is
never populated is marked as such.

---

## Operational context

Produced by `orchestrator/evidence.py`. All read-only.

| Context | Model | Fields | Reaches the agent? |
|---|---|---|---|
| Deployment state | `WorkloadState` | namespace, name, image, revision, desired/ready/available/updated/unavailable replicas, observed_generation, conditions, healthy, rollout_complete | **No** — no adapter exists |
| Pod state | `PodState` | name, phase, ready, restarts, image, reason, message, deletion_timestamp, terminating | **No** |
| Events | `EventItem` | type, reason, message, count, object, last_seen | **No** |
| Deployment history | `RevisionInfo` | revision, image, created, change_cause, ready_replicas, is_current | **No** |
| Service health | `HealthResult` | status_code, healthy, body, error | **No** |
| Combined | `orchestrator.evidence.EvidenceSnapshot` | all of the above | **No** |

The agent's own `EvidenceSnapshot` (`agent/models.py:45`) has a *different*
shape: `collected_at`, `deployment_name`, `namespace`, `pod_states`, `events`,
`rollout_history`, `application_health`, `raw`. In the tests it is constructed
by hand.

> **The `raw` field is never populated by anything.** It exists as an escape
> hatch and is empty in every code path.

---

## Ticket context

Two incompatible ticket representations exist.

### `mcp_server/models.py:Ticket` — persisted in SQLite

`id`, `title`, `status`, `severity`, `namespace`, `deployment`, `service`,
`created_at`, `updated_at`, `signals[]`, `related_ticket_ids[]`,
`diagnosis{}`, `plan{}`, `resolution{}`.

`TicketStatus`: `open`, `investigating`, `pending_approval`, `approved`,
`executing`, `resolved`, `blocked`, `closed`.

### `agent/models.py:TicketReference` — what the agent consumes

`ticket_id`, `title`, `reported_symptom`, `named_workload`, `created_at`,
`severity`. All optional except `ticket_id`.

### Mapping — none exists

| `Ticket` field | `TicketReference` field | Mapped by |
|---|---|---|
| `id` | `ticket_id` | **nothing** |
| `title` | `title` | **nothing** |
| `signals[]` | `reported_symptom` (a single string) | **nothing** — lossy, needs a join rule |
| `deployment` | `named_workload` | **nothing** |
| `created_at` (str) | `created_at` (datetime) | **nothing** — needs parsing |
| `severity` | `severity` | **nothing** |
| `diagnosis`, `plan`, `resolution` | no equivalent | — |
| `related_ticket_ids` | no equivalent (superseded by `CorrelationResult`) | — |

Correlation depends on `named_workload` and `created_at`. Both are optional on
`TicketReference` and default to `None`. **A ticket adapted carelessly — losing
`created_at` or `named_workload` — scores at most 1 of 3 correlation signals
and is silently excluded from its own incident.** This is the highest-risk
detail in the whole integration.

---

## Incident context

`agent/models.py:Incident` is the container that flows through the pipeline.

| Field | Populated by | Present? |
|---|---|---|
| `incident_id` | `correlate()` | Yes |
| `state` | `transition()` | Yes |
| `tickets[]` | `correlate()` — members only | Yes |
| `evidence` | caller | Yes in tests, **never in production** |
| `correlation` | `correlate()` | Yes |
| `analysis` | `run_analysis()` | Yes |
| `plan` | `plan_remediation()` | Yes |
| `human_decision` | `record_decision()` | Yes |
| `execution` | `execute()` | Yes |
| `verification` | `verify()` | Yes |
| `audit_log[]` | every stage appends | Yes |

Excluded tickets are returned from `correlate()` as a separate value and are
recorded in `correlation.excluded_tickets`, but the *objects* are dropped by
`run_full_pipeline` — only their ids survive.

### Audit log entries actually written

| `step` / `stage` | Written by |
|---|---|
| `correlation` | `correlate()` |
| `BOB` | `BobResult.audit_entry()` via `run_analysis()` |
| `plan` | `plan_remediation()` |
| `human_decision` | `record_decision()` |
| `rejection_recorded` | `record_decision()`, rejection path only |
| `execute` / `execute_result` | `execute()` |
| `verification` | `verify()` |

The audit log is append-only and is copied verbatim into `IncidentRecord`.

---

## Agent (Bob) context — exactly what is sent

From `agent/bob.py:PROMPT_TEMPLATE`, the prompt contains **only**:

1. A one-line instruction naming the `incident-correlation` skill.
2. `<evidence>` — `json.dumps(incident.evidence.model_dump(mode="json"))`.
3. `<open_tickets>` — the **member** tickets, dumped from `TicketReference`.
4. The allowlist, stated literally: `rollback_deployment`,
   `restart_deployment`, `scale_workload`, with permission to recommend null.
5. A pointer to the output schema and "no prose, no markdown fences".

### What is NOT sent

| Context | Sent? | Consequence |
|---|---|---|
| System / role context | **No** — carried by `KUBEMEDIC_BOB_MODE` and `.bob/` server-side | Depends on the mode existing in the Bob workspace |
| Excluded tickets | **No** | Bob cannot say "you wrongly excluded this one" |
| The deterministic `CorrelationResult` | **No** | Bob correlates from scratch, unaware of the Python result |
| Previous hypotheses | **No** | Every call is stateless |
| Human feedback | **No** | **This is the gap that blocks the rejection loop** |
| Prior incidents | **No** | No cross-incident learning |
| Cluster topology beyond the one deployment | **No** | Single-workload scope |

### The human-feedback gap, precisely

`HumanDecision.feedback` is captured, validated as mandatory on rejection,
written to `audit_log`, and persisted in `IncidentRecord.rejection_feedback`.

It is then **never read by anything**. `PROMPT_TEMPLATE` has no slot for it,
`run_analysis()` takes no feedback parameter, and `run_full_pipeline` returns
immediately after a rejection.

So the rejection path is currently:

```
REJECT + reason -> stored -> incident ends
```

and the target in the orchestrator brief is:

```
REJECT + reason -> stored -> added to Bob's context -> revised plan -> review again
```

The storage half is done and tested. The feedback-into-reasoning half does not
exist. See task `REVIEW-002`.

---

## Context that exists only in the dashboard

`_DETECTIONS`, `_TICKETS`, `_MASTER_INCIDENTS`, `_COUNTER` — module-level
dicts in `dashboard/app.py`. In-memory, lost on restart, never persisted, never
read by the agent, never synced with SQLite. Their contents are literals
authored in `app.py`, not observations.
