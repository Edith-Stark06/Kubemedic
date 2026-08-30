# 09 — Ticket and Incident Model

## The seven entities

| Entity | Model | Cardinality | Persisted where |
|---|---|---|---|
| **Ticket** | `mcp_server.models.Ticket` | many per incident | SQLite `data/kubemedic.db` |
| **Ticket reference** | `agent.models.TicketReference` | many per incident | in-memory, inside `Incident` |
| **Incident** | `agent.models.Incident` | one per correlated group | in-memory only |
| **Correlation** | `agent.models.CorrelationResult` | one per incident (x2 — see below) | inside `Incident` and `IncidentRecord` |
| **Hypothesis** | `agent.models.Hypothesis` | many per analysis, ranked | inside `BobAnalysis` |
| **Root cause** | `agent.models.RootCause` | zero or one per analysis | inside `BobAnalysis` |
| **Remediation plan** | `agent.models.RemediationPlan` | zero or one per incident | inside `Incident` |
| **Review** | `agent.models.HumanDecision` | one per incident today | inside `Incident` |
| **Execution** | `agent.models.ExecutionResult` | zero or one | inside `Incident` |
| **Verification** | `agent.models.VerificationResult` | zero or one, with N signals | inside `Incident` |
| **Audit event** | plain `dict` | many, append-only | `Incident.audit_log`, copied to `IncidentRecord` |

---

## Relationships

```
Ticket A (SQLite) --+
Ticket B (SQLite) --+--> [no adapter] --> TicketReference x3
Ticket C (SQLite) --+                            |
                                                 v
                                        correlate()  (2-of-3 signals)
                                                 |
                                                 v
                                    Incident  INC-<ts>-<n>
                                                 |
        +----------------+----------------+------+--------+-----------------+
        |                |                |               |                 |
   evidence        correlation        analysis          plan          human_decision
 EvidenceSnapshot  CorrelationResult  BobAnalysis   RemediationPlan   HumanDecision
                                          |                                |
                                   hypotheses[] (ranked)             feedback (req. on reject)
                                   root_cause
                                   timeline[]
                                   correlation  <-- Bob's own, duplicate
                                                 |
                                        +--------+--------+
                                        |                 |
                                    execution        verification
                                 ExecutionResult  VerificationResult
                                                        |
                                                    signals[]
                                            rollout_healthy, health_endpoint
                                                 |
                                                 v
                                          IncidentRecord --> records/<id>.json
```

Note the **two** `CorrelationResult` values per incident — one computed by
`agent/correlation.py`, one returned inside `BobAnalysis`. See
`06_AGENT_REASONING_FLOW.md` Violation 1.

---

## Ticket vs Incident — the distinction that carries the demo

A **ticket** is a *reported symptom*. It is what a human or a monitor noticed:
"payment-service is timing out". Tickets are cheap, numerous, and each one is
a partial view.

An **incident** is a *single underlying failure*. It is inferred, not
reported. Three tickets describing three symptoms of one bad deployment are
one incident.

The many-to-one mapping is the project's headline claim:

```
Ticket #101  checkout returns 502   --+
Ticket #102  payment timeouts        --+--> Master Incident INC-...-001
Ticket #103  ticket-booking NotReady --+     root cause: revision 3 image regression
```

### The problem with the demo as it stands

`mcp_server/watcher.py:_check_anomalies()` creates **exactly one ticket per
anomaly burst**. It gathers every anomaly it finds into a single title
(`"Anomaly detected in ticket-booking: Rollout not complete, Pod X is
NotReady"`) and creates one ticket, then suppresses further tickets while any
open or investigating ticket exists for that deployment.

So a real cluster run produces **one** ticket. Correlating one ticket into one
incident demonstrates nothing.

`dashboard/app.py` solves this by fabricating three tickets across three
services — but two of those services (`payment-service`, `frontend-gateway`)
do not exist in `k8s/`, and the tickets are literals, not observations.

**To make the many-to-one story true rather than staged, one of these must
happen:**

1. Deploy the two additional services in `k8s/` so a real cascade occurs, and
   change the watcher to emit one ticket per distinct anomaly rather than one
   per burst. Most honest, most work.
2. Change the watcher to emit one ticket per anomaly *signal* on the single
   deployment (rollout stalled / pod NotReady / health 503). Three real
   tickets from one real failure, all observed. Cheapest true option.
3. Seed tickets through `create_ticket` in a documented demo fixture, clearly
   labelled as seeded and not presented as detection.

Recommended: **(2)**, then **(3)** as the presenter's fallback if the cluster
misbehaves during the video. Task `TICKET-001`.

---

## Lifecycle mapping

| Ticket status (SQLite) | Incident state (agent) | Kept in sync by |
|---|---|---|
| `open` | `OPEN` / `EVIDENCE_COLLECTED` | **nothing** |
| `investigating` | `ANALYSED` | **nothing** |
| `pending_approval` | `PENDING_APPROVAL` | **nothing** |
| `approved` | `APPROVED` | **nothing** |
| `executing` | `EXECUTING` | **nothing** |
| `resolved` | `RESOLVED` | **nothing** |
| `blocked` | `FEEDBACK_RECORDED`? | **nothing** |
| `closed` | — | **nothing** |

The two vocabularies are close enough to look intentional and are wired
together nowhere. When an incident resolves, its member tickets stay `open` in
SQLite forever. Task `TICKET-002`.

---

## Identity

- Ticket ids: `TKT-<YYYYmmdd-HHMMSS-ffffff>` from
  `mcp_server/tickets.py:_generate_ticket_id`.
- Incident ids: `INC-<YYYYmmddTHHMMSS>-<counter:03d>` from
  `agent/correlation.py:_new_id`, where `_counter` is a **module-level global**.
  It resets on process restart, so ids repeat across runs within the same
  second. Not thread-safe. Acceptable for a demo, worth a note. Task `MODEL-003`.
- Dashboard ids: `TKT-1`, `TKT-2`, ... from `_COUNTER`, and
  `INC-<unix-timestamp>`. A third scheme, incompatible with both.
