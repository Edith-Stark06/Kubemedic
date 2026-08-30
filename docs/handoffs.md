# Handoffs — KubeMedic

Cross-owner change requests from Ramana. Each item names the owner, the file,
the change needed, and why. Status tracked here; Ramana messages the owner
directly.

Cross-owner change requests. Each item names the owner, the file, the change
needed, and why. Status tracked here; authors message owners directly.

---

## #1 — MCP server `--profile evidence` flag [BLOCKING]

**Owner:** Shivraj  
**File:** `mcp_server/server.py` (or equivalent entry point)  
**Status:** OPEN  

### What is needed

The project MCP configuration (`.bob/mcp.json`) launches the evidence server
with:

```
python -m mcp_server.server --profile evidence
```

and sets the environment variable `KUBEMEDIC_MCP_PROFILE=evidence`.

The `--profile evidence` flag (or equivalent mechanism) must restrict the
server's exposed tool surface to **read-only tools only**:

```
get_workload_status
get_pods
get_events
get_application_health
get_workload_snapshot
list_tickets
get_ticket
```

**No mutation tool may be exposed on this profile.** Specifically, none of
`rollback_deployment`, `restart_deployment`, or `scale_workload` must appear
in the tool list returned to Bob under this profile.

### Why this is blocking

The project's central safety claim — "Bob has no tool that can change the
cluster" — is verified by reading `.bob/mcp.json`. If the MCP server ignores
the `--profile` flag and exposes action tools regardless, the claim collapses.
This is both a correctness requirement and a contest compliance requirement.

The judge's ten-second verification is: open `mcp.json`, see
`--profile evidence`, confirm no mutation tool is registered. If the server
ignores the flag, a judge who checks the running tool surface finds the claim
false.
### What Ramana supplies

- `.bob/mcp.json` already written with the `--profile evidence` args and env.
- The allowlisted read-only tool names are listed above.
- The mutation tools (`rollback_deployment`, `restart_deployment`,
  `scale_workload`) live in `agent/executor.py` (Ramana's lane), imported
  directly, never exposed to Bob.

### How to verify once implemented

```bash
# Start the server with the profile flag
python -m mcp_server.server --profile evidence &

# Confirm read tools are accessible
# Confirm mutation tools are absent from the tool list
```

Alternatively, run the `gemini-audit` skill in `kubemedic-auditor` mode —
it checks the tool surface as part of the compliance sweep.

---

## #2 — HTTP API layer for the dashboard [BLOCKING for Verona's lane]

**Owner:** Ramana  
**File:** `agent/` — new file, e.g. `agent/api.py` or `agent/main.py`  
**Requested by:** Verona  
**Status:** OPEN  

### What is needed

`agent/pipeline.py` documents: *"the dashboard calls each stage individually
through the API layer (not yet implemented)"*. No HTTP server exists in `agent/`.
The dashboard cannot call the pipeline without one.

Minimum surface needed:

| Method | Path | Request body | Response |
|---|---|---|---|
| `GET` | `/incidents` | — | List of incidents (id, state, workload, created_at) |
| `GET` | `/incidents/{id}` | — | Full `Incident` as JSON |
| `POST` | `/incidents/{id}/decision` | `{decision, approver, feedback}` | Updated `Incident` |
| `GET` | `/incidents/{id}/record` | — | `IncidentRecord` as JSON |

**Critical field name:** The rejection body field must be `feedback` (matching
`HumanDecision.feedback` in `agent/models.py`). The dashboard will send this
exact name. If the API renames it, the server returns 422 silently.

### Why this is blocking

Without this API, the dashboard can be built and demonstrated against mock data
only. The end-to-end incident lifecycle — including the human review gate and
the recorded rejection — cannot be wired up for the final recording without it.

### Verification

```bash
curl http://localhost:8000/incidents
curl http://localhost:8000/incidents/INC-501
curl -X POST http://localhost:8000/incidents/INC-501/decision \
  -H "Content-Type: application/json" \
  -d '{"decision": "rejected", "approver": "verona", "feedback": "deliberate maintenance rollout"}'
# Expect: incident state transitions to FEEDBACK_RECORDED, feedback stored verbatim
```

---

## #3 — Confirm `IncidentState` enum value for "awaiting human review" [BLOCKING for Verona's lane]

**Owner:** Ramana  
**File:** `agent/models.py`  
**Requested by:** Verona  
**Status:** OPEN  

### What is needed

The `incident-ui-flow` skill and the prompt use `AWAITING_HUMAN_REVIEW` and
`PLAN_PROPOSED` as state names. The actual `IncidentState` enum uses
`PENDING_APPROVAL` for both. The dashboard must use the real enum value as
returned by the API.

Please confirm:
1. `PENDING_APPROVAL` is the single state where the approve/reject controls
   should appear — and that no separate `AWAITING_HUMAN_REVIEW` state will be
   added later.
2. There is no `VERIFYING` state — verification runs synchronously and the
   transition goes `EXECUTED → RESOLVED` or `EXECUTED → VERIFICATION_FAILED`.
   The dashboard should not poll for a `VERIFYING` intermediate state.

If either answer is "we will add that state", please notify Verona before
adding it so the display-label map can be updated in the same commit.

### Why this matters

If Ramana adds a state after the dashboard ships, all undefined states will
render as a blank badge or "Unknown" — visible on camera. Agreeing the closed
set now avoids that.

---

*Add further handoffs below as work progresses.*
