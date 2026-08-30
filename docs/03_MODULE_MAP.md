# 03 — Module Map

Line counts are from `wc -l` on branch `shivraj/mcp-repo-ci` @ `1448908`.

---

## agent/ — Track 2, the real system

### `agent/models.py` (387 lines)

- **Purpose:** every data contract. Field names in `BobAnalysis` and
  `CorrelationResult` are frozen to mirror
  `.bob/skills/incident-correlation/references/evidence-schema.md`.
- **Inputs:** raw dicts from Bob; Python constructor calls.
- **Outputs:** `AllowedAction`, `TicketReference`, `EvidenceSnapshot`,
  `CorrelationResult`, `Hypothesis`, `RootCause`, `BobAnalysis`,
  `RemediationPlan`, `HumanDecision`, `ExecutionResult`, `VerificationResult`,
  `IncidentState`, `Incident`, `IncidentRecord`.
- **Dependencies:** pydantic v2 only.
- **Called by:** every other `agent/` module, all tests.
- **State:** none. Pure contracts.
- **Side effects:** none.
- **Tests:** `TestModelCreation`, `TestBobAnalysisValid`,
  `TestBobAnalysisMalformed`, `TestRemediationPlan`, `TestInvalidRemediation`.
- **Status:** **READY**.
- **Safety carriers:** `AllowedAction` (closed set of three);
  `_ILLEGAL_TRANSITIONS` blocking `REJECTED -> EXECUTING` and
  `FEEDBACK_RECORDED -> EXECUTING`; `HumanDecision._require_feedback_on_rejection`;
  `Incident.require_approval()`.

### `agent/bob.py` (386 lines)

- **Purpose:** the only module that knows how IBM Bob is invoked.
- **Inputs:** `evidence: dict`, `tickets: list[dict]`; env vars
  `KUBEMEDIC_BOB_API_KEY`, `KUBEMEDIC_BOB_AGENT_ID`, `KUBEMEDIC_BOB_API_BASE`,
  `KUBEMEDIC_BOB_MODE`, `KUBEMEDIC_BOB_TIMEOUT_SECONDS`.
- **Outputs:** `BobResult(ok, analysis, raw_stdout, invocation, duration_ms, error)`.
- **Dependencies:** stdlib only (`urllib`, `json`).
- **Called by:** `agent/reasoning.py` exclusively.
- **State:** none.
- **Side effects:** one or two outbound HTTPS POSTs.
- **Tests:** `test_analyze_no_key_returns_unavailable`.
- **Status:** **UNVERIFIED**. The code path is correct and the no-key path is
  tested, but no successful live response has ever been observed.
- **Notes:** `_build_argv()` deliberately returns `[]` — the module docstring
  records that IBM Bob v1.126.0 (`bobide`, Antigravity IDE) has no headless
  stdout mode, so the REST API is the only programmatic path. `_extract_json`
  and `_last_object` defensively parse a model response that may be wrapped or
  fenced.
- **UNKNOWN / NEEDS VERIFICATION:** the endpoint is `https://cloud.manufact.com`.
  Whether this is the sanctioned IBM Bob API for the contest is not established
  by anything in the repository. See `19_HACKATHON_COMPLIANCE.md`.

### `agent/reasoning.py` (78 lines)

- **Purpose:** bridge between the pipeline and Bob; validates Bob's output into
  `BobAnalysis`.
- **Inputs:** `Incident` (must have `evidence`).
- **Outputs:** `(Incident, BobAnalysis)`.
- **Called by:** `agent/pipeline.py`.
- **Side effects:** appends a `BobResult.audit_entry()` to `incident.audit_log`;
  transitions state to `ANALYSED` or `BOB_UNAVAILABLE`.
- **Tests:** `test_reasoning_on_bob_unavailable_does_not_fabricate`,
  `test_reasoning_on_malformed_output_does_not_fabricate`.
- **Status:** **READY** (logic), **UNVERIFIED** (against a live Bob).
- **Key property:** a Bob failure or a malformed response is never converted
  into a successful analysis. Both paths produce `analysis_source="unavailable"`.

### `agent/correlation.py` (138 lines)

- **Purpose:** deterministic N tickets to 1 incident.
- **Inputs:** `list[TicketReference]`, `EvidenceSnapshot`, optional incident id.
- **Outputs:** `(Incident, excluded_tickets)`.
- **Algorithm:** three signals — workload-name match, creation inside a
  7200-second window before evidence collection, and a symptom-keyword regex.
  A ticket joins the incident at **2 of 3**.
- **State:** module-level `_counter` for id generation (not thread-safe).
- **Tests:** `TestCorrelation` — `test_three_tickets_one_incident`,
  `test_unrelated_ticket_excluded`, `test_old_ticket_excluded`,
  `test_empty_tickets_list`.
- **Status:** **READY**.
- **Boundary concern:** this is Bob's advertised job done in Python.
  `PROMPT_TEMPLATE` in `bob.py` also asks Bob to correlate, and `BobAnalysis`
  carries its own `correlation` field. Two correlations are produced per
  incident and nothing reconciles them. See `06_AGENT_REASONING_FLOW.md`.

