# 08 — Human Review

## Intended behaviour

```
PROPOSED PLAN
      |
HUMAN FINAL REVIEW
      |-- APPROVE --> EXECUTE --> VERIFY --> RESOLVED
      |
      +-- REJECT --> feedback REQUIRED
                        |
                   store feedback
                        |
              feed into next reasoning cycle
                        |
                    revised plan
                        |
                HUMAN FINAL REVIEW  (loop)
```

**Approve** may be direct: the reviewer has read the proposed action and
accepts it.

**Reject must require feedback.** A rejection without a reason must be
refused by the API, not merely discouraged in the UI.

---

## What is implemented

### The model layer — correct and tested

`agent/models.py:HumanDecision` has a `model_validator` that raises when
`decision == "rejected"` and `feedback` is empty or whitespace. Constructing
an invalid rejection is impossible.

`_ILLEGAL_TRANSITIONS` blocks `REJECTED -> EXECUTING` and
`FEEDBACK_RECORDED -> EXECUTING` at the `Incident.transition()` level. Even a
caller that ignored every other guard could not execute a rejected plan.

`Incident.require_approval()` raises unless state is exactly `APPROVED`, and
`executor.execute()` calls it before doing anything.

`agent/audit.py:record_decision()` requires the incident to be in `ANALYSED`
or `PENDING_APPROVAL`, writes a `human_decision` audit entry, and on rejection
writes a second `rejection_recorded` entry with `executed: False` before
transitioning to `FEEDBACK_RECORDED`.

`IncidentRecord.rejection_feedback` persists the reason into the durable
record, but only when the decision was a rejection.

Tests (all passing): `test_human_decision_rejected_requires_feedback`,
`test_empty_feedback_on_reject_raises_422_equivalent`,
`test_human_decision_rejected_with_feedback_ok`,
`test_human_decision_approved_no_feedback_ok`,
`test_rejection_stops_before_execution`,
`test_rejected_to_executing_is_unreachable`,
`test_illegal_transition_rejected_to_executing`,
`test_rejection_feedback_persisted_in_audit_log`,
`test_rejected_record_contains_feedback`,
`test_rejection_sets_executed_false_in_record`,
`test_valid_feedback_transitions_to_feedback_recorded`,
`test_decision_on_wrong_state_raises`.

**This is the best-covered behaviour in the repository.**

### The HTTP layer — absent or wrong

There is no API over `agent/`. The only HTTP surface is
`dashboard/app.py`, which:

- Defines `ApproveRejectBody` as `{ticket_id, master_incident_id?, approver?}`.
  **There is no `feedback` field.** A rejection reason cannot be transmitted.
- Routes both `POST /api/approve` and `POST /api/reject` into the same
  `_decide()`, which flips a boolean.
- Never constructs a `HumanDecision`, so none of the validation above runs.
- On rejection writes a record with `outcome: "blocked_awaiting_approval"` and
  `execution.executed: False` — the *right shape*, with none of the enforcement.

### The feedback loop — not implemented

Feedback is stored and never read. `PROMPT_TEMPLATE` has no slot for it;
`run_analysis()` takes no feedback argument; `run_full_pipeline` returns as
soon as the incident is rejected. See `05_CONTEXT_MODEL.md` and
`06_AGENT_REASONING_FLOW.md`.

---

## Target API contract

Not yet implemented. Proposed for `14_INTEGRATION_PLAN.md` Phase 5.

```http
POST /incidents/{incident_id}/review
Content-Type: application/json
```

**Approval**

```json
{ "decision": "APPROVED", "approver": "shivraj" }
```

`200 OK` — incident moves to `APPROVED`; execution may then be triggered.

**Rejection**

```json
{
  "decision": "REJECTED",
  "approver": "shivraj",
  "feedback": "Investigate the recent deployment before restarting the service."
}
```

`200 OK` — incident moves to `REJECTED` then `FEEDBACK_RECORDED`; feedback
persisted; **no execution occurs**.

**Rejection without feedback**

```json
{ "decision": "REJECTED", "approver": "shivraj" }
```

```http
HTTP 400
{ "error": "feedback_required",
  "detail": "A rejection must state why. Feedback is added to the incident context and sent to IBM Bob for the revised plan." }
```

> FastAPI would naturally return `422` for a pydantic validation failure. The
> brief specifies `400` with an explicit `feedback_required` code, which is
> clearer for the UI. Implement it as an explicit check that raises
> `HTTPException(400, ...)` before model construction, so the code is stable
> and the message is ours. The existing test is named
> `test_empty_feedback_on_reject_raises_422_equivalent` — deliberately
> "equivalent", because at model level it is a `ValidationError`.

---

## State vocabulary

`agent.models.IncidentState` (13 values, implemented):

| State | Meaning | Set by |
|---|---|---|
| `OPEN` | Created, no evidence | default |
| `EVIDENCE_COLLECTED` | Evidence attached | `correlate()` |
| `EVIDENCE_FAILED` | Collection failed | **never set** |
| `ANALYSED` | Bob returned a valid analysis | `run_analysis()` |
| `BOB_UNAVAILABLE` | Bob down or output invalid | `run_analysis()` |
| `PENDING_APPROVAL` | Plan built, awaiting human | `plan_remediation()` |
| `APPROVED` | Human approved | `record_decision()` |
| `REJECTED` | Human rejected | `record_decision()` |
| `FEEDBACK_RECORDED` | Reason stored; terminal today | `record_decision()` |
| `EXECUTING` | Action in flight | `execute()` |
| `EXECUTED` | Action returned | `execute()` |
| `VERIFIED` | — | **never set** |
| `RESOLVED` | Both verification signals passed | `verify()` |
| `VERIFICATION_FAILED` | Verification did not pass | `verify()` |

Mapping to the vocabulary in the brief:

| Brief | Implementation |
|---|---|
| `APPROVED` | `APPROVED` |
| `REJECTED` | `REJECTED` then immediately `FEEDBACK_RECORDED` |
| `REVISION_REQUESTED` | **No equivalent.** Would be the state after feedback is fed back to Bob |
| `EXECUTING` | `EXECUTING` |
| `VERIFYING` | **No equivalent** — verification is synchronous inside `verify()` |
| `RESOLVED` | `RESOLVED` |

Two dead states exist: `EVIDENCE_FAILED` and `VERIFIED`. `VERIFIED` is
skipped because `verify()` goes straight to `RESOLVED`. Either wire them or
delete them — a judge reading the enum will ask. Task `MODEL-001`.

`mcp_server.models.TicketStatus` is a *third*, unrelated vocabulary
(`open`, `investigating`, `pending_approval`, `approved`, `executing`,
`resolved`, `blocked`, `closed`) with no mapping to `IncidentState`.
Task `MODEL-002`.

---

## UI requirement

The dashboard must make the rejection reason **mandatory in the UI and
enforced by the server**. A client-side `required` attribute is not the
control; the server check is. The reason should then be visible on the
incident afterwards, so a reviewer can see why a previous plan was rejected
before judging the revised one.
