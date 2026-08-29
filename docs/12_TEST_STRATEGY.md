# 12 — Test Strategy

## Current position

```
python -m pytest -q
62 passed in 0.28s        (executed 2026-08-29, PASS)
```

All 62 target `agent/`. `mcp_server/`, `dashboard/`, `orchestrator/` and
`workload/` have **zero** tests.

| Area | Tests | Verdict |
|---|---|---|
| `agent/models.py` | ~20 | Strong |
| `agent/correlation.py` | 4 | Adequate |
| `agent/bob.py` | 1 | Thin — only the no-key path |
| `agent/reasoning.py` | 2 | Good — both cover non-fabrication |
| `agent/executor.py` | 8 | Strong |
| `agent/verification.py` | 6 | Strong |
| `agent/audit.py` | 10 | Strong |
| `agent/pipeline.py` | 3 | Adequate |
| `mcp_server/*` | 0 | **Gap** |
| `dashboard/*` | 0 | **Gap** |
| `orchestrator/evidence.py` | 0 | **Gap** |

There is no `pytest.ini`, `pyproject.toml` or `conftest.py`. Tests run from
the repository root by import path. There is no coverage measurement.

---

## Principle

The safety properties are the product. Test them like the product:

- A rejected plan must be **unable** to execute — not merely unlikely.
- Bob being down must never produce an analysis.
- Verification must never say PASS without both signals.
- The executor must never accept anything outside the allowlist.

Every one of these already has a test. Protect them; do not refactor them away.

---

## Unit tests

### Existing and adequate

Action allowlist, state transitions, review validation, feedback persistence,
plan construction, verification outcome logic, record shape.

### Missing — write these

| Target | Test | Why |
|---|---|---|
| `mcp_server/tickets.py` | `update_ticket` with a scalar field succeeds | Catches the live `NameError` |
| `mcp_server/tickets.py` | create, get, list, list-by-status, link | Zero coverage on the ticket store |
| `mcp_server/tools.py` | each tool returns a dict; a cluster error becomes `{"error": ...}` | Zero coverage |
| `mcp_server/server.py` | `handle_list_tools` returns exactly 7 tools under `--profile evidence` | Enforces the safety claim |
| `mcp_server/server.py` | no mutation tool is listed under the evidence profile | The judge's ten-second check, as a test |
| `mcp_server/watcher.py` | anomaly rules fire; duplicate suppression works | Ticket generation is untested |
| adapter | `Ticket` to `TicketReference` preserves `named_workload` and `created_at` | These two fields decide correlation |
| adapter | Track 1 `EvidenceSnapshot` to Track 2 `EvidenceSnapshot` | The main type boundary |
| `agent/bob.py` | `_extract_json` handles fenced, enveloped and prose-wrapped output | Only the no-key path is covered |
| `agent/bob.py` | HTTP 401 and timeout produce `bob_unavailable` | Failure policy is the strongest claim; test it |

---

## Integration tests

| Test | Covers | Status |
|---|---|---|
| MCP tool to evidence (fake K8s client) | tools return real shapes | MISSING |
| MCP tickets to agent `TicketReference` | the adapter | MISSING |
| agent to Bob with a stubbed HTTP layer | `_rest_analyze` parsing | MISSING |
| agent to ticket store: resolving an incident updates its tickets | the sync gap | MISSING |
| dashboard to API | the UI shows agent state, not literals | MISSING |
| review to feedback to reasoning | feedback reaches the next prompt | MISSING (feature absent) |
| executor to verification | execution then independent re-read | Partial — `test_happy_path_resolves` uses fakes |

---

## End-to-end

The required scenario, exactly as in the brief:

```
healthy -> incident -> evidence -> correlation -> plan
        -> human REJECT (with reason)
        -> feedback stored -> revised plan
        -> human APPROVE
        -> execution -> verification -> closure
```

**Today this cannot run**, for three reasons: no revise-after-rejection loop,
no real `KubernetesClient`, no API layer. `test_happy_path_resolves` covers
the approve branch with fakes; `test_rejection_stops_before_execution` covers
the reject branch and stops there.

`scripts/validate.sh` was written to be this harness. It is broken —
hardcoded `/c/Users/shivraj/...` paths and a call to
`orchestrator/validate_incident.py`, which is not in this repository. Rewrite
it once the API exists. Task `E2E-001`.

---

## Negative tests

| Scenario | Expected | Status |
|---|---|---|
| Missing evidence | `run_analysis` raises `ValueError` | Implemented, **untested** |
| MCP unavailable | evidence tool returns `{"error": ...}`; incident does not advance | MISSING |
| Invalid ticket (no workload, no timestamp) | excluded from the incident, recorded in `excluded_tickets` | Partial — `test_unrelated_ticket_excluded` |
| Invalid review decision | rejected by the `Literal` type | Implicit, no explicit test |
| **Reject without feedback** | `ValidationError` at model level; `400 feedback_required` at API | Model **PASS**; API MISSING |
| Executor failure | captured, `success=False`, no exception | **PASS** — `test_cluster_failure_captured_not_raised` |
| Verification failure | `VERIFICATION_FAILED`, never `RESOLVED` | **PASS** — two tests |
| Verification tool error | `INCONCLUSIVE`, not `FAIL` | **PASS** |
| Reasoning failure | `bob_unavailable`, no fabrication | **PASS** — two tests |
| Duplicate ticket | watcher suppresses | Implemented, **untested** |
| Duplicate execution | idempotent | **PASS** |
| Bob recommends a non-allowlisted action | `ValueError` before parsing | **PASS** — two tests |
| Bob recommends `kubectl delete ...` | rejected as not in the enum | **PASS** |

The negative coverage on the agent is genuinely good. The gaps are all in
layers that have no tests at all.

---

## Test infrastructure to add

1. `pytest.ini` (or `[tool.pytest.ini_options]`) pinning `testpaths = tests`.
2. `conftest.py` with shared fixtures: a fake `KubernetesClient`, a fake
   `EvidenceReader`, a temporary SQLite path so ticket tests never touch
   `data/kubemedic.db`.
3. A `requirements-dev.txt` declaring `pytest` — currently undeclared.
4. `pytest --cov` in CI, reported not gated, until a baseline exists.

## Rules for this project

- Never report PASS without pasting the command and its output.
- A test that needs a live cluster is not a unit test — inject a fake.
- Ticket-store tests must use a temp database. The real one is currently
  committed to git (see `20_KNOWN_GAPS.md`); do not make that worse.
- When a safety property changes, the test changes in the same commit.
