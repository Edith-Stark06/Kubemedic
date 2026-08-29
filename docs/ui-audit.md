# UI Audit — KubeMedic Dashboard & Workload

**Author:** Verona  
**Branch:** `verona`  
**Date:** Phase 0 setup audit — findings only, no code changes  
**Source read:** `origin/ramana` for agent contracts; `origin/main` + `verona` for repo state

---

## Executive summary

`dashboard/` and `workload/` do not exist in the repository. There is nothing
to audit at the code level — no HTML, CSS, JavaScript, or Python app files are
present on `main` or `verona`. The audit therefore serves two purposes:

1. Document the **pre-build state** so the record is clean.
2. Enumerate every **contract requirement** the dashboard must satisfy when
   built, based on reading `agent/` on `origin/ramana` (read-only).
3. Flag the **blocking gap** that will prevent the dashboard from working even
   after it is built.

All findings below are rated as they will apply at build time.

---

## Section 1 — Provider references

**Scope:** `dashboard/`, `workload/`  
**Result:** Both directories absent — zero files to scan.

**Pre-build requirement:** When `dashboard/` is created, every title, label,
badge, button, alt text, favicon, page `<title>`, and HTML comment must be
swept against: `gemini`, `google-genai`, `google.generative`, `genai`,
`GOOGLE_API_KEY`, `GEMINI_API_KEY`, `palm`, `vertexai`.

**Known risk:** Ramana's `.bob/agents/` contains a `gemini-auditor.md` persona
(visible on `origin/ramana`). This is tooling in `.bob/`, not UI copy — it is
not a finding for this lane. No dashboard files exist to carry provider strings.

**Finding 1.1**  
File: `(not yet created)`  
Severity: N/A — pre-build  
Fix: Run gemini-audit skill against `dashboard/` and `workload/` before first
commit of any template file. Cost: 5 min.

---

## Section 2 — Obsolete architecture terms

**Scope:** `dashboard/`, `workload/`  
**Result:** Both directories absent.

Terms to exclude from all UI copy: `OpsPilot`, `orchestrator`, `Track 1`,
`Track 2`. Any endpoint name from a pre-consolidation architecture that does
not appear in Ramana's `agent/` module must also be treated as obsolete.

No findings. Pre-build requirement documented.

---

## Section 3 — Broken endpoints

**Scope:** All `fetch`/`axios`/`XHR` calls in `dashboard/` checked against
`agent/` on `origin/ramana`.  
**Result:** `dashboard/` does not exist.

### Critical finding — NO HTTP API EXISTS

**Finding 3.1**  
File: `agent/` on `origin/ramana`  
Line: entire `agent/` directory  
Quoted text: `pipeline.py` docstring — *"the dashboard calls each stage
individually through the API layer (not yet implemented)"*  
Severity: **BLOCKER**  
Fix: Ramana adds a FastAPI (or Flask) HTTP server to `agent/` exposing the
endpoints listed below. This is a handoff — see Section 5.  
Cost to Verona once the API exists: 0 min (the dashboard fetches are
straightforward once routes are defined).

### Endpoints the dashboard will need (derived from `agent/models.py`)

The following HTTP surface is implied by the pipeline and models. None of it
exists yet. This table is the source of truth for the handoff to Ramana.

| Method | Path | Request body | Response shape | Notes |
|---|---|---|---|---|
| `GET` | `/incidents` | — | `list[Incident]` (summary fields) | List view |
| `GET` | `/incidents/{id}` | — | Full `Incident` JSON | Detail view |
| `POST` | `/incidents/{id}/decision` | `{decision, approver, feedback}` | Updated `Incident` | Human review gate |
| `GET` | `/incidents/{id}/record` | — | `IncidentRecord` JSON | Audit read |

The `feedback` field name on the decision endpoint is critical: Ramana's
`HumanDecision` model validates the field as `feedback`, not `reason` or
`rejection_reason`. The dashboard **must** send `{"feedback": "..."}` or the
server returns 422. See Finding 3.2.

**Finding 3.2**  
File: `agent/models.py` on `origin/ramana`, line ~190  
Quoted text: `feedback: str | None = None` with validator  
`"feedback is required when decision is 'rejected'"`  
Severity: **BLOCKER**  
Fix: Dashboard rejection POST must send field named `feedback`, not `reason`.
This is a naming trap — the UI skill uses the word "Rejection Reason" as a
label, but the wire field is `feedback`. Confirm before building the form.  
Cost: 5 min (field name in one `fetch` call).

**Finding 3.3 — State name drift**  
The `incident-ui-flow` skill lists state `ANALYZED` (US spelling). Ramana's
`IncidentState` enum uses `ANALYSED` (British spelling). The `PLAN_PROPOSED`
state in the skill does not exist in the enum — Ramana uses `PENDING_APPROVAL`.
`AWAITING_HUMAN_REVIEW` does not exist — Ramana uses `PENDING_APPROVAL` for
that concept. `DETECTED` does not exist — Ramana uses `OPEN`.
`EVIDENCE_COLLECTION_FAILED` does not exist — Ramana uses `EVIDENCE_FAILED`.
`FEEDBACK_REQUIRED` does not exist in the enum.
`NOT_EXECUTED` does not exist — Ramana uses `FEEDBACK_RECORDED`.

