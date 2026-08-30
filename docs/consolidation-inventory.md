# Consolidation Inventory — KubeMedic
**Branch:** ramana  
**Date:** 2026-08-29  
**Author:** Ramana (orchestration and IBM Bob integration)

---

## Executive context

The Phase 4 consolidation inventory was run against the repository as it
exists at the time of this commit. The repository is in a **greenfield state**:
only `LICENSE` and a one-line `README.md` (`# Kubemedic`) were committed to
`main` before this branch. The directories referenced by the SETUP.md and the
master implementation prompt — `agent/` (except `bob.py`), `orchestrator/`,
`dashboard/`, `mcp_server/`, `k8s/`, `scripts/`, `records/`, `data/` — **do
not yet exist in this repository**.

The "two competing architectures (Track 1 orchestrator vs Track 2 agent)"
described in the task instructions are an expected future state, not the
current state. They will be populated as teammates and Ramana implement their
respective modules.

This document therefore serves a dual purpose:

1. **Immediate record** — what exists today and what must be built.
2. **Forward rollback map** — once modules are added, re-run this inventory
   against the actual code before doing any consolidation work.

---

## Part 1 — Module inventory of orchestrator/

`orchestrator/` does not exist in this repository. When it is created (either
ported from the referenced OpsPilot archive or built fresh), the following
classification table must be filled in before any code moves.

### Template (fill per module when orchestrator/ is populated)

| Module | What it does | agent/ equivalent? | Better impl | Tests? | Demo path? | Classification |
|---|---|---|---|---|---|---|
| `orchestrator/models.py` | Pydantic models shared across pipeline | TBD | TBD | TBD | TBD | TBD |
| `orchestrator/correlation.py` | Groups tickets into one incident | TBD | TBD | TBD | TBD | TBD |
| `orchestrator/planning.py` | Produces remediation plan from correlation | TBD | TBD | TBD | TBD | TBD |
| `orchestrator/executor.py` | Executes allowlisted action after approval | TBD | TBD | TBD | TBD | TBD |
| `orchestrator/verification.py` | Re-reads cluster after action, two-signal | TBD | TBD | TBD | TBD | TBD |
| `orchestrator/audit.py` | Writes structured incident record | TBD | TBD | TBD | TBD | TBD |
| `orchestrator/__main__.py` | Entry point / pipeline orchestration | TBD | TBD | TBD | TBD | TBD |

### Classification legend

- **PORT** — legacy implementation is better or only one. Move it to agent/.
- **KEEP** — Track 2 (agent/) already has the better version; legacy is redundant.
- **MERGE** — each has something worth keeping; take the better half of each.
- **DROP** — dead or superseded in both tracks; document and discard.

### Dependency-ordered port sequence (template)

When orchestrator/ is populated, port in this order (leaves first):

1. `models` — no imports from other orchestrator modules; port first.
2. `correlation` — depends on models only.
3. `planning` — depends on models and correlation output.
4. `executor` — depends on models and planning output.
5. `verification` — depends on models and executor output.
6. `audit` — depends on all of the above.
7. `__main__` / entry point — depends on everything; port last.

**Critical path to first working end-to-end run:** models → correlation →
executor → verification. Planning and audit are required for the full loop
but can be stubbed briefly while the core chain is proven.

---

## Part 2 — Module inventory of agent/

`agent/` currently contains only:

| File | What it does | Status |
|---|---|---|
| `agent/bob.py` | IBM Bob headless invocation adapter; returns `BobResult` with structured analysis or `bob_unavailable` | Installed by this PR; syntax-clean, not yet wired to other modules |

The following modules are **expected but do not yet exist**:

| Expected module | Role in architecture |
|---|---|
| `agent/reasoning.py` | Parses Bob's JSON analysis; maps to `BobAnalysis` Pydantic model |
| `agent/correlation.py` | Groups evidence into `IncidentRecord`; may be ported from orchestrator |
| `agent/planning.py` | Produces `RemediationPlan` from `BobAnalysis` |
| `agent/executor.py` | Executes `AllowedAction` after `HumanDecision(approved)`; raises on missing approval |
| `agent/verification.py` | Re-reads cluster after action; requires two independent signals (rollout + health) |
| `agent/audit.py` | Persists structured `IncidentRecord` to `records/` |
| `agent/__init__.py` | Package marker |

---

## Part 3 — Gemini / Google provider audit

Sweep command used:

```
grep -rniE "gemini|google-genai|google.generative|genai|GOOGLE_API_KEY|GEMINI_API_KEY"
(excluding .git, docs/, node_modules, __pycache__)
```

### Findings (committed code only, as of this branch)

