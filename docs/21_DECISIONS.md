# 21 — Decisions (ADR log)

`ACCEPTED` = evidenced in the repository. `PROPOSED` = recommended here, not
yet agreed. No dates are invented — where a decision predates this audit, the
date is the commit that shows it.

---

## ADR-001 — Track 2 (`agent/`) is the submission architecture

- **Status:** ACCEPTED
- **Date:** 2026-08-29 (visible in commits `317c979`, `6af80d4`, `5e1743f` on `ramana`)
- **Context:** two implementations existed. `orchestrator/` (Track 1) and
  `agent/` (Track 2) both contained correlation, hypothesis, plan, executor,
  verification and record modules.
- **Options:** (a) keep Track 1; (b) keep Track 2; (c) maintain both.
- **Chosen:** (b).
- **Reason:** Track 2 is typed end to end, has 62 passing tests, and has a
  single reasoning boundary. Track 1 has no tests on this branch.
- **Consequences:** `orchestrator/` must disappear. Only `evidence.py` still
  blocks that, because `mcp_server` imports it (`MCP-003`).

## ADR-002 — MCP is the evidence and tool layer; it never reasons

- **Status:** ACCEPTED
- **Evidence:** `AGENTS.md` "The AI boundary"; `.bob/mcp.json` `//safety`;
  `mcp_server/tools.py` returns evidence only; no mutation tool is registered.
- **Consequences:** the read-only claim must be *enforced*, not merely true by
  omission — `MCP-002`. Note `create_ticket` and `update_ticket_status` mutate
  the ticket store and are currently exposed on the evidence profile.

## ADR-003 — Human rejection requires feedback

- **Status:** ACCEPTED at the model layer; **GAP** at the HTTP layer.
- **Evidence:** `HumanDecision._require_feedback_on_rejection` raises on empty
  or whitespace feedback; twelve tests cover the rejection path.
- **Gap:** `dashboard/app.py:ApproveRejectBody` has no `feedback` field.
- **Consequences:** `REVIEW-001` must enforce this server-side and return
  `400 feedback_required`, not rely on a UI `required` attribute.

## ADR-004 — Human feedback becomes reasoning context

- **Status:** **PROPOSED — not implemented**
- **Context:** feedback is captured, validated, audited and persisted in
  `IncidentRecord.rejection_feedback`, and then read by nothing.
  `PROMPT_TEMPLATE` has no slot for it.
- **Options:** (a) leave rejection terminal; (b) feed the reason into the next
  Bob call and produce a revised plan; (c) let a human edit the plan directly.
- **Recommended:** (b). It is the project's differentiating feature and the
  thing the orchestrator brief asks for.
- **Consequences:** needs a feedback field on `Incident`, a prompt slot, a
  parameter through `run_analysis()`, a `FEEDBACK_RECORDED -> ANALYSED`
  transition, and a **revision cap** so reject/revise cannot spin.
  `_ILLEGAL_TRANSITIONS` already blocks `FEEDBACK_RECORDED -> EXECUTING`, so
  the loop cannot create a path from rejection to execution — that guard is
  what makes this safe to attempt. Task `REVIEW-002`.

## ADR-005 — The executor is deterministic and allowlisted

- **Status:** ACCEPTED
- **Evidence:** `AllowedAction` is a closed enum of three;
  `BobAnalysis.from_raw` rejects anything else before parsing; `_dispatch` maps
  the enum to typed method calls; no `subprocess`, `os.system`, `eval` or
  `exec` anywhere in `agent/`. `test_action_enum_rejects_kubectl_string`.
- **Consequences:** adding an action means adding an enum member, a dispatch
  branch, a `KubernetesClient` method **and** a test — deliberately four
  places, so it cannot happen by accident.

## ADR-006 — Verification is independent and dual-signal

- **Status:** ACCEPTED in `agent/`; **VIOLATED** in `dashboard/`.
- **Evidence:** `verify()` re-reads the cluster on two independent sources —
  the control plane's rollout view and the application answering HTTP through
  the Service. `INCONCLUSIVE` is checked before `FAIL`, so "we could not tell"
  is never reported as "it did not work". Neither is ever softened to `PASS`.
- **Violation:** `dashboard/app.py:_decide()` derives six verification results
  from the `approved` boolean.
- **Consequences:** `DASH-001` is P0 on integrity grounds, not just UX.

## ADR-007 — Who owns correlation?

