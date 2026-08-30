# 10 — Remediation and Verification

## Allowed mutations

`agent/models.py:AllowedAction` is a closed enum of three:

| Action | Parameters | Reversible |
|---|---|---|
| `rollback_deployment` | `to_revision` (optional) | Yes |
| `restart_deployment` | none | Yes |
| `scale_workload` | `replicas` (required, `int()`-cast) | Yes |

Nothing else can be executed. **Implemented and tested.**

---

## Safety controls — status of each

| Control | Where | Implemented | Test |
|---|---|---|---|
| Closed action allowlist | `AllowedAction` | **Yes** | `test_allowed_action_enum` |
| Bob output outside allowlist rejected before parsing | `BobAnalysis.from_raw` | **Yes** | `test_action_enum_rejects_arbitrary_string` |
| A `kubectl ...` string is rejected as an action | same | **Yes** | `test_action_enum_rejects_kubectl_string` |
| Action requires a target | `_check_action_target` validator | **Yes** | `test_action_without_target_rejected` |
| Execution requires `APPROVED` | `Incident.require_approval()` | **Yes** | `test_execute_without_approval_raises` |
| `REJECTED -> EXECUTING` impossible | `_ILLEGAL_TRANSITIONS` | **Yes** | `test_illegal_transition_rejected_to_executing` |
| `FEEDBACK_RECORDED -> EXECUTING` impossible | same | **Yes** | `test_rejected_to_executing_is_unreachable` |
| Idempotent execution | `execute()` early return | **Yes** | `test_second_execute_returns_existing_state` |
| No shell, ever | `_dispatch` maps enum to typed calls | **Yes** | by construction — no `subprocess`/`os.system` in `agent/executor.py` |
| Unknown action raises | `_dispatch` fallthrough | **Yes** | `test_unknown_action_rejected` |
| Cluster failure captured, not raised | `execute()` try/except | **Yes** | `test_cluster_failure_captured_not_raised` |
| Bob has no mutation tool | `.bob/mcp.json` + `server.py` | **Yes, but unenforced** | MISSING — see `07_MCP_CONTRACT.md` Gap 2 |

`git grep` for `subprocess`, `os.system`, `eval` or `exec` in `agent/` returns
only `agent/bob.py`'s unused `subprocess` import (a documented remnant of the
abandoned CLI path). **No model-composed command can reach a shell.**

---

## The approval boundary

```
BobAnalysis (recommendation only, requires_human_approval defaults True)
      |
RemediationPlan.from_analysis()   -- mechanical copy, no new authority
      |
state = PENDING_APPROVAL
      |
record_decision(HumanDecision)    -- the only way past this line
      |
state = APPROVED
      |
execute()  -- calls require_approval() first
```

`BobAnalysis.requires_human_approval` defaults to `True` and is asserted by
`test_requires_human_approval_always_true`. Note it is a *declaration*, not
the enforcement — the enforcement is `require_approval()` plus the illegal
transitions. That is the right design: the guard does not trust a field that
came from the model.

---

## Verification

`agent/verification.py:verify()` re-reads the cluster through `EvidenceReader`.

**Signal 1 — `rollout_healthy`**

```python
ws.get("ready") is truthy AND (
    ws.get("updated_replicas") == ws.get("desired_replicas")
    OR ws.get("available_replicas", 0) >= ws.get("desired_replicas", 1)
)
```

**Signal 2 — `health_endpoint`**

```python
health.get("status_code") == 200 OR health.get("healthy") is True
```

**Outcome rules**

| Condition | Outcome | State |
|---|---|---|
| A reader call raised | `INCONCLUSIVE` | `VERIFICATION_FAILED` |
| Both signals passed | `PASS` | `RESOLVED` |
| Otherwise | `FAIL` | `VERIFICATION_FAILED` |

`INCONCLUSIVE` is checked **first**, so a tool error can never be reported as
`FAIL` — a distinction that matters, since "we could not tell" is different
from "it did not work". Neither is ever softened to `PASS`.

Tests: `test_both_signals_pass_resolves`, `test_rollout_fail_does_not_resolve`,
`test_health_fail_does_not_resolve`, `test_tool_error_inconclusive`,
`test_verify_on_wrong_state_raises`, `test_verification_written_to_audit_log`.

**Dual-signal independence.** The two signals come from different sources: one
from the Kubernetes control plane's view of the rollout, one from the
application answering an HTTP request through the Service. A rollback that
satisfies the controller but leaves the app broken fails signal 2. That
independence is the point.

---

## Audit record

`IncidentRecord` (`agent/models.py:334`), written by `write_record()` to
`records/<incident_id>.json`, never overwriting.

Fields: `incident_id`, `final_state`, `tickets[]`, `correlation`,
`analysis_source`, `bob_analysis` (full snapshot), `root_cause`,
`recommended_action`, `human_decision`, `rejection_feedback`, `executed`,
`verification_outcome`, `created_at`, `resolved_at`, `audit_log[]`.

`analysis_source` is `ibm-bob`, `unavailable`, or `none` — so the record
always states whether Bob actually reasoned. `executed` is
`execution is not None and execution.success`, so a failed execution records
`executed: false`. `resolved_at` is set only for terminal states.

Tests: `test_incident_record_from_incident`, `test_write_record_creates_file`,
`test_no_overwrite_on_duplicate`, `test_record_is_valid_incident_record`.

---

## What is NOT implemented — read this before claiming remediation works

**There is no `KubernetesClient` implementation.** `git grep
rollback_deployment` across the repository finds the Protocol declaration in
`agent/executor.py`, the three dispatch branches, the allowlist string in the
Bob prompt, three strings in `dashboard/app.py`, and test fakes. **Nothing
else.** No module anywhere calls `AppsV1Api.patch_namespaced_deployment` or
equivalent.

**There is no `EvidenceReader` implementation.** `orchestrator/evidence.py`
has `inspect_workload` and `check_application_health`, which return
`WorkloadState` and `HealthResult` **pydantic models**. The protocol expects
methods named `get_workload_status` / `get_application_health` returning
**dicts** with keys `ready`, `updated_replicas`, `desired_replicas`,
`available_replicas`, `status_code`, `healthy`.

Field-level check of that adapter:

| Verifier expects | `WorkloadState` has | OK? |
|---|---|---|
| `ready` | `healthy` / `rollout_complete` | needs mapping — **name differs** |
| `updated_replicas` | `updated_replicas` | yes |
| `desired_replicas` | `desired_replicas` | yes |
| `available_replicas` | `available_replicas` | yes |

| Verifier expects | `HealthResult` has | OK? |
|---|---|---|
| `status_code` | `status_code` | yes |
| `healthy` | `healthy` | yes |

So verification needs a thin adapter with one genuine decision: which
`WorkloadState` field means `ready`. `rollout_complete` is the honest choice —
`healthy` is a broader claim. Task `VER-001`.

The executor needs a real implementation written from scratch — roughly 60
lines against `kubernetes.client.AppsV1Api`. Task `EXEC-001`.

**Until both land, the sentence "OpsPilot remediates and verifies" is not
true of any code path that has ever run.** The tests prove the logic is
correct given a working client; they do not prove a working client exists.
