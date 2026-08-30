# 20 — Known Gaps

**Updated 2026-08-30.** This document reflects the state of `main` after all
branch merges. Gaps marked **RESOLVED** are closed; evidence is cited.

Each open gap: problem, evidence, impact, fix, priority.

---

## Architecture gaps

### G-A1 — Two disconnected systems ✅ RESOLVED

- **Fix applied:** Dashboard wired to `agent/api.py` via `dashboard/api_adapter.py`.
  `RealAdapter` forwards to the live agent when `KUBEMEDIC_AGENT_BASE_URL` is
  set; `MockAdapter` handles local development. 7 integration tests confirm the
  real seam. **Commit `d3d91a1`.**

### G-A2 — No API over the agent ✅ RESOLVED

- **Fix applied:** `agent/api.py` — 8 routes, 28 tests. Covers the full lifecycle
  including `/review` (with mandatory feedback on rejection) and `/revise`.

### G-A3 — MCP depends on Track 1 ✅ RESOLVED

- **Fix applied:** `mcp_server/evidence.py` replaces `orchestrator/evidence.py`
  as the evidence layer. `orchestrator/` was deleted. Commit `c570da9`.

### G-A4 — Two `EvidenceSnapshot` types ✅ RESOLVED

- **Fix applied:** `agent/adapters.py:collect_agent_evidence` produces a single
  typed `EvidenceSnapshot` from the live cluster. Both consumer paths use it.

### G-A5 — Correlation is performed twice

- **Status: open — accepted.** `agent/correlation.py` runs deterministically;
  Bob is also asked to correlate in its prompt. The two results are not yet
  reconciled. `docs/21_DECISIONS.md` ADR-007 documents this decision.
- **Impact on submission:** the many-to-one claim is true of `correlation.py`
  and of Bob's prompt; which result the code acts on is Python's.
- **Priority: P3** — not affecting correctness or safety, but the demo
  narrative should not imply Bob performed the correlation alone.

---

## Code gaps

### G-C1 — `mcp_server/tickets.py` raises `NameError` ✅ RESOLVED

- **Fix applied:** `Enum` imported; 12 regression tests. Commit `de4b32d`.

### G-C2 — `--profile evidence` is ignored ✅ RESOLVED

- **Fix applied:** `mcp_server/server.py` reads `--profile` from `sys.argv` and
  enforces the read-only tool set. CI asserts via `test_mcp_profile_evidence`.
  Commit `d4796a5`.

### G-C3 — Three MCP tool names mismatch ✅ RESOLVED

- **Fix applied:** server renamed to `get_workload_status`,
  `get_application_health`, `get_workload_snapshot`. 18 contract tests.
  Commit `d4796a5`.

### G-C4 — No `KubernetesClient` implementation ✅ RESOLVED

- **Fix applied:** `agent/k8s_client.py:LiveCluster` — rollback, restart, scale
  against the Kubernetes API. Live rollback executed and verified on k3s.
  Commit `f9c564b`.

### G-C5 — No `EvidenceReader` implementation ✅ RESOLVED

- **Fix applied:** `agent/adapters.py:LiveEvidenceReader` implements the
  protocol and maps field names. Both signals verified live. Commit `f9c564b`.

### G-C6 — Watcher produces one ticket, not many ✅ RESOLVED

- **Fix applied:** `mcp_server/watcher.py` — one ticket per anomaly signal kind,
  deduplicated by `(deployment, signal_kind)`. 2 real tickets filed and
  correlated into 1 incident in the end-to-end run. Commit `592d487`.

### G-C7 — Watcher blocks the event loop

- **Status: open.** `_check_anomalies()` is synchronous and performs blocking
  Kubernetes I/O inside an async loop. The MCP server stalls for the poll
  duration.
- **Impact:** negligible for a demo / proof of concept. Would matter under load.
- **Priority: P3** — not fixing before submission.

### G-C8 — MCP results are Python `repr`

- **Status: partially resolved.** The server now returns proper dicts from the
  evidence tools. Error handling still returns strings in some paths.
- **Priority: P3.**

### G-C9 — Dead states ✅ RESOLVED (partial)

- `EVIDENCE_FAILED` is raised when evidence collection fails (`agent/reasoning.py`).
  `VERIFIED` is not used; `verify()` transitions directly to `RESOLVED`.
  Accepted as an architectural simplification — the verification outcome is
  captured in the audit log rather than as a state.

---

## Testing gaps

### G-T1 — Whole layers untested ✅ RESOLVED

- **Fix applied:** 238 tests across `agent/`, `mcp_server/`, `dashboard/`,
  `tests/integration/`. Commit `9ba495e` and subsequent.

### G-T2 — No end-to-end test ✅ RESOLVED

- **Fix applied:** `scripts/validate.sh` — portable, no absolute paths,
  29 assertions against a live k3s cluster. ALL CHECKS PASSED on 2026-08-30.
  Commit `9ba495e`.

### G-T3 — Bob has never returned a real analysis

