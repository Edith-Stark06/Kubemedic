# 00 — Project Status

**Branch audited:** `shivraj/mcp-repo-ci` @ `1448908`
**Audit date:** 2026-08-29
**Test result:** `python -m pytest -q` → **62 passed in 0.28s** (executed)

This branch = Ramana's consolidated `agent/` (from `origin/ramana`) + the
`mcp_server/`, `dashboard/`, `k8s/`, `workload/`, `scripts/` layers imported
from the OpsPilot archive. It is the only branch where all layers coexist.

---

## The single most important finding

**There are two systems in this repository that do not touch each other.**

| | `agent/` | `dashboard/` |
|---|---|---|
| Origin | Ramana, Track 2 consolidation | OpsPilot archive, Track 1 era |
| Reality | Real typed pipeline, 62 tests | Hardcoded simulation |
| Bob | Real REST call, fails honestly | Not called at all |
| Evidence | From `EvidenceSnapshot` | Literal dicts in `app.py` |
| Verification | Re-reads cluster, two signals | `"passed": approved` |
| Rejection feedback | Required by model validator | Field does not exist |

`dashboard/app.py:17` tries `from agent.bob import BobAgent, Detection` and
`from agent.record import save_record`. **Neither exists** — `agent/bob.py`
exports `analyze()`, not `BobAgent`, and `agent/record.py` was deleted in the
consolidation. The `except ImportError` on line 19 swallows the failure and
sets `BobAgent = None`. The dashboard then runs entirely on fabricated data
and nobody sees an error.

Everything a judge would click is the mocked system. Everything that is
correct and tested is unreachable from the UI.

---

## Current state

### What works (verified)

- `agent/` full lifecycle: correlate → analyse → plan → decide → execute →
  verify → record. 62 tests pass; command and result above.
- `agent/models.py` contracts: allowlisted action enum, illegal-transition
  guard (`REJECTED → EXECUTING` raises), mandatory feedback on rejection.
- `agent/bob.py` returns `bob_unavailable` rather than fabricating an
  analysis when no API key is configured. `test_analyze_no_key_returns_unavailable` covers this.
- `mcp_server/tools.py` and `dashboard/app.py` both import cleanly
  (`python -c "import ..."` → ok).
- `orchestrator/evidence.py` is a genuine read-only Kubernetes evidence layer.

### What is partially implemented

- **MCP server.** Ten tools registered and dispatched. No `--profile` flag
  exists despite `.bob/mcp.json` passing one. Three tool names do not match
  what Bob is configured to call.
- **Human review.** The *model* enforces feedback-on-reject correctly. The
  *HTTP surface* (`POST /api/reject`) accepts no feedback field at all.
- **Correlation.** Implemented deterministically in `agent/correlation.py`,
  and *also* requested from Bob via `PROMPT_TEMPLATE`. Both produce a
  `CorrelationResult`. Which one wins is undefined.

### What is broken

- `mcp_server/tickets.py:update_ticket()` raises `NameError: name 'Enum' is
  not defined` — `Enum` is referenced on the `elif` branch but never imported.
  Verified by direct call. This breaks the `update_ticket_status` MCP tool for
  every scalar field.
- `dashboard/app.py` imports symbols that no longer exist (above).
- `scripts/validate.sh` hardcodes `/c/Users/shivraj/Desktop/Devops/opspilot/...`
  and calls `orchestrator/validate_incident.py`, which is not in this repo.

### What is duplicated

- `EvidenceSnapshot` is defined twice, differently: `agent/models.py:45` and
  `orchestrator/evidence.py:100`.
- Correlation logic exists in `agent/correlation.py` and is also asked of Bob.
- Ticket state lives in SQLite (`mcp_server/`) *and* in the dashboard's
  in-memory `_TICKETS` dict. They never sync.

### What is untested

`mcp_server/` (0 tests), `dashboard/` (0 tests), `orchestrator/evidence.py`
(0 tests), `workload/` (0 tests). All 62 tests target `agent/`.

### What is missing

No HTTP/API layer over `agent/pipeline.py`. No `.github/` or CI. No root
`requirements.txt` or `pyproject.toml`. No `agent/requirements.txt` (pydantic
is undeclared). README is one line. No `submission/` directory. No feedback →
re-analysis loop.

---

## Architecture status

**Track 1** — `orchestrator/`. Only `evidence.py` survives on this branch, as
a dependency of `mcp_server/`. The rest (correlation, hypothesis, plan,
executor, verification, record, pipeline, app) exists only in the archive and
on `main`'s `abe5672`.

**Track 2** — `agent/`. Complete, typed, tested. This is the real system.

**Final intended architecture** — Track 2 owns reasoning and lifecycle; MCP
owns evidence; a dashboard renders Track 2's state. **Not yet reached.** The
dashboard is still Track 1-era and mocked; MCP still imports Track 1.

Track 2 is *internally* complete. It is not *integrated*.

---

## Critical blockers

### P0 — submission blockers

| ID | Blocker |
|---|---|
| P0-1 | Dashboard is a simulation; it fabricates verification results and never calls the agent |
| P0-2 | No API layer — nothing can drive `agent/pipeline.py` from a UI |
| P0-3 | Contest deadline is 2026-08-30 10:00 ET (see `19_HACKATHON_COMPLIANCE.md`) |
| P0-4 | IBM Bob has never been observed returning a real analysis (no key configured) |
| P0-5 | Submission deliverables absent: video, statements, exported Bob report |

### P1 — integration blockers

| ID | Blocker |
|---|---|
| P1-1 | MCP tool names ≠ `.bob/mcp.json` / `EvidenceReader` names |
| P1-2 | No `--profile evidence` flag (`docs/handoffs.md` #1) |
| P1-3 | `mcp_server` imports `orchestrator.evidence` |
| P1-4 | `tickets.update_ticket()` `NameError` |
| P1-5 | No feedback → revised plan loop |
| P1-6 | Two `EvidenceSnapshot` types; no adapter MCP → agent |

### P2 — quality

Gemini strings in `dashboard/`; no CI; `data/kubemedic.db` committed;
`validate.sh` local paths; namespace `kubemedic` vs `opspilot` mismatch;
undeclared dependencies.

### P3 — polish

README, naming consistency, docstring cleanup.

---

## Confidence by subsystem

| Subsystem | Status | Basis |
|---|---|---|
| MCP | **PARTIAL** | Imports and dispatches; wrong names, no profile, one broken tool |
| Agent | **READY** | 62 tests pass |
| Reasoning | **UNVERIFIED** | Code correct; no real Bob response ever observed |
| Ticketing | **PARTIAL** | SQLite works; `update_ticket` broken; two competing stores |
| Dashboard | **BROKEN** | Fabricates data; dead imports |
| Human approval | **PARTIAL** | Model layer correct; HTTP layer wrong |
| Remediation | **PARTIAL** | Executor correct + tested; no real `KubernetesClient` implementation exists |
| Verification | **PARTIAL** | Logic correct + tested; no real `EvidenceReader` implementation exists |
| Audit | **READY** | Records written and tested |
| CI | **MISSING** | No `.github/` |
| Documentation | **PARTIAL** | This set; README missing |
| Submission | **MISSING** | No deliverables produced |

> **UNKNOWN / NEEDS VERIFICATION:** no `KubernetesClient` or `EvidenceReader`
> concrete implementation exists anywhere in the repository. Both protocols are
> satisfied only by test fakes. The executor and verifier have never run
> against a cluster.
