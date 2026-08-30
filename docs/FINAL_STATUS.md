# KubeMedic — Final Phase Status

**Commit:** see `git log -1` · **2026-08-30** · `python -m pytest` → **332 passed**

> **Scope note.** The final-phase brief describes roughly a multi-day
> engineering effort. It arrived with 1.5 hours left before the submission
> deadline, so it was triaged to the genuine deltas rather than attempted in
> full. What was already built is listed as such; what was added in this phase
> is named; what was not attempted is named too, rather than quietly omitted.

---

## Status by area

| Area | Status | Basis |
|---|---|---|
| Architecture | **PASS** | Single provider abstraction; `agent/reasoning.py` is the only reasoning boundary |
| AI provider — IBM watsonx | **PARTIAL** | IAM auth verified working; inference blocked by an Inactive WML instance |
| AI provider — IBM Bob | **PARTIAL** | Endpoint unresolved; 401 on `cloud.manufact.com`, 404 on `bob.ibm.com` |
| AI provider — Gemini | **PARTIAL** | Implemented and registered; never called with a real key |
| AI provider — Host IDE | **PASS** | Detects Claude Code / Bob IDE / Antigravity; round trip verified |
| Fallback chain | **PASS** | Primary → fallback on runtime failure, with safe logging; no retry storm |
| MCP evidence layer | **PASS** | 11 read-only tools; `--profile evidence` enforced; CI asserts no mutation tool |
| Ticket flow | **PASS** | Watcher files one ticket per signal; verified live on k3s |
| Agent | **PASS** | Correlation, structured output contract, allowlist enforced before parsing |
| Human review | **PASS** | `400 feedback_required`; enforced at model, API and CLI |
| Feedback loop | **PASS** | Reason enters the prompt; revised plan differs; capped at 3 revisions |
| Remediation | **PASS** | Three allowlisted actions; typed API calls; no shell anywhere |
| Verification | **PASS** | Two independent signals; settle window; never inferred from the executor |
| Dashboard | **PASS** | Operator console at `/ui`; renders only what the API returned |
| Testing | **PASS** | 332 tests; live E2E 29 assertions; deterministic dry run |
| Documentation | **PASS** | 25 docs |
| Repository hygiene | **PASS** | No secrets in history; `.env` untracked; CI hygiene job |

---

## Added in this phase

| Item | Where |
|---|---|
| Gemini provider | `agent/providers/gemini.py` |
| Fallback chain with safe logging | `agent/providers/__init__.py:analyze_with_fallback` |
| `AI_PRIMARY_PROVIDER` / `AI_FALLBACK_*` config | `.env.example` |
| `GET /health/ai` | `agent/api.py` |
| Deterministic dry run | `scripts/dry_run.py` |
| Provider setup and status | `docs/AI_PROVIDER_SETUP.md` |

## Not attempted, and why

| Asked for | Why not |
|---|---|
| `docs/CONFIGURATION_AUDIT.md`, `MCP_OPERATIONS.md`, `TROUBLESHOOTING.md`, `FINAL_ARCHITECTURE.md` | Time. `docs/23_SYSTEM_WORKFLOW.md` and `docs/07_MCP_CONTRACT.md` already cover the architecture and the MCP contract |
| Full dashboard polish pass (§23–24) | The console is functional and honest; a full UX pass did not fit |
| Provider connectivity tests as PASS | No provider has a working credential. Marked UNAVAILABLE, not PASS |
| Repository-wide TODO/mock sweep (§29) | Not run. The legitimate fixtures are labelled in place |

---

## Final E2E result

```
python scripts/dry_run.py --non-interactive     ->  RESOLVED
```

```
[1]  incident injected        revision 12, ticketbooking:1.1, readiness failing
[2]  tickets created          TKT-101, TKT-102, TKT-103
[3]  MCP evidence collected   6 tools
[4]  correlation              3 tickets -> 1 incident, 0 excluded
[5]  AI analysis              root cause proposed
[6]  proposal                 restart_deployment -> PENDING_APPROVAL
[7]  human review required
[8]  REJECTED with feedback   cluster asserted UNCHANGED
[9]  revised analysis         restart_deployment -> rollback_deployment{to_revision:11}
[10] approval received
[11] remediation executed
[12] verification             rollout_healthy=True, health_endpoint=True -> PASS
[13] incident closed          RESOLVED
```

Also, against a **live k3s cluster**: `bash scripts/validate.sh` → 29
assertions, 0 failures.

---

## Known limitations

**No AI provider has produced a live analysis.** Every record reads
`analysis_source: "unavailable"`, or `"fixture"` for the dry run. The dry run
prints this at the end rather than letting the RESOLVED status imply reasoning
happened. This is the single largest gap and it is a credentials problem, not
a code one — the reasoning path is implemented, contract-tested, and its
failure policy verified.

**The dry run's cluster is a fixture.** Correlation, the approval gate, the
executor allowlist, the verifier and the audit trail are the real code paths;
only the thing being observed and mutated is simulated. The live proof is
`scripts/validate.sh`.

**The dry run's reasoner is scripted** when no engine is reachable, stamped
`fixture` so it cannot be mistaken for a model.

**Incidents live in memory.** The API and CLI each hold their own; records on
disk are the durable artifact.

**Correlation is done twice** — deterministically in Python and again by the
model — and the two are not reconciled. Open decision, `docs/21_DECISIONS.md`
ADR-007.

## Remaining submission risks

1. **No live IBM reasoning.** The closest available fix needs no credentials:
   run the incident inside the IBM Bob IDE with `AI_PRIMARY_PROVIDER=host`.
   `SHIVRAJ_DOCS/08_BOB_RUNBOOK.md` has the exact prompts.
2. **A Gemini provider now exists in an IBM Bob project.** It is a fallback,
   not the default, and `docs/19_HACKATHON_COMPLIANCE.md` records that the
   rules do not prohibit it. A judge scanning filenames may still read it as
   mixed signals — worth a sentence in the submission if it stays.
3. **Both API keys used in testing were pasted into a chat transcript.**
   Rotate them. Neither is committed.