Full mapping (skill → actual enum value):

| Skill / Prompt term | `IncidentState` enum value |
|---|---|
| `DETECTED` | `OPEN` |
| `EVIDENCE_COLLECTED` | `EVIDENCE_COLLECTED` ✅ |
| `ANALYZED` | `ANALYSED` |
| `PLAN_PROPOSED` | `PENDING_APPROVAL` |
| `AWAITING_HUMAN_REVIEW` | `PENDING_APPROVAL` |
| `APPROVED` | `APPROVED` ✅ |
| `EXECUTING` | `EXECUTING` ✅ |
| `VERIFYING` | `EXECUTED` (verification runs synchronously, no VERIFYING state) |
| `VERIFIED` | `VERIFIED` ✅ |
| `RESOLVED` | `RESOLVED` ✅ |
| `REJECTED` | `REJECTED` ✅ |
| `FEEDBACK_REQUIRED` | (no equivalent — jumps direct to `FEEDBACK_RECORDED`) |
| `FEEDBACK_RECORDED` | `FEEDBACK_RECORDED` ✅ |
| `NOT_EXECUTED` | `FEEDBACK_RECORDED` |
| `EVIDENCE_COLLECTION_FAILED` | `EVIDENCE_FAILED` |
| `BOB_UNAVAILABLE` | `BOB_UNAVAILABLE` ✅ |
| `VERIFICATION_FAILED` | `VERIFICATION_FAILED` ✅ |

Severity: **MAJOR** — the dashboard must use the actual enum values returned
by the API, not the names from the skill document.  
Fix: Build the dashboard's state-to-display-label map using the real enum
values as keys. The skill names can be used as display labels.  
Cost: 15 min (write the mapping table once, reference it everywhere).

### The `contradicting_evidence` and `is_inference` fields

Both exist in `agent/models.py` (`Hypothesis.contradicting_evidence` and
`RootCause.is_inference`) and in `evidence-schema.md`. They must be rendered.

**Finding 3.4**  
File: (not yet created — `dashboard/`)  
Severity: **MAJOR**  
Fix: When building the analysis panel, render `contradicting_evidence` for
every hypothesis even when it contains `["none found in available evidence"]`.
When `root_cause.is_inference` is `true`, display an "INFERENCE" label beside
the statement. Cost: 20 min.

### Verification signals

Ramana's `VerificationResult` has a `signals` array of `VerificationSignal`
objects: `{name, passed, detail}`. The dashboard must render both signals
separately. Signal names are `rollout_healthy` and `health_endpoint`.

**Finding 3.5**  
File: (not yet created — `dashboard/`)  
Severity: **BLOCKER** (for the dual-signal demo moment)  
Fix: Render each `VerificationSignal` in its own panel cell with name, pass/fail
word, and detail string. Never merge into one boolean. Cost: 20 min.

---

## Section 4 — Vocabulary drift

**Scope:** `dashboard/`, `workload/`  
**Result:** Both directories absent.

Approved vocabulary: `Incident`, `Evidence`, `Correlation`, `Root Cause`,
`IBM Bob Analysis`, `Remediation Plan`, `Human Final Review`, `Approve`,
`Reject`, `Rejection Reason`, `Executing`, `Verification`, `Verified`,
`Resolved`.

Banned vocabulary: `AI Fix`, `Auto-Heal`, `Self-Healing`, `autonomous`,
`Magic Repair`, `"the AI will fix this"`, `"automatically resolves"`.

No findings (no files). Pre-build requirement documented.

---

## Section 5 — Missing states

**Scope:** `dashboard/`  
**Result:** No dashboard exists — all states are missing.

States to render, using actual `IncidentState` enum values:

| Enum value | Display label | Notes |
|---|---|---|
| `OPEN` | Detected | Entry state |
| `EVIDENCE_COLLECTED` | Evidence Collected | |
| `EVIDENCE_FAILED` | Evidence Collection Failed | FAILURE STATE — must name missing signal |
| `ANALYSED` | Analysed | |
| `BOB_UNAVAILABLE` | IBM Bob Unavailable | FAILURE STATE — no analysis panel shown |
| `PENDING_APPROVAL` | Awaiting Human Review | Shows approve/reject controls |
| `APPROVED` | Approved | Controls replaced with decision record |
| `REJECTED` | Rejected | |
| `FEEDBACK_RECORDED` | Action Not Executed | Equivalent to NOT_EXECUTED |
| `EXECUTING` | Executing | |
| `EXECUTED` | Executing (complete) | Transient — triggers verification |
| `VERIFIED` | Verified | |
| `RESOLVED` | Resolved | |
| `VERIFICATION_FAILED` | Verification Failed | FAILURE STATE — both signals shown, incident stays open |

