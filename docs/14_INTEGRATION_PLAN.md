# 14 — Integration Plan

> **Read `19_HACKATHON_COMPLIANCE.md` before using this plan.** The Official
> Rules put the submission deadline at **10:00 AM ET on 2026-08-30**. Today is
> **2026-08-29**. This plan is written for roughly one working day, not a
> normal sprint. The phase ordering below is therefore also a *triage* order:
> if you run out of time, everything after Phase 6 is what you drop.

Estimates are working hours for one engineer who knows the code.

---

## Phase 0 — Repository baseline

| Field | Value |
|---|---|
| **Task** | `REPO-001` Untrack `data/kubemedic.db`; add `data/*.db` and `records/*.json` to `.gitignore` |
| Owner | Shivraj |
| Depends | — |
| Files | `.gitignore`, `data/kubemedic.db` |
| Estimate | 10 min |
| Done when | `git ls-files data/` is empty; a fresh clone has no database |
| Tests | `git ls-files \| grep -c "\.db$"` returns 0 |
| Commit | `chore: untrack the runtime sqlite database` |

| Field | Value |
|---|---|
| **Task** | `REPO-002` Root `requirements.txt` + `requirements-dev.txt` |
| Owner | Shivraj |
| Depends | — |
| Files | new |
| Estimate | 15 min |
| Done when | `pip install -r requirements.txt` in a clean venv, then `pytest`, both work |
| Commit | `chore: declare dependencies` |

| Field | Value |
|---|---|
| **Task** | `REPO-003` README with real setup steps |
| Owner | Shivraj |
| Depends | `REPO-002` |
| Files | `README.md` (currently one line) |
| Estimate | 45 min |
| Done when | A judge can clone and reach a running dashboard using only the README |
| Commit | `docs: README with setup and demo instructions` |

---

## Phase 1 — Architecture consolidation

| Field | Value |
|---|---|
| **Task** | `MCP-003` Move `orchestrator/evidence.py` to `mcp_server/evidence.py`; update 3 imports; delete `orchestrator/` |
| Owner | Shivraj |
| Depends | — |
| Files | `orchestrator/evidence.py`, `mcp_server/{models,tools,watcher}.py` |
| Estimate | 20 min |
| Done when | `git grep "from orchestrator"` is empty; `orchestrator/` is gone; imports still succeed |
| Tests | `python -c "import mcp_server.tools"`; `pytest -q` still 62 |
| Commit | `refactor: move the evidence layer into mcp_server, retire orchestrator/` |

---

## Phase 2 — MCP contract

| Field | Value |
|---|---|
| **Task** | `MCP-001` Rename 3 tools to the names both consumers already expect |
| Owner | Shivraj |
| Depends | `MCP-003` |
| Files | `mcp_server/server.py`, `mcp_server/tools.py` |
| Estimate | 20 min |
| Done when | `get_workload_status`, `get_application_health`, `get_workload_snapshot` are the registered names |
| Tests | New: list_tools returns exactly the names in `.bob/mcp.json` |
| Commit | `fix(mcp): align tool names with .bob/mcp.json and EvidenceReader` |

| Field | Value |
|---|---|
| **Task** | `MCP-005` Import `Enum` in `mcp_server/tickets.py` |
| Owner | Shivraj |
| Depends | — |
| Files | `mcp_server/tickets.py` |
| Estimate | 5 min |
| Done when | `update_ticket(id, status='investigating')` returns a `Ticket` |
| Tests | New unit test asserting a scalar-field update |
| Commit | `fix(tickets): import Enum; scalar field updates no longer raise` |

