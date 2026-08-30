# 20 — Known Gaps

Each gap: problem, evidence, impact, fix, priority. Evidence is a file and
line, a command output, or a quotation — never an impression.

---

## Architecture gaps

### G-A1 — Two disconnected systems

- **Problem:** `agent/` (real, tested) and `dashboard/` (mocked) share no code.
- **Evidence:** `dashboard/app.py:17-19` imports `agent.bob.BobAgent`,
  `agent.bob.Detection`, `agent.record.save_record`. None exist —
  `agent/bob.py` exports `analyze()`; `agent/record.py` was deleted in the
  consolidation. `except ImportError` sets `BobAgent = None`, silently.
- **Impact:** everything a judge clicks is fabricated; everything correct is
  unreachable. Also affects `RECORDS_DIR`, which falls back to
  `agent/records/` while `agent/audit.py` writes to `records/`.
- **Fix:** `API-001` then `DASH-001`.
- **Priority:** **P0.**

### G-A2 — No API over the agent

- **Problem:** `agent/pipeline.py` has no HTTP surface, and
  `run_full_pipeline()` takes the human decision as an argument, so it cannot
  pause at the approval gate.
- **Evidence:** the docstring itself: *"the dashboard calls each stage
  individually through the API layer (not yet implemented)"*.
- **Impact:** no interactive human review is possible.
- **Fix:** `API-001`. **Priority: P0.**

### G-A3 — MCP depends on Track 1

- **Evidence:** `mcp_server/models.py:6`, `mcp_server/tools.py:4`,
  `mcp_server/watcher.py:3` — all `from orchestrator.evidence import ...`.
- **Impact:** `orchestrator/` cannot be deleted; the dependency graph reads
  backwards.
- **Fix:** `MCP-003` — move the file, update three imports. **Priority: P1.**

### G-A4 — Two `EvidenceSnapshot` types

- **Evidence:** `agent/models.py:45` and `orchestrator/evidence.py:100` define
  different classes with the same name.
- **Impact:** MCP evidence cannot reach the agent without an adapter.
- **Fix:** `MCP-008`. **Priority: P1.**

### G-A5 — Correlation is performed twice

- **Evidence:** `agent/correlation.py` computes a `CorrelationResult`
  deterministically; `agent/bob.py:PROMPT_TEMPLATE` also asks Bob to correlate,
  and `BobAnalysis.correlation` holds Bob's answer. Nothing reconciles them.
- **Impact:** the headline claim — "Bob understood that three symptoms were one
  problem" — is ambiguous. A judge asking "who correlated these?" gets no clean
  answer.
- **Fix:** decide ownership, `ADR-007`. **Priority: P2** (P1 if the demo
  narrative leans on it).

---

## Code gaps

### G-C1 — `mcp_server/tickets.py` raises `NameError`

- **Evidence:** reproduced —
  `tickets.update_ticket(id, status='investigating')` →
  `NameError: name 'Enum' is not defined`. `Enum` is used at the `elif` in
  `update_ticket()` but never imported.
- **Impact:** every scalar-field update fails; `update_ticket_status` is
  entirely broken.
- **Fix:** one import line, plus a test. `MCP-005`. **Priority: P1.**

### G-C2 — `--profile evidence` is ignored

- **Evidence:** `.bob/mcp.json` passes `--profile evidence`;
  `mcp_server/server.py` has no `argparse`, no `sys.argv`, no reference to
  `KUBEMEDIC_MCP_PROFILE`.
- **Impact:** `create_ticket` and `update_ticket_status` are exposed on a
  profile whose `//safety` key says READ ONLY. The judge's ten-second check
  passes only because no cluster mutation tool was ever written.
