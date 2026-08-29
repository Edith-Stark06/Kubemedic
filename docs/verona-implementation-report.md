# Verona — Frontend & Workload Implementation Report

**Author:** Verona  
**Branch:** `verona`  
**Date:** Phase 0 — inspection only, no code changed  
**Branches read:** `origin/main`, `origin/ramana`, `origin/verona`

---

## 1. Current dashboard architecture

**There is no dashboard.**

No `dashboard/` directory exists on any branch (`main`, `ramana`, `verona`).
This is a greenfield build. Every file in the dashboard will be created by
Verona from scratch.

The backend pipeline it will call is implemented on `origin/ramana` as a
pure-Python library (`agent/`). That library has **no HTTP server** — no
FastAPI, no Flask, no routes. The `pipeline.py` docstring explicitly labels
it: *"the API layer (not yet implemented)"*.

---

## 2. Current dashboard entry point

**None.** No `index.html`, no server entrypoint, no static file directory.

---

## 3. Current frontend technologies

**None selected yet.** The project's standing rule (from `SETUP_VERONA.md`
and `01-ui-contract.md`) is:

> No new frontend framework, no build step, no npm install, no CDN link.
> Whatever the dashboard is written in today, keep it.

Since nothing exists, Verona has full choice — subject to the constraint that
no build toolchain is introduced (no Webpack, no Vite, no React). The
practical options consistent with those rules:

- **Vanilla HTML + CSS + JavaScript** — plain files served by a simple Python
  HTTP server or FastAPI static mount. Zero dependencies, maximum reliability
  under a deadline.
- **Jinja2 templates** (served by FastAPI) — allows server-side rendering of
  incident state, which eliminates the need for a client-side fetch layer
  during early development.

No decision has been committed. The recommendation from `SETUP_VERONA.md` is
to keep whatever exists; since nothing exists, vanilla + FastAPI is the safest
choice.

---

## 4. Existing pages and components

**None.** Zero HTML files, zero CSS files, zero JavaScript files exist in
the repository on any branch.

---

## 5. Existing API calls

**None.** No frontend code exists, therefore no API calls exist.

The API that the dashboard will call does not exist either (see item 1 above).

What *does* exist on `origin/ramana`: the full pipeline Python library.
The dashboard will need an HTTP layer placed in front of it before it can
call anything real. See item 21 (Ramana dependencies).

---

## 6. Existing incident UI

**None.**

---

## 7. Existing ticket UI

**None.**

---

## 8. Existing remediation UI

**None.**

---

## 9. Existing approval UI

**None.**

---

## 10. Existing rejection UI

**None.**

---

## 11. Existing timeline/status UI

**None.**

---

## 12. Current workload implementation

**There is no workload.** No `workload/` directory exists on any branch.

The ticket-booking demo app described in `demo-workload/SKILL.md` does not
exist yet. Its spec is documented; its code is not written.

Required endpoints per the skill:

| Endpoint | Behaviour |
|---|---|
| `GET /` | Landing page — establishes the app is alive |
| `GET /health` | 200 while process is up; must be honest |
| `GET /ready` | 200 only when can actually serve bookings |
| `POST /book` | Create booking; return BK-prefixed id |
| `GET /bookings` | List all bookings (readback verification) |

Required failure lever: an environment variable (`HEALTHY=false` or equivalent
bad image tag) that within ~20 seconds produces pods that fail their readiness
probe, creates a real deployment revision in rollout history, and is
reversible in under 30 seconds.

Required dual-signal property: `maxUnavailable: 0` so a failed rollout leaves
the previous revision serving traffic — producing `rollout DEGRADED` + `health
200 OK` simultaneously.

---

## 13. Current Kubernetes manifests relevant to the demo

**No `k8s/` directory exists on any branch.**

The manifests needed for the demo (Deployment, Service, possibly a Namespace)
do not exist yet. These are Shivraj's responsibility. What Verona needs to
know about them is:

- The deployment must be named `ticket-booking` (matches `KUBERNETES_DEPLOYMENT`
  in `.env.example`).
- The namespace must be `kubemedic` (matches `KUBERNETES_NAMESPACE`).
- The `maxUnavailable: 0` rollout strategy is required for the dual-signal demo
  moment.