| Field | Value |
|---|---|
| **Task** | `MCP-002` Implement `--profile evidence` (handoff #1, BLOCKING) |
| Owner | Shivraj |
| Depends | `MCP-001` |
| Files | `mcp_server/server.py` |
| Estimate | 45 min |
| Done when | With the flag, `list_tools` returns exactly the 7 allowlisted read tools and `call_tool` refuses anything else |
| Tests | Two new tests: 7 tools listed; a mutation tool call is refused |
| Commit | `feat(mcp): enforce the read-only evidence profile` |

| Field | Value |
|---|---|
| **Task** | `MCP-006` `json.dumps` tool results instead of `str()` |
| Owner | Shivraj |
| Depends | `MCP-001` |
| Estimate | 10 min |
| Commit | `fix(mcp): return JSON, not Python repr` |

---

## Phase 3 — Agent / Bob integration

| Field | Value |
|---|---|
| **Task** | `BOB-001` Obtain credentials and observe one real analysis |
| Owner | Ramana |
| Depends | — |
| Files | `.env` (never committed) |
| Estimate | 30 min, or unbounded if the endpoint is wrong |
| Done when | One incident record exists with `analysis_source: "ibm-bob"` |
| **Priority** | **P0. Nothing else in the submission matters as much as this.** |
| Commit | `docs: record the first live IBM Bob analysis` (record file, not code) |

| Field | Value |
|---|---|
| **Task** | `MCP-008` Adapter: MCP evidence + tickets to agent types |
| Owner | Shivraj + Ramana |
| Depends | `MCP-001`, `MCP-003` |
| Files | new `agent/adapters.py` |
| Estimate | 1.5 h |
| Done when | `collect()` output becomes an `agent.models.EvidenceSnapshot`, and SQLite `Ticket` rows become `TicketReference` **with `named_workload` and `created_at` populated** |
| Tests | Adapter round-trip tests; a correlation test driven by adapted tickets |
| Commit | `feat(agent): adapt MCP evidence and tickets to agent contracts` |
| **Risk** | Dropping `named_workload` or `created_at` silently breaks correlation — see `05_CONTEXT_MODEL.md` |

---

## Phase 4 — Ticket / incident state

| Field | Value |
|---|---|
| **Task** | `TICKET-001` Watcher emits one ticket per distinct anomaly signal |
| Owner | Shivraj |
| Depends | `MCP-005` |
| Files | `mcp_server/watcher.py` |
| Estimate | 1 h |
| Done when | One injected failure produces 3 real tickets (rollout stalled, pod NotReady, health 503) |
| Tests | Watcher unit tests with a fake evidence layer |
| Commit | `feat(watcher): one ticket per anomaly signal so correlation has real input` |
| **Why** | Today a real run yields one ticket. Many-to-one correlation of one ticket demonstrates nothing |

| Field | Value |
|---|---|
| **Task** | `TICKET-002` Resolving an incident updates its member tickets |
| Owner | Shivraj |
| Depends | `MCP-008` |
| Estimate | 45 min |
| Commit | `feat: propagate incident state to member tickets` |

---

## Phase 5 — Human review feedback loop

| Field | Value |
|---|---|
| **Task** | `API-001` FastAPI layer over the agent stages |
| Owner | Ramana |
| Depends | `MCP-008` |
| Files | new `agent/api.py` |
| Estimate | 2.5 h |
| Done when | The endpoints in `11_API_CONTRACTS.md` exist and hold `Incident` state between requests |
| Tests | `TestClient` tests per endpoint |
| Commit | `feat(api): HTTP surface over the incident lifecycle` |
| **Note** | `run_full_pipeline()` cannot serve this — it takes the decision up front. Call the stages individually |

| Field | Value |
|---|---|
| **Task** | `REVIEW-001` `POST /incidents/{id}/review` with `400 feedback_required` |
| Owner | Ramana |
| Depends | `API-001` |
| Estimate | 45 min |
| Done when | Rejection without feedback returns 400; with feedback returns 200 and stores it |
| Tests | Both branches |
| Commit | `feat(api): human review gate; rejection requires a reason` |

| Field | Value |
|---|---|
| **Task** | `REVIEW-002` Feed rejection feedback into the next Bob call |
| Owner | Ramana |
| Depends | `REVIEW-001` |
| Files | `agent/models.py`, `agent/bob.py`, `agent/reasoning.py`, `agent/pipeline.py` |
| Estimate | 2 h |
| Done when | Rejecting with a reason produces a **different** plan, and the feedback is visible in the audit log of the revised analysis |
| Tests | Reject, re-analyse, assert the new prompt contains the feedback and the plan changed; assert a revision cap |
| Commit | `feat(agent): human feedback becomes reasoning context for the revised plan` |
| **Safety** | `_ILLEGAL_TRANSITIONS` already blocks `FEEDBACK_RECORDED -> EXECUTING`. Do not weaken it. Add a revision cap so reject/revise cannot spin |

---

## Phase 6 — Remediation

| Field | Value |
|---|---|
| **Task** | `EXEC-001` Real `KubernetesClient` |
| Owner | Ramana |
| Depends | `MCP-003` |
| Files | new `agent/k8s_client.py` |
| Estimate | 1.5 h |
| Done when | `rollback_deployment`, `restart_deployment`, `scale_workload` work against the live cluster through `AppsV1Api` |
| Tests | Unit tests with a mocked API client; one manual live run |
| Commit | `feat(agent): Kubernetes client for the three allowlisted actions` |
| **Safety** | No shell, no `kubectl` subprocess. Typed API calls only |

---

## Phase 7 — Verification

| Field | Value |
|---|---|
| **Task** | `VER-001` Real `EvidenceReader` |
| Owner | Ramana |
| Depends | `MCP-001` |
| Estimate | 45 min |
| Done when | `verify()` re-reads the live cluster on both signals |
| **Decision needed** | Which `WorkloadState` field means `ready`. Use `rollout_complete`, not `healthy` — see `10_REMEDIATION_AND_VERIFICATION.md` |
| Commit | `feat(agent): live dual-signal verification` |

---

## Phase 8 — Dashboard integration

| Field | Value |
|---|---|
| **Task** | `DASH-001` Point the dashboard at the real API; delete every mock |
| Owner | Verona |
| Depends | `API-001` |
| Files | `dashboard/app.py`, `templates/index.html` |
| Estimate | 3 h |
| Done when | No literal ticket, evidence or verification data remains in `app.py`; `git grep -n '"passed": approved'` is empty |
| **This is P0-1.** The current dashboard writes audit records asserting verification results that were never checked |
| Commit | `refactor(dashboard): render real incidents from the agent API` |

| Field | Value |
|---|---|
| **Task** | `DASH-002` Reject dialog requiring a reason |
| Owner | Verona |
| Depends | `REVIEW-001` |
| Estimate | 1 h |
| Done when | Reject is disabled until a reason is typed; the server also enforces it; the reason is shown on the incident afterwards |
| Commit | `feat(dashboard): mandatory rejection reason` |

| Field | Value |
|---|---|
| **Task** | `DASH-003` Remove Gemini strings from user-visible surfaces |
| Owner | Verona |
| Depends | `DASH-001` |
| Files | `templates/index.html:263,834`, `dashboard/app.py:202,299,389` |
| Estimate | 15 min |
| Commit | `fix(dashboard): the reasoning engine is IBM Bob` |

---

## Phase 9 — Full end-to-end

| Field | Value |
|---|---|
| **Task** | `E2E-001` Rewrite `scripts/validate.sh` |
| Owner | Shivraj |
| Depends | Phases 5-8 |
| Estimate | 1.5 h |
| Done when | `bash scripts/validate.sh` runs reset, inject, detect, reject-with-reason, revise, approve, execute, verify, reset — with hard assertions, no absolute paths, exit 0 |
| Commit | `test: end-to-end validation harness` |

| Field | Value |
|---|---|
| **Task** | `CI-001` GitHub Actions |
| Owner | Shivraj |
| Depends | `REPO-002` |
| Estimate | 45 min |
| Done when | Install, compile, `pytest`, import `mcp_server.server`, import `dashboard.app` — all green on PR |
| Commit | `ci: pull request validation` |

---

## Phase 10 — Submission freeze

| Task | Owner | Estimate |
|---|---|---|
| `SUB-001` Written problem and solution statements | Ramana | 45 min |
| `SUB-002` "How IBM Bob was used" statement | Ramana | 45 min |
| `SUB-003` Exported IBM Bob report of all relevant tasks/sessions | Shivraj | 30 min |
| `SUB-004` Demo video, in English, showing how Bob was used | Verona | 2 h |
| `SUB-005` Secret sweep, then tag `v1.0-submission` | Shivraj | 30 min |

All five are **required deliverables** under ENTRY REQUIREMENTS. See
`19_HACKATHON_COMPLIANCE.md`.

---

## Critical path

```
MCP-005 -> MCP-003 -> MCP-001 -> MCP-008 -> API-001 -> REVIEW-001 -> DASH-001 -> E2E-001 -> SUB-*
                                    BOB-001 (parallel, P0)
                                    EXEC-001, VER-001 (parallel)
```

**Rough total for Phases 0-9: 22-25 hours of focused work.** Against a
deadline under 24 hours away, with three people, that is not comfortably
achievable in full. Triage guidance is in `16_TASK_BACKLOG.md`.
