# 23 — System Workflow

The complete picture: every module, what it owns, and how one incident moves
through all of them.

**Verified 2026-08-30 at `bc63c46`** — 282 tests pass; `scripts/validate.sh`
passes 29 assertions against a live k3s cluster.

---

## The one-sentence version

Kubernetes breaks → MCP collects evidence → tickets are filed → they correlate
into one incident → a reasoning provider explains it → **a human decides** →
one allowlisted action runs → recovery is verified independently → an audit
record is written.

---

## Layer map

```
┌──────────────────────────────────────────────────────────────────────┐
│  dashboard/          the human's window                              │
│    app.py            incident console                                │
│    api_adapter.py    the ONE seam to the agent (Real | Mock)         │
└───────────────────────────────┬──────────────────────────────────────┘
                                │ HTTP
┌───────────────────────────────▼──────────────────────────────────────┐
│  agent/              THE COORDINATOR — owns the lifecycle            │
│    api.py            HTTP surface, holds incident state              │
│    pipeline.py       stage sequencer + request_revision()            │
│    correlation.py    N tickets → 1 incident (deterministic)          │
│    reasoning.py      the single reasoning boundary                   │
│    models.py         every contract, the allowlist, the state machine│
│    executor.py       post-approval mutation, allowlisted only        │
│    verification.py   two independent signals                         │
│    audit.py          the approval gate + durable records             │
│    adapters.py       MCP types → agent types                         │
│    k8s_client.py     the ONLY module that changes a cluster          │
│    secrets.py        every credential goes through here              │
│    providers/        pluggable reasoning engines                     │
└─────────┬──────────────────────────────────┬─────────────────────────┘
          │                                  │
┌─────────▼────────────────┐   ┌─────────────▼────────────────────────┐
│  mcp_server/  READ-ONLY  │   │  providers/                          │
│    server.py  11 tools   │   │    ibm-bob    IBM Bob REST  (default)│
│    tools.py              │   │    watsonx    IBM watsonx.ai         │
│    evidence.py  k8s reads│   │    anthropic  Claude (dev/fallback)  │
│    tickets.py   SQLite   │   │    manual     interactive Bob session│
│    watcher.py   anomalies│   │    base.py    ONE failure policy      │
│    incidents.py history  │   │    prompt.py  ONE prompt              │
└──────────────────────────┘   │    parsing.py ONE JSON extractor      │
                               └──────────────────────────────────────┘
```

### The two rules that hold the design up

**1. MCP is passive.** It answers questions. It has no loop, no state, no plan,
and no tool that can change the cluster. `rollback_deployment`,
`restart_deployment` and `scale_workload` are not MCP tools at any profile —
they live in `agent/executor.py` behind the approval gate. The safety claim
*"Bob has no tool that can change the cluster"* is true by construction, and CI
asserts it on every push.

**2. `agent/` coordinates.** Not MCP, not the model. The pipeline decides what
happens next; the model only supplies an opinion, and the human supplies the
authority.

---

## One incident, end to end

### 1 · Failure

`scripts/inject_incident.sh` ships `ticketbooking:1.1` — the same source as
`:1.0`, built with `HEALTHY=false`.

`k8s/deployment.yaml` is built so this is legible: readiness probes `/ready`,
which fails; liveness is a plain TCP check, so the pod does **not** crash-loop
— it sits `Running` but `0/1 Ready`; and `maxUnavailable: 0` keeps the old pods
serving, so the rollout **stalls** rather than causing an outage.

### 2 · Evidence — `mcp_server/evidence.py`

Read-only Kubernetes inspection: workload status, pods, events, ReplicaSet
revision history, application health through the Service proxy. Cluster errors
become structured values, never exceptions and never silence.

### 3 · Tickets — `mcp_server/watcher.py`

Polls every 15s and files **one ticket per distinct anomaly signal** — rollout
stalled, pod not ready, restart threshold, health failing — deduplicated per
signal kind. One real failure yields two or three real tickets, which is what
makes the next step mean anything.

### 4 · Correlation — `agent/correlation.py`

Deterministic Python, not a model call. A ticket joins on **2 of 3** signals:
workload name matches the evidence, created inside the 2-hour window, symptom
keywords match. Produces a `CorrelationResult` with `correlation_basis` — plain
English reasons each ticket joined.

> Bob is *also* asked to correlate and the two results are not reconciled.
> Open decision: `docs/21_DECISIONS.md` ADR-007.

### 5 · Reasoning — `agent/reasoning.py` → `agent/providers/`

The single boundary. `KUBEMEDIC_REASONING_PROVIDER` selects the engine; nothing
downstream knows which answered.

Bob receives the correlated evidence, the member tickets, the allowlist stated
literally, and — on a revision — the human's rejection reasons. It returns one
JSON object: ranked hypotheses with confidence and **both** supporting and
contradicting evidence, a root cause labelled as inference, a timeline, and one
allowlisted action or null.

**The failure policy is the important part.** No credentials, auth rejected,
timeout, unreachable, unparseable, schema violation — all converge on
`analysis_source: "unavailable"`, and the incident stops before a plan exists.
The system reports the outage rather than inventing a diagnosis.

### 6 · Plan — `agent/pipeline.py:plan_remediation`

A mechanical copy from the validated analysis. No new authority is created
here. State → `PENDING_APPROVAL`.

### 7 · Human review — `agent/audit.py` + `agent/api.py`

```
PENDING_APPROVAL
   ├── APPROVE ──────────────────► APPROVED
   └── REJECT (reason REQUIRED) ─► REJECTED → FEEDBACK_RECORDED
                                       │
                                  reason → Bob's next prompt
                                       │
                                  revised plan → PENDING_APPROVAL
                                  (capped at MAX_REVISIONS = 3)
```

