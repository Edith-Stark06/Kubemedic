# 04 — Runtime Flow

Two flows exist. **Flow A** is what `agent/` does and what the tests exercise.
**Flow B** is what a person actually sees if they run the dashboard. They share
no code.

---

## Flow A — the agent pipeline (real, tested, has no UI)

Entry point: `agent.pipeline.run_full_pipeline(tickets, evidence,
human_decision, kubernetes, reader)`. Today the only callers are
`tests/test_lifecycle.py`.

| # | Step | Code | Function | Input | Output | State transition |
|---|---|---|---|---|---|---|
| 1 | Healthy state | `k8s/deployment.yaml` | — | `ticketbooking:1.0` | 2/2 ready | — |
| 2 | Failure introduced | `scripts/inject_incident.sh` | — | `kubectl set image :1.1` | Pods NotReady, rollout stalls | — |
| 3 | Evidence available | `orchestrator/evidence.py` | `collect()` | namespace, deployment, service | `EvidenceSnapshot` (Track 1 type) | — |
| 4 | Tickets generated | `mcp_server/watcher.py` | `_check_anomalies()` | polled cluster state | one SQLite `Ticket` | — |
| 5 | Agent invoked | `agent/pipeline.py:104` | `run_full_pipeline()` | tickets + evidence | — | — |
| 6 | Correlation | `agent/correlation.py:31` | `correlate()` | `list[TicketReference]`, `EvidenceSnapshot` | `Incident`, excluded | `OPEN` to `EVIDENCE_COLLECTED` |
| 7 | Reasoning | `agent/reasoning.py:24` | `run_analysis()` | `Incident` | `BobAnalysis` | to `ANALYSED` or `BOB_UNAVAILABLE` |
| 7a | Bob call | `agent/bob.py:221` | `analyze()` | evidence dict, ticket dicts | `BobResult` | — |
| 7b | Bob REST | `agent/bob.py:131` | `_rest_analyze()` | prompt | JSON analysis | — |
| 8 | Plan | `agent/pipeline.py:41` | `plan_remediation()` | `BobAnalysis` | `RemediationPlan` | to `PENDING_APPROVAL` |
| 9 | Human decision | `agent/audit.py:35` | `record_decision()` | `HumanDecision` | updated `Incident` | to `APPROVED`, or `REJECTED` then `FEEDBACK_RECORDED` |
| 10 | Execution | `agent/executor.py:52` | `execute()` | `Incident` + `KubernetesClient` | `ExecutionResult` | `APPROVED` to `EXECUTING` to `EXECUTED` |
| 11 | Verification | `agent/verification.py:45` | `verify()` | `Incident` + `EvidenceReader` | `VerificationResult` | to `RESOLVED` or `VERIFICATION_FAILED` |
| 12 | Audit | `agent/audit.py:107` | `write_record()` | terminal `Incident` | `records/<id>.json` | — |

### Where Flow A stops early

```
BOB_UNAVAILABLE      -> write record, return.  No plan, no execution.
plan is None         -> write record, return.  Bob recommended null.
REJECTED             -> write record, return.  Execution never reached.
execution failed     -> write record, return.  Verification never reached.
```

Each early exit still produces an audit record. That is deliberate: a rejected
or failed incident is as much a fact as a resolved one.

### Steps 3-4 to steps 5-6: the missing join

Step 4 writes a `Ticket` (from `mcp_server/models.py`) into SQLite. Step 6
expects `TicketReference` objects (from `agent/models.py`). Step 3 produces a
Track 1 `EvidenceSnapshot`; step 6 expects the Track 2 `EvidenceSnapshot`.
**No code converts either.** In the tests, the fixtures construct Track 2
objects directly. This is the single largest integration gap.

### Steps 10-11: the missing cluster

`execute()` calls `kubernetes.rollback_deployment(...)` on an injected
`KubernetesClient`. `verify()` calls `reader.get_workload_status(...)` on an
injected `EvidenceReader`. Neither protocol has a concrete implementation in
the repository. In the tests both are fakes. **The executor has never mutated
a cluster and the verifier has never read one.**

---

## Flow B — the dashboard (what a person actually sees)

| # | Step | Code | Reality |
|---|---|---|---|
| 1 | Open `/` | `dashboard/app.py:47` | Renders `index.html` |
| 2 | Poll status | `/api/status` | Hardcoded. Comment: `# Mock live cluster status` |
| 3 | Click detect | `POST /api/detect` | Fabricates `TKT-1` CrashLoopBackOff, `TKT-2` payment-service timeout, `TKT-3` frontend-gateway 502, plus their evidence, correlation summary and signals — all literals in `app.py` |
| 4 | View correlation | `_MASTER_INCIDENTS` | Grouping is hardcoded, not computed |
| 5 | Click approve | `POST /api/approve` | `_decide(body, approved=True)` |
| 6 | Click reject | `POST /api/reject` | `_decide(body, approved=False)`. **No feedback is requested, accepted, or stored** |
| 7 | Record written | `_decide()` | `verification.passed = approved`; six named checks all report the value of that boolean |
| 8 | Verification | — | **Nothing is verified.** No cluster call is made |

Flow B never imports a working `agent` symbol, never calls Bob, never touches
Kubernetes, and never reads the SQLite ticket store.

> A judge following the demo sees Flow B and concludes the system works. The
> audit record it writes asserts that six verification checks passed. Under
> `AGENTS.md` rule 3 that record is a false claim of success. This is the
> reason `P0-1` is ranked first in `00_PROJECT_STATUS.md`.

---

## Flow C — the intended flow after integration

```
healthy cluster
   -> inject_incident.sh
   -> watcher opens tickets in SQLite
   -> API: POST /incidents  (collect evidence via MCP, adapt to agent types)
   -> correlate()                     N tickets -> 1 incident
   -> run_analysis() -> IBM Bob       evidence in, structured analysis out
   -> plan_remediation()              -> PENDING_APPROVAL
   -> dashboard renders the plan, the reasoning and the evidence
   -> human clicks REJECT with a reason
        -> feedback persisted on the incident
        -> feedback added to the next Bob prompt
        -> revised plan -> PENDING_APPROVAL again
   -> human clicks APPROVE
        -> executor performs one allowlisted action through the K8s API
   -> verify() re-reads the cluster on two independent signals
   -> RESOLVED, record written to records/
```

The bold-line difference from Flow A: an **API layer holding incident state
between requests**, so the pipeline can genuinely pause at the approval gate
instead of receiving the decision up front. See `14_INTEGRATION_PLAN.md`
Phase 5.