- The deployment must support the failure lever (either via env var or image tag
  swap) without requiring a manual `kubectl` command — the failure must be
  triggerable from a script.

---

## 14. Current incident injection and reset mechanism

**No `scripts/` directory exists on any branch.**

No injection script (`break.sh`, `inject-failure.py`, etc.) or reset script
(`reset.sh`) has been written. These are Shivraj's directory (`scripts/`).

What Verona needs from the reset mechanism: after reset, the dashboard must
start from a clean view — no active incident, no pending decision. If the reset
clears `records/` or archives incidents, the dashboard must handle an empty
incident list gracefully (not an error state, not a blank screen with no copy).

---

## 15. What already works

On `origin/ramana` (Ramana's branch, **not yet merged to main**):

| Component | Status |
|---|---|
| `agent/models.py` | Complete. All Pydantic models for the full lifecycle. 62 tests pass. |
| `agent/correlation.py` | Complete. Deterministic ticket grouping with exclude logic. |
| `agent/reasoning.py` | Complete. Bob bridge — calls IBM Bob REST, validates JSON output. |
| `agent/bob.py` | Complete. IBM Bob REST adapter with `bob_unavailable` fallback. |
| `agent/pipeline.py` | Complete. End-to-end `run_full_pipeline()` wiring all stages. |
| `agent/executor.py` | Complete. Allowlisted Kubernetes actions, approval guard. |
| `agent/verification.py` | Complete. Two-signal verification (rollout + health endpoint). |
| `agent/audit.py` | Complete. `record_decision()` with server-side feedback validation; `write_record()` to `records/`. |
| `tests/` (62 tests) | Pass. Cover models, correlation, lifecycle, rejection path, executor safety. |
| `.bob/` asset pack | Complete. Modes, skills, agents, MCP config. |
| `docs/handoffs.md` | Started (Ramana's entry #1). |
| `docs/consolidation-inventory.md` | Written. |

On `origin/verona` (Verona's branch):

| Component | Status |
|---|---|
| `docs/ui-audit.md` | Written. Findings from Phase 0. |
| `docs/handoffs.md` | Written. Entries #1–#3 (carries Ramana's #1 forward plus two new). |
| `~/.bob/` tooling | Installed globally (not committed). 3 modes, 8 skills, 4 personas. |

---

## 16. What is incomplete

| Gap | Owner | Blocking? |
|---|---|---|
| HTTP API layer (`agent/api.py` or `agent/main.py`) | Ramana | **YES — blocks all real dashboard fetches** |
| `dashboard/` — entire frontend | Verona | — |
| `workload/` — ticket-booking FastAPI app | Verona | — |
| `k8s/` — Deployment + Service manifests | Shivraj | YES — needed for end-to-end demo |
| `scripts/` — break/reset scripts | Shivraj | YES — needed for demo recording |
| `mcp_server/` — evidence MCP server | Shivraj | YES — needed for real incident pipeline |
| `DEMO.md` — demo runbook | Verona | No (write late in project) |
| `README.md` — actual content | Ramana? | No |

---

## 17. What is broken

Nothing is "broken" in the sense of regression — the repository has no
frontend code to break. The architectural gap that matters most:

**The agent pipeline is a library with no HTTP interface.** `pipeline.py`
documents this explicitly. Until Ramana exposes the pipeline via HTTP routes,
the dashboard must operate against mock/fixture data. That is viable for
development but not for the final recording.

**State name drift between documentation and code.** The `incident-ui-flow`
skill and the prompt use state names that differ from the actual
`IncidentState` enum. Full mapping:

| Docs/skill term | Actual `IncidentState` enum value |
|---|---|
| `DETECTED` | `OPEN` |
| `ANALYZED` | `ANALYSED` |
| `PLAN_PROPOSED` | `PENDING_APPROVAL` |
| `AWAITING_HUMAN_REVIEW` | `PENDING_APPROVAL` |
| `VERIFYING` | *(does not exist — synchronous, goes direct to RESOLVED or VERIFICATION_FAILED)* |
| `EVIDENCE_COLLECTION_FAILED` | `EVIDENCE_FAILED` |
| `NOT_EXECUTED` | `FEEDBACK_RECORDED` |
| `FEEDBACK_REQUIRED` | *(does not exist — jumps direct to FEEDBACK_RECORDED)* |

The dashboard state-to-display-label map must use the actual enum values as
keys. The skill names can be used as the human-readable display labels.

**Rejection field name.** The `HumanDecision` model validates `feedback` (not
`reason`, not `rejection_reason`). The POST body the dashboard sends must use
`{"feedback": "..."}` exactly. See handoff #2.

---

## 18. What should be reused

| Asset | How to reuse |
|---|---|
| `agent/models.py` on `origin/ramana` | Read the Pydantic model definitions. Use the exact field names in the dashboard's JSON parsing code — never guess field names. |
| `.bob/skills/incident-correlation/references/evidence-schema.md` | The frozen JSON shape of a Bob analysis. Render only fields that exist in it. Any field not in the schema must come from a handoff, not from client-side derivation. |
| `docs/handoffs.md` | Append to it, never overwrite. |
| `AGENTS.md` | Read-only standing instructions. Do not edit. |

---

## 19. What Verona must build

In priority order for the demo:

### A — Workload (`workload/`)
1. FastAPI app with `GET /`, `GET /health`, `GET /ready`, `POST /book`,
   `GET /bookings`. In-memory storage. Structured JSON logging.
2. Dockerfile: healthy image (`HEALTHY=true`) and failure image
   (`HEALTHY=false`) — or a single image with an env-var lever.
3. `maxUnavailable: 0` rollout strategy (this is a manifest concern — file a
   handoff to Shivraj if the k8s manifest doesn't set it).

### B — Dashboard (`dashboard/`)

Panel build order (each can be reviewed independently before the next):

1. **Incident list view** — load incidents from API, show id/state/workload,
   empty state when list is empty.
2. **Header + status badge** — incident id, `IncidentState` display label (using
   actual enum values), workload, time. Badge readable at a glance.
3. **Correlation panel** — many-to-one SVG/CSS funnel showing member tickets
   converging into one incident, `correlation_basis` reasons, `excluded_tickets`
   shown outside the funnel.
4. **Evidence panel** — pod states with ready counts and images, events, rollout
   history, application health.
5. **IBM Bob Analysis panel** — explicitly labelled as Bob's. Root cause with
   `is_inference` label when true. Confidence with `confidence_reason`. All
   hypotheses. `contradicting_evidence` rendered even when it says "none found".
6. **Proposed Remediation panel** — action, target, blast radius, risk with
   `risk_explanation`, reversibility, expected effect, verification plan.
   `notes_for_reviewer` rendered prominently.
7. **Human Final Review panel** — approve + reject controls, visible only in
   `PENDING_APPROVAL` state. Above the controls: action, target, blast radius,
   risk + reason, verification plan — visible without scrolling.
8. **Rejection dialog** — restates action being rejected, autofocuses textarea,
   disables submit on empty/whitespace, cancel with no state change.
9. **Post-decision display** — replaces controls after decision. Approved and
   rejected outcomes. Rejection shows reason verbatim + "Action executed: NO".
10. **Dual-signal verification panel** — `rollout_healthy` and `health_endpoint`
    signals side by side as two independent readings. `VERIFICATION_FAILED` state
    is loud and keeps the incident open.
11. **Timeline panel** — all `audit_log` entries in order with timestamps.
12. **Audit panel** — structured record from `IncidentRecord`.
13. **Three failure states** — `EVIDENCE_FAILED`, `BOB_UNAVAILABLE`,
    `VERIFICATION_FAILED` — each with clear copy, no analysis panel shown for
    the first two.

### C — Demo documents
- `DEMO.md` — reset runbook, exact commands in order, what "it worked" looks like.
- `docs/demo-script.md` — shot list and narration.

---

## 20. Exact files likely to be changed

All new (none exist yet):

```
dashboard/
  index.html              Incident list / entry point
  incident.html           Incident detail view
  static/
    style.css             All styles (16px+ body, 7:1 contrast, no animation on content)
    app.js                Fetch layer, state rendering, review controls
    correlation.svg.js    SVG funnel builder (or inline SVG template)

workload/
  main.py                 FastAPI app — 5 endpoints + failure lever
  Dockerfile              Single image with HEALTHY env var
  requirements.txt        fastapi, uvicorn (minimal)

DEMO.md                   Demo runbook
docs/demo-script.md       Shot list and narration
docs/handoffs.md          Append-only; Verona adds entries as needed
```

Files Verona reads but **never edits** (even if a bug is visible):

```
agent/           — Ramana's lane
.bob/            — Ramana's lane
mcp_server/      — Shivraj's lane (does not exist yet)
k8s/             — Shivraj's lane (does not exist yet)
scripts/         — Shivraj's lane (does not exist yet)
AGENTS.md        — Ramana's lane
```

---

## 21. Dependencies on Ramana's consolidated backend

| Dependency | What Verona needs | Current status | Blocking? |
|---|---|---|---|
| HTTP API | Routes: `GET /incidents`, `GET /incidents/{id}`, `POST /incidents/{id}/decision`, `GET /incidents/{id}/record` | **Does not exist** | **YES — blocks real wiring** |
| Field name contract | Rejection POST body field must be `feedback` (confirmed in `HumanDecision.feedback`) | Confirmed from `agent/models.py` | No new work; Verona must match it |
| `IncidentState` enum (closed set) | Dashboard needs the final closed set of state values. No `VERIFYING` state exists. `PENDING_APPROVAL` covers both plan-proposed and awaiting-review. | Confirmed from `agent/models.py` | Handoff #3 filed to confirm no new states will be added silently |
| `evidence-schema.md` | The frozen analysis JSON shape. Verona renders only fields in it. | Exists on `origin/ramana` at `.bob/skills/incident-correlation/references/evidence-schema.md` | No — Verona can read it now |
| `BobAnalysis` field names | `contradicting_evidence`, `is_inference`, `confidence_reason`, `notes_for_reviewer`, `dual_signal_note` | All confirmed in `agent/models.py` | No — confirmed |
| Verification signals | `VerificationSignal.name` values: `rollout_healthy`, `health_endpoint` | Confirmed in `agent/verification.py` | No — confirmed |
| `IncidentRecord` shape | Audit panel display; `rejection_feedback`, `bob_analysis`, `root_cause` snapshot fields | Confirmed in `agent/models.py` | No — confirmed |

---

## 22. Dependencies on Shivraj's MCP/server work

| Dependency | What Verona needs | Current status | Blocking? |
|---|---|---|---|
| `mcp_server/` | Evidence collection for real incidents. The dashboard does not call MCP directly — the pipeline does. | Does not exist | Not blocking for UI build; blocking for real end-to-end demo |
| `k8s/` manifests | Deployment with `name: ticket-booking`, `namespace: kubemedic`, `maxUnavailable: 0` strategy | Do not exist | Not blocking for UI build; blocking for demo recording |
| `scripts/` break/reset | Failure injection and clean reset scripts | Do not exist | Not blocking for UI build; blocking for demo recording |
| `--profile evidence` MCP flag | Exposes only read-only tools to Bob (handoff #1 from Ramana) | Open (filed as handoff #1) | Blocking for safety claim verification, not for dashboard build |

---

## Summary

The repository is **greenfield for Verona's lane.** Nothing in `dashboard/`
or `workload/` exists on any branch. The backend agent pipeline (`agent/`) is
fully implemented on `origin/ramana` with 62 passing tests, but has **no HTTP
interface** — that is the single most urgent cross-lane dependency before the
dashboard can be wired up for a live demo.

The recommended build order:

1. **Build the workload first.** It is smaller, self-contained, and the demo
   has no stakes without something to break.
2. **Build the dashboard against mock data.** Use hardcoded fixture JSON shaped
   like `BobAnalysis` / `Incident` from `agent/models.py` — the real field
   names are known, so mock data binds to the real contract.
3. **Wire to Ramana's HTTP API** when it exists. The fetch layer should be one
   JS file; swapping from mock to real is a one-line change per endpoint.
4. **Harden failure states and the rejection dialog** before the first
   Playwright walkthrough.
5. **Record a backup take** after the first full dress rehearsal, per
   `demo-reset/SKILL.md`.