Three independent layers enforce it: `HumanDecision` refuses to construct
without a reason; the API returns `400 feedback_required`; and
`_ILLEGAL_TRANSITIONS` makes `REJECTED → EXECUTING` structurally unreachable.

The reason is not a formality — it becomes the context Bob uses to produce a
different plan.

### 8 · Execution — `agent/executor.py` + `agent/k8s_client.py`

`require_approval()` raises unless the state is exactly `APPROVED`. `_dispatch`
maps an `AllowedAction` enum member to a typed Kubernetes API call. **No shell,
no kubectl subprocess, no string a model composed.** Names are validated
against RFC 1123; `scale_workload` is bounded, because an unbounded replica
count from model output is a denial of service.

### 9 · Verification — `agent/verification.py`

Re-reads the cluster on **two independent signals**: the control plane's view
of the rollout, and the application answering HTTP through the Service.
`PASS` only if both pass. `INCONCLUSIVE` is checked first, so "we could not
tell" is never reported as "it did not work". Neither is ever softened to
`PASS`, and the execution API's own response is never accepted as proof.

> **Why two signals, concretely.** In every live run the application health
> endpoint returned **200 throughout the incident**, because `maxUnavailable: 0`
> kept the healthy old pods serving. Health alone would have missed the failure
> entirely. The rollout signal caught it.

### 10 · Audit — `agent/audit.py`

`records/<incident_id>.json`, never overwritten: which tickets, what the
provider concluded, `analysis_source`, who decided and why, the full feedback
history, what executed, and how recovery was verified.

---

## The reasoning provider layer

```
KUBEMEDIC_REASONING_PROVIDER ──► registry ──► provider.analyze()
                                                    │
                          ┌─────────────────────────┴──────────┐
                          │  BaseProvider.analyze()            │
                          │    is_configured?  ──► unavailable │
                          │    build_prompt()   (ONE prompt)   │
                          │    _invoke()        (per provider) │
                          │    extract_json()   (ONE parser)   │
                          │    stamp provenance                │
                          └────────────────────────────────────┘
```

| Provider | Needs | Notes |
|---|---|---|
| `ibm-bob` | API key + agent id | **Default.** Endpoint unverified |
| `watsonx` | IAM key + project id + URL + model | IAM token cached with its expiry |
| `anthropic` | `sk-ant-...` | Dev/fallback. A Claude Code login is **not** this |
| `manual` | an analysis file | **No credentials.** Bob reasons interactively in the workspace |

Providers own the transport and nothing else. The prompt, the JSON extraction,
the failure policy, the provenance stamp and the usage counters are shared — so
19 parity tests can assert that four engines behave identically on success,
fenced output, prose-wrapped output, three transport failures, missing
credentials, and a non-allowlisted action.

**Secrets** resolve through `agent/secrets.py` — `env`, `file` (`/run/secrets`),
`k8s` Secret, or `vault` as a documented adapter point. No value is ever logged
or returned by a health endpoint.

---

## Interfaces

| Surface | Where | Notes |
|---|---|---|
| MCP stdio, 11 read-only tools | `mcp_server/server.py` | `--profile evidence` enforced; CI asserts no mutation tool |
| Agent HTTP API | `agent/api.py` | 8 routes + aliases + `/api/provider` |
| Dashboard | `dashboard/app.py` | Real via `KUBEMEDIC_AGENT_BASE_URL`, mock without |
| CLI harness | `scripts/validate.sh` | 29 assertions, exit non-zero on any failure |
| Bob ingest | `scripts/ingest_bob_analysis.py` | Interactive session → real audit record |

---

## Test coverage

| Suite | Tests | Covers |
|---|---|---|
| `test_agent_contracts` + `test_lifecycle` | 62 | Contracts, states, safety guards |
| `test_provider_parity` | 19 | Four engines behaving identically |
| `test_k8s_client` | 29 | Rollback/restart/scale guards |
| `test_api` | 28 | Every route; no route bypasses a guard |
| `test_secrets_and_incident_tools` | 25 | Redaction, path traversal, read-only |
| `test_adapters` | 25 | The type join and the correlation hazard |
| `test_review_loop` | 19 | Reject → revise → review, and its safety |
| `test_mcp_contract` | 18 | Tool names, evidence profile read-only |
| `test_watcher` | 13 | One ticket per signal, dedup |
| `test_tickets` | 12 | Ticket store |
| `test_ingest_bob_analysis` | 10 | Provenance and allowlist guards |
| `test_dashboard_agent_integration` | 7 | The real dashboard↔agent seam |
| `dashboard/tests` | 15 | UI adapter and rendering |
| **Total** | **282** | |

---

## What is verified, and what is not

**Verified against a live cluster:** evidence collection, ticket generation,
many-to-one correlation, the approval refusal (with the cluster asserted
unchanged), the reasonless-rejection refusal, real rollback through the
Kubernetes API, dual-signal verification, audit records, the dashboard↔agent
seam, and live provider switching.

**Not verified:** a live IBM Bob or watsonx model call. No credentials are
provisioned, so every record reads `analysis_source: "unavailable"`. The
harness substitutes an operator-specified plan **and labels it as such**. The
`manual` provider closes this the moment someone runs the Bob session in
`SHIVRAJ_DOCS/08_BOB_RUNBOOK.md` — it needs no credentials.

That distinction is the point of the whole design. A system that invents a
diagnosis when its reasoner is unreachable is more dangerous than one that says
nothing, and ours refusing to is tested rather than asserted.