- **Status: open.** No record with `analysis_source: "ibm-bob"` exists.
  `agent/bob.py` is implemented and tested; no live model call has been
  completed (no credentials).
- **Impact:** the central capability is demonstrated by contract and tests, not
  by a live run. `submission/HOW_WE_USED_IBM_BOB.md` states this plainly.
- `scripts/ingest_bob_analysis.py` provides the path to produce such a record
  from an interactive Bob session.
- **Priority: P0 — highest-value remaining task if credentials become available.**

### G-T4 — No CI ✅ RESOLVED

- **Fix applied:** `.github/workflows/ci.yml` — lint, tests, safety assertion
  (evidence profile is read-only). Commit `9ba495e`.

---

## Security and safety gaps

### G-S1 — The dashboard fabricates verification results ✅ RESOLVED

- **Fix applied:** `dashboard/app.py` routes to `dashboard/api_adapter.py`.
  The `MockAdapter` (used for local dev) does not write any verification results.
  The `RealAdapter` reads actual incident state from `agent/api.py`. Commit `d3d91a1`.
- **Note:** the `MockAdapter` fixture data (in `api_adapter.py`) was updated to
  use realistic, non-fabricated verification signals. The old `_decide()` 
  pattern is gone.

### G-S2 — The read-only safety claim is unenforced ✅ RESOLVED

- Covered by G-C2. Enforced and tested.

### G-S3 — What is genuinely safe (do not regress these)

No `subprocess`, `os.system`, `eval` or `exec` in `agent/`. Actions are a
closed enum. `BobAnalysis.from_raw` rejects non-allowlisted actions before
parsing. `REJECTED -> EXECUTING` and `FEEDBACK_RECORDED -> EXECUTING` are
structurally impossible. `_redact()` keeps the prompt out of logs; the API key
never leaves the header.

---

## Repository hygiene gaps

### G-R1 — The runtime database is committed ✅ RESOLVED

- **Fix applied:** `.gitignore` updated with `data/*.db`. File is untracked.

### G-R2 — Absolute developer paths committed ✅ RESOLVED

- **Fix applied:** `scripts/validate.sh` uses `$(cd "$(dirname "$0")/.." && pwd)`
  and portable Python invocation. No absolute paths.

### G-R3 — No dependency declaration ✅ RESOLVED

- **Fix applied:** `requirements.txt` and `requirements-dev.txt` at root.

### G-R4 — `main` is empty ✅ RESOLVED

- **Fix applied:** all three branches merged to `main`. `d3d91a1` is the trunk.

### G-R5 — Inconsistent branch naming

- **Status: moot** — all branches are merged; the branch naming question only
  mattered while branches were live.

### G-R6 — Two project names and two namespaces

- **Status: partially resolved.** README, manifests, scripts and defaults all
  use `opspilot`. `.env.example` updated to match.
- **Priority: P3** — cosmetic.

---

## Documentation gaps

### G-D1 — README is one line ✅ RESOLVED

- **Fix applied:** full README with architecture diagram, setup, API reference,
  known limitations.

### G-D2 — `consolidation-inventory.md` is now inaccurate ✅ RESOLVED

- Dashboard templates no longer contain Gemini strings (the `_decide()` function
  was replaced; templates were audited). The consolidation-inventory claim is
  now accurate.

### G-D3 — No `THIRD_PARTY_NOTICES.md` ✅ RESOLVED

- **Fix applied:** `THIRD_PARTY_NOTICES.md` created at repository root.

---

## IBM Bob / watsonx gaps

### G-B1 — No live analysis has ever been observed

- **Status: open.** Covered by G-T3.
- The interactive ingestion path (`scripts/ingest_bob_analysis.py`) exists and
  is tested — a live analysis from a Bob workspace session can be ingested and
  validated against the same contract as the REST path.
- **Priority: P0.**

### G-B2 — The Bob endpoint is unverified

- **Status: open.** `agent/bob.py` posts to the RemoteAgent REST API. The base
  URL has not been confirmed against IBM Bob's own documentation.
- **Impact:** the REST path may not work even with credentials.
- **Priority: P0** — verify before relying on it.

### G-B3 — Gemini strings in user-visible surfaces ✅ RESOLVED

- Dashboard templates and `app.py` were audited — no Gemini strings in any
  user-visible surface. No Google SDK is present anywhere in the codebase.
  Verified by `git grep`.

---

## Demo gaps

### G-DM1 — The demo the UI shows is not the demo the cluster produces ✅ RESOLVED

- **Fix applied:** `dashboard/api_adapter.py` serves the real incident from the
  live agent when `KUBEMEDIC_AGENT_BASE_URL` is set. `MockAdapter` fixture was
  updated to match the real incident shape (the `ticket-booking` rollout
  failure, not the multi-service CrashLoopBackOff). Commit `d3d91a1`.

### G-DM2 — No rehearsed runbook ✅ RESOLVED

- `SHIVRAJ_DOCS/06_DEMO_SCRIPT.md` — two versions (dashboard and terminal), with
  step-by-step narration, timing, and lines to avoid.
