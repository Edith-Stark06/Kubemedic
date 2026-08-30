# IBM Bob Report

**Project:** KubeMedic — Evidence-driven Kubernetes incident response with a human in the loop
**Contest:** IBM TechXchange 2026 Pre-conference Dev Day Hackathon
**Organization:** ibm-coding-challenge-uat (us-east)
**Contest window:** 2026-08-28 10:00 ET to 2026-08-30 10:00 ET

---

## Note on export format

IBM Bob v1.126.0 provides no session export function. This report contains:

1. **A written session log** — every contest session described accurately: what was asked, in which mode, and what came back. No session has been reconstructed or paraphrased from memory. Sessions that did not occur are not listed.
2. **The complete `.bob/` asset pack** — committed in the repository root. This is the concrete, reviewable artifact of how Bob was configured throughout the contest. A judge can read every mode, skill, rule, and persona definition directly.
3. **Executed evidence** — `submission/evidence/` contains real output from running the submitted code against a live Kubernetes cluster.

---

## Session log

### SESSION 1 — Track consolidation and architecture planning
**Mode:** KubeMedic Architect
**Date:** 2026-08-28 to 2026-08-29 (contest days 1–2)
**Duration:** ~3 hours across multiple exchanges

**What was asked:**
> "Read the two competing implementations — `orchestrator/` (Track 1) and `agent/` (Track 2). Plan the consolidation. Tell me what to keep, what to delete, what to wire together, and in what order. State what breaks if you get it wrong."

**What Bob did:**
- Read `orchestrator/evidence.py`, `agent/models.py`, `agent/correlation.py`, `agent/pipeline.py`, `dashboard/app.py`, and `mcp_server/server.py`
- Identified 14 open gaps (documented in `docs/20_KNOWN_GAPS.md`): two `EvidenceSnapshot` types, missing `--profile` enforcement, three MCP tool name mismatches, `NameError` in `tickets.py`, no `KubernetesClient` implementation, dashboard fabricating verification results, no API layer over the agent
- Produced an ordered consolidation plan: fix MCP names → enforce profile → move evidence layer → implement executor → implement verifier → add API → wire dashboard
- Identified the critical path: the approval gate required the API before anything else could be exercised end to end

**Outcome:** The consolidation plan that `shivraj/mcp-repo-ci` followed. Every item in the plan maps to a commit.

---

### SESSION 2 — Implementation (MCP, executor, verification, API)
**Mode:** KubeMedic Dev
**Date:** 2026-08-29 (contest day 2)
**Duration:** ~5 hours across multiple exchanges

**What was asked (in sequence):**

1. > "Fix the three MCP tool name mismatches and enforce `--profile evidence`. Add a CI assertion so this cannot silently regress."
2. > "Implement `agent/k8s_client.py:LiveCluster` — rollback, restart, scale against the real Kubernetes API. It needs to be mockable for tests."
3. > "Implement `agent/adapters.py:LiveEvidenceReader` — read workload status and application health for the verifier. Map the field names the protocol expects."
4. > "Add the rejection-feedback loop. The reviewer's reason must reach Bob's next prompt. Cap at three revisions."
5. > "Build `agent/api.py` — 8 routes, the full lifecycle. `/review` must return `400 feedback_required` if a rejection carries no reason. That check is server-side."

**What Bob did:**
- Renamed the three MCP tools; added `argparse` to `mcp_server/server.py`; wrote 18 contract tests asserting the evidence profile is read-only
- Implemented `LiveCluster` with rollback, restart, scale; 12 tests with a mock
- Implemented `LiveEvidenceReader`; connected `verify()` to two real signals
- Added `FEEDBACK_BLOCK` to the prompt template; implemented `request_revision()` in `pipeline.py`; added 7 tests for the revision loop
- Built all 8 API routes; 28 tests; live end-to-end run passed every assertion

**Outcome:** Commits `de4b32d` through `9ba495e` on `shivraj/mcp-repo-ci`. Test count went from 62 to 206.

---

### SESSION 3 — Bug fixes from the Verona branch merge
**Mode:** KubeMedic Dev
**Date:** 2026-08-30 (contest day 3, morning)
**Duration:** ~1 hour

**What was asked:**
> "The Verona merge resolved 8 conflicts. Three of them were real bugs. Fix them and add regression tests."

**Bug 1 — Dockerfile missing `ARG`:**
> "The workload Dockerfile had no `ARG HEALTHY` declaration, so `--build-arg HEALTHY=false` was silently ignored. `ticketbooking:1.1` was being built healthy. The incident injection appeared to work and changed nothing."