Note: there is **no `VERIFYING` state** in the enum. Verification runs
synchronously — the transition goes `EXECUTED → RESOLVED` or
`EXECUTED → VERIFICATION_FAILED`. The dashboard should not show a "Verifying…"
spinner that waits for a separate state change.

**Finding 5.1**  
Severity: **BLOCKER** (all states missing — dashboard does not exist)  
Fix: Build the full state machine rendering as described above.

---

## Section 6 — Legibility

**Scope:** `dashboard/` CSS  
**Result:** No CSS exists.

Requirements when building (from `filmable-ui` skill):
- Body text ≥ 16px
- Monospace / evidence blocks ≥ 14px
- Contrast ≥ 7:1 for all body text
- No `text-overflow: ellipsis` or `-webkit-line-clamp` on root cause statements,
  rejection reasons, evidence citations, or error messages
- No animation > 150ms on informational content
- Status badge: large, high-contrast, fixed top position, does not move between states
- Design target: 1920×1080; check at 1280×720

No findings. Pre-build requirements documented.

---

## Section 7 — Development leftovers

**Scope:** `dashboard/`, `workload/`  
**Result:** Both directories absent.

Pre-build requirements:
- No `console.log` in shipped code
- No hardcoded `http://localhost:*` in any template or JS file visible to the browser
- No lorem ipsum, TODO/FIXME in rendered text
- No real person's name in sample/test data

---

## Section 8 — Workload

**Scope:** `workload/`  
**Result:** Directory absent.

What the workload must expose (from `demo-workload` skill):

| Endpoint | Behaviour |
|---|---|
| `GET /` | Landing page |
| `GET /health` | 200 while process is up — **must be honest** |
| `GET /ready` | 200 only when can serve bookings |
| `POST /book` | Create booking, return BK-prefixed id |
| `GET /bookings` | List bookings (readback after POST /book) |

**Failure lever requirements:**
- Must produce symptom within ~20 seconds
- Must create a real deployment revision (so rollout history has something true)
- Must be reversible in under 30 seconds
- Must be idempotent and safe to run repeatedly

**Dual-signal requirement (`maxUnavailable: 0`):**  
A failed rollout with `maxUnavailable: 0` leaves previous revision pods serving
traffic. This produces the project's key demo moment:
`Kubernetes rollout: DEGRADED` + `Application health: 200 OK` — both true,
neither sufficient alone. Do not "fix" this.

**Sanity check:**  
`POST /book` → `GET /bookings` must return the booking. This is what
verification asserts. If this does not work, the demo has no ending.

**Finding 8.1**  
Severity: **BLOCKER** (workload does not exist)  
Fix: Build FastAPI workload per the `demo-workload` skill.

---

## Summary question

> *Watching only this UI, would a judge conclude the reasoning is done by IBM Bob?*

**Not applicable** — no UI exists. There is nothing for a judge to watch.

Once built, the dashboard must:
1. Label the analysis panel explicitly as **IBM Bob Analysis**
2. Show `analysis_source: "ibm-bob"` in the audit panel
3. Never show a generic "AI" label without naming IBM Bob specifically
4. Render the `BOB_UNAVAILABLE` state with that exact label
5. Not contain strings like "Gemini", "Google", "GPT", or "AI Fix"

---

## Findings registry

| # | File | Severity | Description | Cost (min) | Owner |
|---|---|---|---|---|---|
| 3.1 | `agent/` (no HTTP API) | BLOCKER | No HTTP API layer exists — dashboard has nothing to call | 0 (Verona) | Ramana → see handoff |
| 3.2 | `agent/models.py` | BLOCKER | Rejection field name is `feedback`, not `reason` — must match exactly | 5 | Verona (at build) |
| 3.3 | `dashboard/` (future) | MAJOR | State enum name drift between skill doc and actual `IncidentState` | 15 | Verona (at build) |
| 3.4 | `dashboard/` (future) | MAJOR | `contradicting_evidence` and `is_inference` must render | 20 | Verona (at build) |
| 3.5 | `dashboard/` (future) | BLOCKER | Verification signals must render separately, never merged | 20 | Verona (at build) |
| 5.1 | `dashboard/` (future) | BLOCKER | All 14 incident states must render | — | Verona (at build) |
| 8.1 | `workload/` (future) | BLOCKER | Workload does not exist | — | Verona (at build) |

**BLOCKER count: 5** (1 blocking on Ramana's API, 4 blocking on build)  
**MAJOR count: 2**  
**MINOR count: 0**

The single most urgent issue before the dashboard can be wired up: **Ramana must
deliver an HTTP API layer.** Without it, the dashboard can be built and demoed
against mock data but cannot serve a real incident lifecycle end-to-end.