### `agent/pipeline.py` (155 lines)

- **Purpose:** stage sequencer; `plan_remediation()` plus `run_full_pipeline()`.
- **Inputs:** tickets, evidence, a `HumanDecision`, a `KubernetesClient`, an
  `EvidenceReader`.
- **Outputs:** terminal-state `Incident`.
- **Side effects:** writes a record when `persist=True`.
- **Tests:** `TestPipeline` — `test_happy_path_resolves`,
  `test_bob_unavailable_stops_pipeline`, `test_rejection_stops_before_execution`.
- **Status:** **READY** as a synchronous test/demo runner.
- **Design limit:** `run_full_pipeline` takes the human decision **as an
  argument up front**. It cannot pause for a real human. Any interactive
  review needs a stateful API layer that calls the stages individually. The
  docstring acknowledges this: *"the dashboard calls each stage individually
  through the API layer (not yet implemented)"*.

### `agent/executor.py` (149 lines)

- **Purpose:** perform exactly one allowlisted action after approval.
- **Inputs:** `Incident` in `APPROVED` state, a `KubernetesClient`.
- **Outputs:** `(Incident, ExecutionResult)`.
- **Guards:** `require_approval()`; idempotency (a second call on an
  `EXECUTED` incident returns the existing result); `_dispatch` raises on an
  unknown action.
- **Tests:** `TestExecutor` — 5 tests including
  `test_execute_without_approval_raises`,
  `test_rejected_to_executing_is_unreachable`,
  `test_second_execute_returns_existing_state`.
- **Status:** **PARTIAL** — logic READY, but `KubernetesClient` has no concrete
  implementation, so this has never mutated a real cluster.

### `agent/verification.py` (147 lines)

- **Purpose:** independent, dual-signal recovery confirmation.
- **Signals:** `rollout_healthy` (from `get_workload_status`) and
  `health_endpoint` (from `get_application_health`).
- **Outcomes:** `PASS` only when both signals pass; `INCONCLUSIVE` when a
  verification tool itself errored; otherwise `FAIL`.
- **Tests:** `TestVerification` — 6 tests including `test_tool_error_inconclusive`,
  `test_rollout_fail_does_not_resolve`, `test_health_fail_does_not_resolve`.
- **Status:** **PARTIAL** — logic READY, `EvidenceReader` has no concrete
  implementation.
- **Name dependency:** the protocol requires `get_workload_status` and
  `get_application_health`. `mcp_server/tools.py` names them
  `get_workload_state` and `get_app_health`. See `07_MCP_CONTRACT.md`.

### `agent/audit.py` (120 lines)

- **Purpose:** the human-decision gate and record persistence.
- **`record_decision()`:** requires state in `{ANALYSED, PENDING_APPROVAL}`;
  on rejection transitions `REJECTED` then `FEEDBACK_RECORDED` and writes two
  audit entries; on approval transitions `APPROVED`.
- **`write_record()`:** writes `records/<incident_id>.json`, never overwriting
  (appends a time suffix on collision).
- **Tests:** `TestAudit`, `TestRejectionPath` — 10 tests.
- **Status:** **READY**.

---

## mcp_server/ — the evidence and ticket layer

### `mcp_server/server.py` (194 lines)

- **Purpose:** stdio MCP server exposing ten tools.
- **Tools registered:** `get_workload_state`, `get_pods`, `get_events`,
  `get_recent_changes`, `get_app_health`, `get_full_snapshot`, `list_tickets`,
  `get_ticket`, `create_ticket`, `update_ticket_status`.
- **Side effects:** calls `init_db()` **at import time** — importing this
  module creates `data/kubemedic.db` as a side effect. Starts `KubeWatcher`
  inside `run()`.