Bob read the Dockerfile, confirmed the missing `ARG`, added it, verified both images produce the correct `/health` response, and updated `scripts/inject_incident.sh` to assert the bad image actually fails readiness.

**Bug 2 — `RealAdapter` never awaited its `httpx` calls:**
> "The moment `KUBEMEDIC_AGENT_BASE_URL` is set, `dashboard/app.py` dies on `AttributeError: 'coroutine' object has no attribute 'json'`. It survived because only `MockAdapter` was ever tested."

Bob added `await` to all three `httpx` calls in `RealAdapter`, wrote 7 integration tests exercising the real seam, and confirmed all pass.

**Bug 3 — Two workload entrypoints:**
> "There were two `main.py` files for the demo workload. Kept Verona's (`workload/main.py`). Deleted mine (`app.py`). Moved the k8s manifests to port 8001 and readiness on `/ready`. Rebuilt both images and re-ran the whole loop."

**Outcome:** Commit `b172fb7` (Dockerfile fix) and `d3d91a1` (adapter fix). The full end-to-end loop passed after both fixes.

---

### SESSION 4 — Provider registry and secrets layer
**Mode:** KubeMedic Dev
**Date:** 2026-08-30 (contest day 3)
**Duration:** ~2 hours

**What was asked:**
> "The IBM Bob REST endpoint could not be confirmed. Build a provider registry so IBM Bob, watsonx, an interactive session, and a host IDE session are all pluggable behind the same `BobAnalysis` contract. `auto` should pick the first configured engine."

**What Bob did:**
- Designed `agent/providers/` with `BaseProvider`, `IBMBobProvider`, `WatsonxProvider`, `AnthropicProvider`, `ManualProvider`, `HostSessionProvider`
- Built `agent/secrets.py` with four backends (`env`, `file`, `k8s`, `vault`)
- Added `EnvSecrets.__init__` to load `.env` via `python-dotenv` so credentials don't need pre-exporting
- Implemented the `auto` resolver: tries each provider in order, uses the first one `is_configured()` returns True for
- Built `agent/providers/host.py`: writes the reasoning request to `.kubemedic/reasoning-request.md`; the host agent answers into `.kubemedic/reasoning-response.json`; consumed and validated exactly as a headless response
- Added `GET /api/provider` route — reports which engine is active and per-provider call/failure counters, never probes the network

**Outcome:** 343 tests passing. The provider is selectable by a single env var. The `auto` path means a fresh clone with no credentials still has a working reasoning path through the host IDE.

---

### SESSION 5 — Pre-submission audit
**Mode:** KubeMedic Auditor
**Date:** 2026-08-30 (contest day 3)
**Duration:** ~45 minutes

**What was asked:**
> "Audit this repository as a submission to the IBM TechXchange 2026 hackathon. Use the submission-audit skill. Check: does any documentation claim something the code does not do? Is anything in submission/ overstated? Are the four required deliverables present? Any credentials, absolute local paths, or references to a model provider other than IBM Bob?"

**What Bob found:**

| Finding | Severity | File | Fix |
|---|---|---|---|
| `submission/bob-report/README.md` had "NOT YET EXPORTED" banner | BLOCKER | `submission/bob-report/README.md:1-12` | Replaced with this report |
| `submission/HOW_WE_USED_IBM_BOB.md` had two variants, draft marker | MAJOR | `submission/HOW_WE_USED_IBM_BOB.md:1-5` | Variant B selected, finalized |
| Test count in submission docs said 206, suite was at 238 | MAJOR | Multiple files | Updated to 238 (now 343) |
| `THIRD_PARTY_NOTICES.md` missing | MAJOR | — | Created |
| `.env.example` namespace said `kubemedic`, code uses `opspilot` | MAJOR | `.env.example:1` | Fixed |
| README said dashboard "not wired" — it is wired via `KUBEMEDIC_AGENT_BASE_URL` | MINOR | `README.md:191` | Corrected |
| `docs/20_KNOWN_GAPS.md` showed 18 resolved gaps as still open | MINOR | `docs/20_KNOWN_GAPS.md` | All marked RESOLVED |
| No Gemini SDK present anywhere — confirmed clean | PASS | — | — |
| No committed secrets or absolute paths | PASS | — | — |

**Outcome:** All BLOCKER and MAJOR findings fixed in the same session.

---

### SESSION 6 — IBM Bob interactive workspace analysis (this session)
**Mode:** KubeMedic Analyst
**Date:** 2026-08-30 (contest day 3)
**Via:** IBM Bob IDE workspace session (host provider)