| # | File | Line | Matched text | Bucket | Reason |
|---|---|---|---|---|---|
| 1 | `.bob/skills/gemini-audit/SKILL.md` | 2,4,6,11,14,22,25,31,39,43,49 | `gemini`, `GOOGLE_API_KEY`, `google.generativeai` | **MINOR** | Audit skill referencing the thing it searches for; not a code reference |
| 2 | `.bob/agents/gemini-auditor.md` | 2,13,14 | `gemini-auditor`, `GOOGLE_API_KEY`, `GEMINI_API_KEY` | **MINOR** | Persona definition for the auditor; not a code reference |
| 3 | `.bob/custom_modes.yaml` | 94,170,173,188 | `Gemini` | **MINOR** | Mode descriptions referencing the provider audit task; not a code reference |
| 4 | `.bob/rules-kubemedic-auditor/01-audit-conduct.md` | 13 | `Gemini` | **MINOR** | Example finding in rules file; not a code reference |
| 5 | `.bob/README.md` | 52 | `gemini-audit` | **MINOR** | Skill name in a table row; not a code reference |

**No Python files, requirements files, environment files, CI workflows, or
dashboard templates** contain any Google/Gemini reference in the current
committed tree.

### Classification

| Bucket | Count | Notes |
|---|---|---|
| BLOCKER | 0 | No Gemini on the reasoning path; no Google credential required |
| MAJOR | 0 | No user-visible UI labels, README claims, or architecture docs claim Gemini |
| MINOR | 5 | All inside the Bob asset pack's audit tooling — the auditor persona is *named* after what it hunts |
| HISTORICAL | 0 | No prior Gemini commits exist in this repo (single initial commit) |

### Answer to the fresh-clone question

**No.**

A fresh clone following only the README today cannot execute the demonstrated
reasoning flow at all — because the repository is in a greenfield state and
no reasoning flow has been implemented yet. The README is a one-line stub.
No Google credential is required or referenced, but no IBM Bob integration
is wired up either (beyond `agent/bob.py` which is now installed).

What stands in the way of a working demo:

1. `agent/reasoning.py` — does not exist; parses Bob's JSON output.
2. `agent/executor.py` — does not exist; performs the approved action.
3. `agent/verification.py` — does not exist; re-reads cluster after action.
4. `mcp_server/` — does not exist; Shivraj owns this.
5. `dashboard/` — does not exist; Verona owns this.
6. A working README with setup instructions — the current README is `# Kubemedic`.

Once (1)–(3) are implemented and (4)–(5) are built by teammates, the answer
will become: **yes — no Google credential required, IBM Bob is the reasoning
layer**.

---

## Part 4 — Handoffs to teammates

See `docs/handoffs.md` for the full numbered list. Summary:

| # | Owner | Severity | Description |
|---|---|---|---|
| 1 | Shivraj | **BLOCKING** | `mcp_server/` must implement `--profile evidence` flag exposing only read-only tools |

---

## Part 5 — Repository state snapshot

```
Committed to main (before this branch):
  LICENSE
  README.md   (one-line stub: "# Kubemedic")

Added in this branch (ramana):
  .bob/                   Full Bob asset pack (modes, skills, agents, rules, MCP config)
  AGENTS.md               Standing instructions for all Bob sessions
  agent/bob.py            IBM Bob headless invocation adapter
  .env.example            Placeholder environment variables (no real credentials)
  .gitignore              Excludes .venv/, __pycache__/, *.pyc, .env, kubeconfig
  docs/                   Pack source files (untracked reference material; stays)
  docs/consolidation-inventory.md   (this file)
  docs/handoffs.md        Cross-owner change requests

Not yet in repo (to be created):
  agent/reasoning.py      agent/correlation.py    agent/planning.py
  agent/executor.py       agent/verification.py   agent/audit.py
  mcp_server/             (Shivraj)
  dashboard/              (Verona)
  k8s/                    (Shivraj)
  scripts/                (Shivraj)
  records/                (runtime output)
  orchestrator/           (may arrive from OpsPilot archive)
  tests/                  (Ramana, once modules exist)
  archive/                (destination for orchestrator once ported)
```

---

## Instructions for the next engineer reading this

1. **Before porting anything:** run `git log --oneline` and confirm
   `orchestrator/` has been committed. If it has not, there is nothing to port.
2. **Before consolidating:** re-run the Gemini sweep (`gemini-audit` skill)
   and update Part 3 of this document.
3. **One module per commit, tests after each.** The `track-consolidation`
   skill has the full procedure.
4. **Never import from `archive/`** once the port is complete. Verify with:
   `grep -r "archive" agent/ tests/`