- **Fix:** `MCP-002`. **Priority: P1.** *(`docs/handoffs.md` #1, BLOCKING.)*

### G-C3 — Three MCP tool names mismatch

- **Evidence:** server registers `get_workload_state`, `get_app_health`,
  `get_full_snapshot`. `.bob/mcp.json` and
  `agent/verification.py:EvidenceReader` both expect `get_workload_status`,
  `get_application_health`, `get_workload_snapshot`.
- **Fix:** rename the server's tools. `MCP-001`. **Priority: P1.**

### G-C4 — No `KubernetesClient` implementation

- **Evidence:** `git grep rollback_deployment` finds the Protocol, the
  dispatch, the prompt allowlist, three dashboard strings and test fakes.
  Nothing else.
- **Impact:** the executor has never mutated a cluster. "OpsPilot remediates"
  is not true of any code path that has run.
- **Fix:** `EXEC-001`. **Priority: P1.**

### G-C5 — No `EvidenceReader` implementation

- **Evidence:** the protocol needs `get_workload_status` /
  `get_application_health` returning dicts; `orchestrator/evidence.py` offers
  `inspect_workload` / `check_application_health` returning pydantic models.
- **Impact:** verification has never read a cluster.
- **Fix:** `VER-001`, mapping `ready` to `rollout_complete`. **Priority: P1.**

### G-C6 — Watcher produces one ticket, not many

- **Evidence:** `_check_anomalies()` joins all anomalies into one title,
  creates one ticket, then suppresses further tickets while any open or
  investigating ticket exists for the deployment.
- **Impact:** many-to-one correlation has no real input. This is *why* the
  dashboard fabricates three tickets.
- **Fix:** `TICKET-001`. **Priority: P1.**

### G-C7 — Watcher blocks the event loop

- **Evidence:** `_check_anomalies()` is synchronous and performs blocking
  Kubernetes I/O; it is called from the async `_loop()`.
- **Impact:** the MCP server stalls for the duration of every poll.
- **Fix:** `asyncio.to_thread`. **Priority: P2.**

### G-C8 — MCP results are Python `repr`, and errors look like successes

- **Evidence:** `handle_call_tool` returns `str(result)`; it also catches every
  exception and returns `f"Error: {e}"` as a normal text result.
- **Impact:** the model must parse `repr`, and cannot distinguish a failed tool
  call from a successful one — contradicting `AGENTS.md` rule 1.
- **Fix:** `MCP-006`, `MCP-007`. **Priority: P2.**

### G-C9 — Dead states

- **Evidence:** `EVIDENCE_FAILED` and `VERIFIED` are never set;
  `verify()` goes straight to `RESOLVED`.
- **Fix:** `MODEL-001`. **Priority: P3.**

---

## Testing gaps

### G-T1 — Whole layers untested

- **Evidence:** all 62 tests target `agent/`. Zero for `mcp_server/`,
  `dashboard/`, `orchestrator/`, `workload/`.
- **Fix:** `TEST-001`, `TEST-002`, plus tests inside `MCP-002`. **Priority: P2.**

### G-T2 — No end-to-end test

- **Evidence:** `scripts/validate.sh` hardcodes
  `/c/Users/shivraj/Desktop/Devops/opspilot/orchestrator/.venv/Scripts/python.exe`
  and calls `orchestrator/validate_incident.py`, absent from this repo.
- **Fix:** `E2E-001`. **Priority: P2.**

### G-T3 — Bob has never returned a real analysis

- **Evidence:** the only Bob test is `test_analyze_no_key_returns_unavailable`.
  No record with `analysis_source: "ibm-bob"` exists.
- **Impact:** the central claim of the submission is unproven.
- **Fix:** `BOB-001`. **Priority: P0.**

### G-T4 — No CI

- **Evidence:** no `.github/` directory.
- **Fix:** `CI-001`. **Priority: P2.**

---

## Security and safety gaps

### G-S1 — The dashboard fabricates verification results

- **Evidence:** `dashboard/app.py:_decide()` — six named checks each report the
  value of `approved`; `"passed": approved` appears throughout the
  `verification` block. No cluster call is made anywhere in the function.
- **Impact:** the audit record makes a false claim of verified recovery. This
  contradicts `AGENTS.md` rule 3 and touches the rules' honest-and-good-faith
  clause. **Do not record the demo video against this.**
- **Fix:** `DASH-001`. **Priority: P0.**

### G-S2 — The read-only safety claim is unenforced

- Covered by G-C2. True today only by accident of what was written.
  **Priority: P1.**

### G-S3 — What is genuinely safe (do not regress these)

No `subprocess`, `os.system`, `eval` or `exec` in `agent/`. Actions are a
closed enum. `BobAnalysis.from_raw` rejects non-allowlisted actions before
parsing. `REJECTED -> EXECUTING` and `FEEDBACK_RECORDED -> EXECUTING` are
structurally impossible. `_redact()` keeps the prompt out of logs; the API key
never leaves the header.

---

## Repository hygiene gaps

### G-R1 — The runtime database is committed

- **Evidence:** `git ls-files data/` → `data/kubemedic.db`. Committed in
  `1448908`.
- **Cause:** the archive's `.gitignore` had `data/*.db`; the branch's
  `.gitignore` (from `ramana`) does not, and `git add -A` picked the file up.
  **This was introduced by the import commit — my error.**
- **Impact:** the database churns on every run and appears as a diff.
- **Fix:** `REPO-001`. **Priority: P2.**
- *Note:* the blob remains in history. Untracking is enough for a 12KB
  schema-only file; history rewriting is not justified here.

### G-R2 — Absolute developer paths committed

- **Evidence:** `scripts/validate.sh:18-19`.
- **Impact:** `AGENTS.md` explicitly forbids this; the script cannot run on
  another machine.
- **Fix:** `REPO-004`. **Priority: P2.**

### G-R3 — No dependency declaration

- **Evidence:** no root `requirements.txt` or `pyproject.toml`;
  `agent/requirements.txt` does not exist on this branch. pydantic and pytest
  are undeclared.
- **Impact:** a fresh clone cannot be set up from the repository alone —
  directly against judging criterion "completeness and feasibility".
- **Fix:** `REPO-002`. **Priority: P2.**

### G-R4 — `main` is empty and the trunk is `ramana`

- **Evidence:** `origin/main` is `95adfc6`, containing `LICENSE` and a one-line
  `README.md`.
- **Impact:** a judge cloning the default branch sees nothing.
- **Fix:** merge `ramana` to `main` first — `15_GIT_WORKFLOW.md`. **Priority: P0.**

### G-R5 — Inconsistent branch naming

- `ramana`, `verona` (flat) vs `shivraj/mcp-repo-ci` (`owner/topic`). Git
  cannot hold both `ramana` and `ramana/x`. **Priority: P3**, but decide now.

### G-R6 — Two project names and two namespaces

- KubeMedic vs OpsPilot; `.env.example` says `KUBERNETES_NAMESPACE=kubemedic`
  while manifests, scripts and code defaults use `opspilot`.
- **Impact:** following `.env.example` points the tools at a namespace that
  does not exist.
- **Fix:** `NAME-001`, `NAME-002`. **Priority: P3** for the name, **P2** for
  the namespace.

---

## Documentation gaps

### G-D1 — README is one line

`# Kubemedic`. Nothing else. **Fix:** `REPO-003`. **Priority: P2.**

### G-D2 — `consolidation-inventory.md` is now inaccurate

It states no dashboard template contains a Gemini reference. True when written
(the dashboard was not yet on the branch); false now —
`templates/index.html:263,834`. **Fix:** `DOC-001`. **Priority: P2.**

### G-D3 — No `THIRD_PARTY_NOTICES.md`

`AGENTS.md` calls for one. **Priority: P3.**

---

## IBM Bob / watsonx gaps

### G-B1 — No live analysis has ever been observed

Covered by G-T3. **Priority: P0.** The highest-value single task in the project.

### G-B2 — The Bob endpoint is unverified

- **Evidence:** `agent/bob.py` posts to `https://cloud.manufact.com/api/v1/chats`.
  The docstring says the protocol was read from the IDE extension's
  `RemoteAgent` class.
- **Impact:** **UNKNOWN / NEEDS VERIFICATION** — nothing in the repository
  establishes this as the sanctioned IBM Bob API for the contest. If it is not,
  the Bob integration story needs rebuilding, and there is under a day left.
- **Fix:** verify against IBM Bob's own documentation **before** writing more
  integration code. **Priority: P0.**

### G-B3 — Gemini strings in user-visible surfaces

`dashboard/app.py:202,299,389`; `templates/index.html:263,834`. Not a rules
violation — no Google SDK is used anywhere — but a judge reading
*"Gemini LLM for hypothesis generation"* in the UI will discount the Bob
integration. **Fix:** `DASH-003`. **Priority: P2.**

---

## Demo gaps

### G-DM1 — The demo the UI shows is not the demo the cluster produces

- **Evidence:** `k8s/deployment.yaml` produces a readiness regression on
  `ticket-booking` (liveness is TCP precisely so pods do *not* crash-loop).
  `dashboard/app.py:149` fabricates a CrashLoopBackOff storm across
  `ticket-booking`, `payment-service` and `frontend-gateway` — the latter two
  are not deployed by anything in `k8s/`.
- **Impact:** the video and the cluster tell different stories. A judge who
  runs the repository sees neither.
- **Fix:** `DASH-001` + `TICKET-001`. **Priority: P0.**

### G-DM2 — No rehearsed runbook

`18_DEMO_RUNBOOK.md` now exists but is honest that steps 6+ do not run today.
**Priority: P1.**