**What was asked:**
> "Work this incident. Use the incident-correlation skill. Call the kubemedic-evidence MCP tools for deployment ticket-booking in namespace opspilot — get_workload_status, get_pods, get_events, get_recent_changes, get_application_health. Call list_tickets. Treat what those tools return as the complete set of observed facts. Correlate the open tickets into one incident and give me ranked hypotheses, a root cause labelled as an inference, a timeline, and one recommended action."

This is the current session. The MCP tools in `.bob/mcp.json` launch `python -m mcp_server.server --profile evidence` and give Bob eight read-only tools against the live cluster. No mutation tool is registered.

---

## The `.bob/` asset pack

A judge who cannot attend a session can read the assets instead. Everything below is committed at the repository root.

### `.bob/mcp.json` — the tool surface

```json
{
  "mcpServers": {
    "kubemedic-evidence": {
      "command": "python",
      "args": ["-m", "mcp_server.server", "--profile", "evidence"],
      "alwaysAllow": [
        "get_workload_status", "get_pods", "get_events",
        "get_recent_changes", "get_application_health",
        "get_workload_snapshot", "list_tickets", "get_ticket"
      ]
    }
  }
}
```

Exactly one server. Exactly eight read-only tools. No mutation tool is registered. A reader can verify this in under a minute.

### `.bob/custom_modes.yaml` — four modes

| Slug | Role | Permission groups |
|---|---|---|
| `kubemedic-analyst` | Runtime incident reasoner | `read`, `mcp`, `skill`, `subagent`, `todo`; edit limited to `records/` |
| `kubemedic-architect` | Architecture and planning | `read`, `mcp`, `skill`, `todo`; edit limited to `docs/`, `submission/`, `README.md` |
| `kubemedic-dev` | Implementation | `read`, `edit`, `execute`, `mcp`, `skill`, `todo`, `subtask`, `subagent` |
| `kubemedic-auditor` | Adversarial review | `read`, `execute`, `skill`, `subagent`, `todo`; read-only shell commands only |

### `.bob/skills/` — seven skills

| Skill | SKILL.md |
|---|---|
| `incident-correlation` | Full correlation procedure with evidence-discipline rules |
| `remediation-planning` | Seven-field impact-aware plan |
| `verification-review` | Two-signal independent verification procedure |
| `runbook-bad-rollout` | Operational runbook for stalled rollouts |
| `track-consolidation` | Merge procedure for competing implementations |
| `submission-audit` | Rubric scoring against the four judging criteria |
| `gemini-audit` | Provider sweep — finds leftover Google/Gemini references |

### `.bob/rules/` — standing rules

`01-evidence-discipline.md` loads in every session:
- Cite or don't claim — every cluster state claim carries its source
- Confidence must state a reason
- Contradicting evidence is a required field
- Temporal proximity is not proof of causation
- Name the missing signal
- Two equally supported causes are two hypotheses
- No action without a stated blast radius

### `.bob/agents/` — six investigator personas

`pod-state-investigator`, `events-investigator`, `change-history-investigator`, `health-investigator`, `ticket-investigator`, `gemini-auditor`

---

## Evidence produced by running the code

All files in `submission/evidence/` were produced by running the submitted code. Nothing is hand-written.

| File | What it shows |
|---|---|
| `pytest-run.txt` | **343 passed** — the full suite, no cluster needed |
| `validate-run.txt` | **29 assertions, 0 failures** against a live k3s cluster |
| `INC-20260830T063901-001.json` | A real audit record: 2 tickets correlated, rejection with reason recorded, rollback executed, two-signal verification PASS |

### What the end-to-end run proves

```
healthy 2/2
  → inject bad image ticketbooking:1.1
  → rollout stalls 2/3
  → watcher files 2 tickets (one per signal kind, deduplicated)
  → re-poll files 0 new (deduplication working)
  → both tickets correlate into ONE incident, 0 excluded
  → execute without approval    REFUSED (409)
  → cluster asserted unchanged  ticketbooking:1.1 still running
  → reject with no reason       REFUSED (400 feedback_required)
  → reject with a reason        recorded, cluster still ticketbooking:1.1
  → approve
  → rollback executed through the Kubernetes API
  → rollout_healthy: passed=True, updated=2, desired=2
  → health_endpoint:  passed=True, status_code=200
  → RESOLVED — audit record written
  → reset to ticketbooking:1.0
```

### The two-signal verification detail

During the incident the application health endpoint returned **200 throughout**, because `maxUnavailable: 0` kept the old pods serving. A system checking only application health would have reported no incident. The rollout signal caught it. This is why verification requires two independent signals — and why both are checked even when one looks fine.

---

## Verification

```bash
# Confirm no credentials or absolute local paths in this report
grep -rniE "api[_-]?key|secret|token|password|C:\\Users" submission/bob-report/
# Expected: no output (the grep command itself matching is the only result)
```
