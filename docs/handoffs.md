# Handoffs — KubeMedic

Cross-owner change requests from Ramana. Each item names the owner, the file,
the change needed, and why. Status tracked here; Ramana messages the owner
directly.

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

*Add further handoffs below as work progresses.*