- **Status:** **PROPOSED — open, needs a decision**
- **Context:** `agent/correlation.py` correlates deterministically (2 of 3
  signals) and its docstring says *"Bob receives the correlated evidence; it
  does not perform the correlation."* But `PROMPT_TEMPLATE` asks Bob to use the
  `incident-correlation` skill, and `BobAnalysis.correlation` holds Bob's own
  result. Both are produced; nothing reconciles them.
- **Options:**
  - (a) Python correlates; Bob is told the grouping and reasons only about
    cause. Simple; weakens the "Bob correlates" claim.
  - (b) Python pre-filters candidates; Bob makes the final grouping and must
    justify it. Keeps the claim; costs a prompt change.
  - (c) Keep both and record agreement/disagreement as a confidence signal.
    Most honest; most work.
- **Recommended:** (b) — the demo sentence is "Bob understood that three
  symptoms were one problem", and (b) is the only option under which that is
  literally true.
- **Consequences:** whichever is chosen, `IncidentRecord` should record which
  correlation is authoritative.

## ADR-008 — Bob is invoked over the cloud REST API, not a subprocess

- **Status:** ACCEPTED (commit `26aa0b8`), endpoint **NEEDS VERIFICATION**
- **Context:** `agent/bob.py`'s docstring records the investigation: IBM Bob
  v1.126.0 (`bobide`, Antigravity IDE) has no headless stdout mode —
  `bobide.cmd chat` opens the GUI and returns exit 0 with no output, and
  `bobide-tunnel agent host` requires the IDE running as supervisor.
- **Chosen:** the RemoteAgent REST endpoint. `_build_argv()` returns `[]`
  deliberately, to document that no subprocess path exists.
- **Open question:** the base is `https://cloud.manufact.com`. Nothing in the
  repository establishes this as the sanctioned IBM Bob API for the contest.
  **Verify before writing more integration code** — `G-B2`.

## ADR-009 — Bob unavailability is never converted into an analysis

- **Status:** ACCEPTED
- **Evidence:** every failure path — no key, no agent id, 401, any HTTP error,
  timeout, unparseable output, schema violation — returns
  `analysis_source: "unavailable"`. The incident then stops before a plan.
  Four tests cover this.
- **Consequences:** a demo without credentials shows the outage path, not a
  fake success. That is correct, and it is also why `BOB-001` is P0.

## ADR-010 — Branch `shivraj/mcp-repo-ci` is based on `ramana`, not `main`

- **Status:** ACCEPTED
- **Date:** 2026-08-29, commit `1448908`
- **Context:** `main` is `95adfc6` — `LICENSE` plus a one-line README.
  `ramana` carries the consolidated architecture.
- **Chosen:** branch from `ramana`.
- **Reason:** basing on `main` would have meant merging backwards into finished
  work.
- **Consequences:** `ramana` must merge to `main` before any normal PR flow.
  Until then `main` is not the trunk. Two defects were introduced by that
  import commit — a tracked `data/kubemedic.db` and developer-local absolute
  paths in `scripts/validate.sh` — tracked as `REPO-001` and `REPO-004`.

## ADR-011 — Ticket granularity for the correlation demo

- **Status:** **PROPOSED**
- **Context:** the watcher emits one ticket per anomaly burst, so a real run
  produces one ticket. Correlating one ticket demonstrates nothing — which is
  why `dashboard/app.py` fabricates three across services that are not
  deployed.
- **Options:** (a) deploy `payment-service` and `frontend-gateway` for a real
  cascade; (b) one ticket per anomaly signal on the single deployment;
  (c) seed tickets through a clearly-labelled fixture.
- **Recommended:** (b), with (c) as the presenter's fallback if the cluster
  misbehaves during recording. (a) is the best story and does not fit the time.
- **Consequences:** `TICKET-001`.

## ADR-012 — Project name

- **Status:** **PROPOSED — open**
- **Context:** "KubeMedic" in `AGENTS.md`, `.bob/`, `agent/`, tests, and the
  repository name; "OpsPilot" in `orchestrator/`, the `opspilot` namespace,
  `dashboard/`, and `scripts/`.
- **Recommended:** KubeMedic — it matches the repository, the Bob asset pack,
  and the code that is actually being submitted. Retain the `opspilot`
  namespace to avoid touching every manifest and script under deadline, and
  note the discrepancy in the README.
- **Consequences:** `NAME-001`, `NAME-002`.