- **Tests:** **MISSING**.
- **Status:** **PARTIAL**.
- **Gaps:** no `argparse`, so the `--profile evidence` argument in
  `.bob/mcp.json` is silently ignored (`docs/handoffs.md` #1). Tool
  results are returned as `str(result)` — a Python `repr`, not JSON, which is
  awkward for a model to parse. `handle_call_tool` catches every exception and
  returns it as text, so a tool failure looks like a successful call.

### `mcp_server/tools.py` (75 lines)

- **Purpose:** thin wrappers turning evidence models into dicts.
- **Dependencies:** `orchestrator.evidence` (Track 1), `mcp_server.tickets`.
- **Tests:** **MISSING**. **Status:** **PARTIAL** — this file is the
  architectural leak.

### `mcp_server/tickets.py` (119 lines)

- **Purpose:** SQLite ticket CRUD.
- **Tests:** **MISSING**.
- **Status:** **BROKEN**. `update_ticket()` evaluates `isinstance(value, Enum)`
  but `Enum` is never imported. Reproduced:
  `tickets.update_ticket(id, status='investigating')` raises
  `NameError: name 'Enum' is not defined`. Every scalar-field update fails.

### `mcp_server/models.py` (56 lines)

- **Purpose:** `Ticket`, `Alert`, `TicketSeverity`, `TicketStatus`; re-exports
  the evidence models from `orchestrator.evidence`.
- **Status:** **PARTIAL** — carries the Track 1 dependency. `TicketStatus` has
  eight values that do not map onto `agent.models.IncidentState`'s thirteen.

### `mcp_server/watcher.py` (95 lines)

- **Purpose:** poll every 15s; open one ticket per anomaly burst.
- **Anomaly rules:** rollout incomplete; any pod NotReady; restarts > 3;
  app health not 200. Suppresses duplicates by checking for existing
  open/investigating tickets on the same deployment.
- **Tests:** **MISSING**.
- **Status:** **UNVERIFIED**. `_check_anomalies()` is synchronous and performs
  blocking Kubernetes I/O inside an asyncio loop; it will stall the MCP server's
  event loop for the duration of each poll.
- **Design note:** the watcher creates exactly **one** ticket per burst, with
  all anomalies joined into the title. The many-to-one correlation story needs
  **several** tickets. Nothing in the repository produces multiple correlatable
  tickets from a real cluster.

### `mcp_server/db.py` (35 lines)

- SQLite connection and `init_db()`. Path:
  `<repo>/data/kubemedic.db`. **Status: READY**, but see `20_KNOWN_GAPS.md` —
  the database file is currently committed to git.

---

## orchestrator/ — Track 1 remnant

### `orchestrator/evidence.py` (312 lines)

- **Purpose:** typed, read-only Kubernetes inspection. The docstring states the
  safety contract: these tools never mutate cluster state.
- **Public functions:** `inspect_workload`, `inspect_pods`, `inspect_events`,
  `recent_changes`, `check_application_health`, `gather_evidence`, `collect`.
- **Models:** `ToolError`, `WorkloadState`, `PodState`, `EventItem`,
  `RevisionInfo`, `HealthResult`, `EvidenceSnapshot`.
- **Called by:** `mcp_server/tools.py`, `mcp_server/models.py`,
  `mcp_server/watcher.py`.
- **Tests:** **MISSING**.
- **Status:** **PARTIAL** — good code in the wrong package. It is the last live
  piece of Track 1 and the reason `orchestrator/` still exists on this branch.
- **Collision:** defines an `EvidenceSnapshot` that is **not**
  `agent.models.EvidenceSnapshot`. Any MCP-to-agent wiring needs an explicit
  adapter.

---

## dashboard/ — Track 1 era, mocked

### `dashboard/app.py` (629 lines)

- **Purpose:** FastAPI app serving the UI and a JSON API.
- **Endpoints:** see `11_API_CONTRACTS.md`.
- **State:** four module-level dicts — `_DETECTIONS`, `_WATCHER`, `_TICKETS`,
  `_MASTER_INCIDENTS`, plus `_COUNTER`. All in-memory; lost on restart; never
  synced with the SQLite ticket store.
- **Tests:** **MISSING**.
- **Status:** **BROKEN**.
  - Lines 17-18 import `agent.bob.BobAgent`, `agent.bob.Detection`,
    `agent.record.save_record` — none of which exist after the consolidation.
    The `except ImportError` silently sets `BobAgent = None`.
  - `/api/status` is commented `# Mock live cluster status`.
  - `/api/detect` fabricates three tickets with hand-written evidence,
    correlation summaries and signals.
  - `_decide()` writes a record whose entire `verification` block is derived
    from the boolean `approved`. Approving makes six named checks report
    "passed" without anything being checked.
  - `POST /api/reject` has no `feedback` field on `ApproveRejectBody`.
- **Contradicts:** `AGENTS.md` rule 1 (never fabricate evidence) and rule 3
  (never claim success without evidence).

### `dashboard/templates/index.html`

- Jinja2 shell; all data arrives via `fetch`. Contains two Gemini strings
  (lines 263, 834). **Status: PARTIAL.**

---

## Supporting

| Path | Purpose | Status |
|---|---|---|
| `k8s/deployment.yaml` | `ticket-booking`, 2 replicas, readiness on `/health`, `maxUnavailable: 0` | READY |
| `k8s/namespace.yaml`, `k8s/service.yaml` | Namespace `opspilot`, ClusterIP service | READY |
| `workload/app.py` (59 lines) | FastAPI demo app; `HEALTHY` env var drives `/health` | READY |
| `workload/Dockerfile` | Builds `ticketbooking:1.0` / `:1.1` | READY |
| `scripts/inject_incident.sh` | `kubectl set image` to `:1.1` | READY |
| `scripts/reset_healthy.sh` | Reverse | READY |
| `scripts/validate.sh` | E2E harness | **BROKEN** — hardcodes `/c/Users/shivraj/...` paths and calls `orchestrator/validate_incident.py`, absent from this repo |
| `.bob/` (21 files) | Modes, skills, personas, rules, `mcp.json` | READY |
| `AGENTS.md` | Standing instructions for Bob sessions | READY |
| `tests/` (968 lines) | 62 tests, all targeting `agent/` | READY |
