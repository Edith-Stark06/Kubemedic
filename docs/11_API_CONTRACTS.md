# 11 — API Contracts

## Summary

There is exactly one HTTP surface in the repository: `dashboard/app.py`
(FastAPI, `uvicorn` on `0.0.0.0:8000`). **It does not expose `agent/`.**
There is no API over the pipeline. Nothing outside a Python process can drive
correlation, reasoning, approval, execution or verification.

---

## Implemented endpoints — `dashboard/app.py`

| Method | Path | Purpose | Request | Response | Errors | State change |
|---|---|---|---|---|---|---|
| GET | `/` | UI shell | — | HTML | — | none |
| GET | `/api/health` | Liveness | — | `{status, service}` | — | none |
| GET | `/api/status` | "Cluster status" | — | workload + app_health | — | none |
| POST | `/api/watcher/start` | Flip a flag | — | `{status:"started"}` | — | `_WATCHER` |
| POST | `/api/watcher/stop` | Flip a flag | — | `{status:"stopped"}` | — | `_WATCHER` |
| GET | `/api/watcher/status` | Read the flag | — | `_WATCHER` | — | none |
| GET | `/api/tickets` | Tickets grouped by master incident | — | list of `master_incident` / `ticket` objects | — | none |
| GET | `/api/tickets/{id}` | One ticket | — | ticket | 404 | none |
| POST | `/api/detect` | "Detect" an incident | — | tickets + master incident | — | `_TICKETS`, `_MASTER_INCIDENTS`, `_DETECTIONS` |
| POST | `/api/approve` | Approve | `ApproveRejectBody` | record | 404 | ticket status, writes a record file |
| POST | `/api/reject` | Reject | `ApproveRejectBody` | record | 404 | ticket status, writes a record file |
| GET | `/api/records` | List records | — | up to 50 summaries | — | none |
| GET | `/api/records/{id}` | One record | — | record JSON | 400, 404 | none |

`ApproveRejectBody`: `{ticket_id: str, master_incident_id: str | None,
approver: str = "web-ui"}`. **No `feedback` field.**

### Endpoint-level defects

**`/api/status`** — the comment says `# Mock live cluster status`. It returns a
workload named `payment-service` with a `us-docker.pkg.dev` image — neither
appears in `k8s/`. The demo cluster runs `ticket-booking` on
`ticketbooking:1.0`.

**`/api/watcher/*`** — sets a boolean. It does not start, stop or communicate
with `mcp_server/watcher.py:KubeWatcher`. A judge clicking "start watcher"
starts nothing.

**`/api/detect`** — 340 lines of literal ticket, evidence, correlation and
signal data. No cluster read, no Bob call.

**`/api/approve` and `/api/reject`** — both call `_decide()`. The record it
writes contains a `verification` block whose six named checks each report the
value of the `approved` boolean. Approving asserts that
`rollout_complete`, `all_replicas_ready`, `no_suspect_image_pods`,
`app_health_200`, `payment_service_recovered` and
`frontend_gateway_recovered` all passed. **Nothing was checked.**

**`/api/records`** — reads `RECORDS_DIR`. Because the `agent.record` import
fails, `RECORDS_DIR` falls back to `<repo>/agent/records`. `agent/audit.py`
writes to `<repo>/records`. **The dashboard reads a directory the agent never
writes to.** Even if the paths were joined, this endpoint reads
`d.get("outcome")`, a key `IncidentRecord` does not have — it has
`final_state`. Every agent record would list as `outcome: "unknown"`.

**`/api/records/{id}`** — the one piece of genuine input validation in the
file: rejects ids not starting with `INC-` and containing `/` or `\`. Good
path-traversal guard; keep it.

---

## Dashboard to backend calls

`templates/index.html` fetches only the endpoints above. It never calls the
MCP server and never reaches `agent/`.

---

## Agent to external calls

| Caller | Target | Method | Auth |
|---|---|---|---|
| `agent/bob.py:_rest_analyze` | `POST {BOB_API_BASE}/api/v1/chats` | HTTPS | `x-api-key` |
| `agent/bob.py:_rest_analyze` | `POST {BOB_API_BASE}/api/v1/chats/{id}/execute` | HTTPS | `x-api-key` |

Default base `https://cloud.manufact.com`. Body of the second call:
`{"query": <prompt>, "max_steps": 20}`. Timeouts 30s and
`KUBEMEDIC_BOB_TIMEOUT_SECONDS` respectively.

> **UNKNOWN / NEEDS VERIFICATION.** The docstring says this protocol was read
> out of the IDE extension's `RemoteAgent` class. Nothing in the repository
> establishes that `cloud.manufact.com` is the sanctioned IBM Bob API for this
> contest. See `19_HACKATHON_COMPLIANCE.md`.

## MCP tool surface

Not HTTP. stdio JSON-RPC — see `07_MCP_CONTRACT.md`.

---

## Proposed API over the agent — not implemented

Needed to make the human-review gate real. Phase 5 of `14_INTEGRATION_PLAN.md`.

| Method | Path | Purpose | Request | Response |
|---|---|---|---|---|
| POST | `/incidents` | Collect evidence, correlate, analyse, plan | `{namespace, deployment, service}` | `Incident` in `PENDING_APPROVAL` or `BOB_UNAVAILABLE` |
| GET | `/incidents` | List | — | summaries |
| GET | `/incidents/{id}` | Full incident: evidence, correlation, Bob analysis, hypotheses, root cause, plan | — | `Incident` |
| POST | `/incidents/{id}/review` | The approval gate | `{decision, approver, feedback?}` | updated `Incident` |
| POST | `/incidents/{id}/execute` | Execute after approval | — | `ExecutionResult` |
| GET | `/incidents/{id}/record` | Audit record | — | `IncidentRecord` |
| GET | `/tickets` | Real tickets from SQLite | `status?` | `[Ticket]` |

Contract details for `/review` — including the mandatory `400
feedback_required` on a rejection without a reason — are in
`08_HUMAN_REVIEW.md`.

**Design constraint.** `run_full_pipeline()` takes the human decision as an
argument, so it cannot serve this API. The API must call the stages
individually — `correlate()`, `run_analysis()`, `plan_remediation()`,
`record_decision()`, `execute()`, `verify()` — and hold the `Incident` between
requests. An in-process dict keyed by `incident_id` is sufficient for the
demo; state loss on restart should be an accepted, documented limitation
rather than an unnoticed one.
