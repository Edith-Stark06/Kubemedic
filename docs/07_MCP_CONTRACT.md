# 07 — MCP Contract

Source: `mcp_server/server.py` (registration and dispatch),
`mcp_server/tools.py` (implementations), `.bob/mcp.json` (client config).

Transport: stdio JSON-RPC via `mcp.server.stdio.stdio_server`.
Server name `kubemedic`, version `0.1.0`.

---

## Registered tools

| # | Tool | Read/Mutate | Inputs | Output | Backed by | Tests |
|---|---|---|---|---|---|---|
| 1 | `get_workload_state` | Read | `namespace`, `deployment` | `WorkloadState` dict | `inspect_workload` | MISSING |
| 2 | `get_pods` | Read | `namespace`, `deployment` | `{pods: [PodState]}` | `inspect_pods` | MISSING |
| 3 | `get_events` | Read | `namespace`, `deployment`, `limit` | `{events: [EventItem]}` | `inspect_events` | MISSING |
| 4 | `get_recent_changes` | Read | `namespace`, `deployment` | `{revisions: [RevisionInfo]}` | `recent_changes` | MISSING |
| 5 | `get_app_health` | Read | `namespace`, `service` | `HealthResult` dict | `check_application_health` | MISSING |
| 6 | `get_full_snapshot` | Read | `namespace`, `deployment`, `service` | `EvidenceSnapshot` dict | `collect` | MISSING |
| 7 | `list_tickets` | Read | `status?` | `{tickets: [Ticket]}` | SQLite | MISSING |
| 8 | `get_ticket` | Read | `ticket_id` (req) | `Ticket` dict | SQLite | MISSING |
| 9 | `create_ticket` | **Mutates store** | `title`, `severity`, `namespace`, `deployment`, `service`, `signals` (all req) | `Ticket` dict | SQLite | MISSING |
| 10 | `update_ticket_status` | **Mutates store** | `ticket_id`, `status` (req), `detail?` | `Ticket` dict | SQLite | **BROKEN** |

**No tool mutates the cluster.** `rollback_deployment`, `restart_deployment`
and `scale_workload` are not registered here — they exist only as the
`KubernetesClient` protocol in `agent/executor.py`, behind the approval gate.
The safety claim in `.bob/mcp.json` is therefore **true today**, but true by
accident of what was written rather than by any enforcement mechanism.

---

## Gap 1 — three tool names do not match their consumers

| Registered in `server.py` | Expected by `.bob/mcp.json` | Expected by `agent/verification.py:EvidenceReader` |
|---|---|---|
| `get_workload_state` | `get_workload_status` | `get_workload_status` |
| `get_app_health` | `get_application_health` | `get_application_health` |
| `get_full_snapshot` | `get_workload_snapshot` | — |
| `get_pods` | `get_pods` | — |
| `get_events` | `get_events` | — |
| `get_recent_changes` | *(absent from allowlist)* | — |
| `list_tickets`, `get_ticket` | same | — |
| `create_ticket`, `update_ticket_status` | *(absent from allowlist)* | — |

Two independent consumers agree on `get_workload_status` and
`get_application_health`. The server is the outlier. **Rename the server's
tools**, do not change the config or the protocol. Task `MCP-001`.

Note also that `get_recent_changes` is not in the `alwaysAllow` list, yet
rollout history is the single most diagnostic signal for a bad-deploy
incident. Either add it to the allowlist or accept that Bob must ask
permission for it. Task `MCP-004`.

---

## Gap 2 — `--profile evidence` is not implemented

`.bob/mcp.json` launches:

```
python -m mcp_server.server --profile evidence
```

with `KUBEMEDIC_MCP_PROFILE=evidence`.

`mcp_server/server.py` contains no `argparse`, no `sys.argv` read, and no
reference to `KUBEMEDIC_MCP_PROFILE`. Verified by grep. The flag is accepted
by the interpreter and ignored.

Consequence today: `create_ticket` and `update_ticket_status` — both store
mutations — are exposed on a profile documented as read-only. The `//safety`
key in `mcp.json` says *"READ ONLY. There is deliberately no mutation server
registered here."*

A judge's ten-second check is to open `mcp.json`, see `--profile evidence`,
and confirm the surface. That check currently passes only because no cluster
mutation tool was ever written. It does not pass on the ticket tools.

This is `docs/handoffs.md` #1, marked BLOCKING. Task `MCP-002`.

**Intended behaviour:** with `--profile evidence`, `handle_list_tools` returns
exactly the seven allowlisted read tools, and `handle_call_tool` refuses
anything outside that set. Without the flag, the full ten.

---

## Gap 3 — MCP depends on Track 1

```
mcp_server/models.py:6   from orchestrator.evidence import (...)
mcp_server/tools.py:4    from orchestrator.evidence import (...)
mcp_server/watcher.py:3  from orchestrator.evidence import (...)
```

Current dependency direction:

```
Kubernetes -> orchestrator/evidence.py -> mcp_server -> (nothing)
                                              agent -> Bob
```

Intended:

```
Kubernetes -> mcp_server (evidence inside it) -> agent -> Bob -> agent -> dashboard
```

`orchestrator/evidence.py` is good code; the problem is only its package. The
cheapest correct fix is to move it to `mcp_server/evidence.py` and update the
three imports — no logic changes, and `orchestrator/` then disappears from
this branch entirely. Task `MCP-003`.

---

## Gap 4 — `update_ticket_status` is broken

`mcp_server/tickets.py:update_ticket()` reaches `isinstance(value, Enum)` on
its `elif` branch, but the module never imports `Enum`. Reproduced directly:

```
tickets.update_ticket(ticket_id, status='investigating')
NameError: name 'Enum' is not defined
```

Every scalar-field update fails — status, title, severity. Only list/dict
fields (`signals`, `diagnosis`, `plan`, `resolution`, `related_ticket_ids`)
take the first branch and survive. Fix is one import line. Task `MCP-005`.

---

## Gap 5 — result serialisation and error masking

`handle_call_tool` returns `[{"type": "text", "text": str(result)}]`.
`str()` on a dict yields Python `repr` — single quotes, `True`/`False`/`None` —
which is not JSON and which a model must guess at. Should be
`json.dumps(result)`. Task `MCP-006`.

The same function wraps every call in `try/except` and returns
`f"Error: {e}"` as a normal text result. A failed tool call is therefore
indistinguishable from a successful one at the protocol level. Under
`AGENTS.md` rule 1 — never fabricate evidence, say so when a tool failed —
this should surface as an MCP error, or at minimum as a structured
`{"error": ...}` payload. Task `MCP-007`.

Note that `tools.py` *already* returns `{"error": str(e)}` for evidence tools,
so an evidence failure is double-wrapped: `str({"error": "..."})`.

---

## Dependency summary

| Direction | Status |
|---|---|
| MCP to `orchestrator/` | **Present — architectural leak.** Three files |
| MCP to Kubernetes | Via `orchestrator/evidence.py` only. Correct shape, wrong package |
| MCP to ticketing | `mcp_server/tickets.py` to SQLite. Self-contained |
| MCP to `agent/` | **None.** Correct — MCP must not depend on the agent |
| `agent/` to MCP | **None.** **This is the missing integration**, task `MCP-008` |
| MCP to common | No shared package exists |
