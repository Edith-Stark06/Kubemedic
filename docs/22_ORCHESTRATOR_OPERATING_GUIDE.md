# 22 — Orchestrator Operating Guide

For the technical orchestrator. How to run this project from here.

---

## Iteration workflow

```
1.  git status                       clean tree before starting
2.  read docs/00_PROJECT_STATUS.md   what changed since last time
3.  read docs/16_TASK_BACKLOG.md     pick the top unblocked P0/P1
4.  check its Depends field          do not start blocked work
5.  read the module in docs/03_MODULE_MAP.md before opening the file
6.  implement the smallest coherent change
7.  python -m pytest -q              paste the real output
8.  update docs/13_TEST_MATRIX.md    PASS only if you ran it
9.  update docs/16_TASK_BACKLOG.md   tick the box
10. git add <named files>            never git add .
11. git commit                       type(scope): summary + why + task id
12. update docs/00_PROJECT_STATUS.md if a subsystem changed status
```

Rule: **if you cannot explain a change in the documentation, do not commit it.**
The chain is Requirement → Architecture → Module → Code → Test → Docs → Commit.

---

## Before every merge

- [ ] `python -m pytest -q` — paste the output, do not recall it
- [ ] `python -c "import mcp_server.server"` succeeds
- [ ] `python -c "import dashboard.app"` succeeds
- [ ] `git grep "from orchestrator"` — expected empty after `MCP-003`
- [ ] `git ls-files | grep -E "\.db$|\.env$|\.venv|__pycache__"` — empty
- [ ] `git grep -n "C:/Users\|/c/Users"` — empty
- [ ] No safety property weakened: allowlist enum, illegal transitions,
      `require_approval()`, dual-signal verification
- [ ] Docs updated in the same commit as the behaviour

## Before every demo

- [ ] `bash scripts/reset_healthy.sh`; `kubectl -n opspilot get pods` → 2/2 Ready
- [ ] `.env` has `KUBEMEDIC_BOB_API_KEY` **and** `KUBEMEDIC_BOB_AGENT_ID`
- [ ] One successful Bob call today — check for `analysis_source: "ibm-bob"`
- [ ] MCP server starts
- [ ] Dashboard reaches the API and shows **real** data
- [ ] `git grep -n '"passed": approved'` — **must be empty**
- [ ] `git grep -in gemini dashboard/` — empty
- [ ] Rehearse the reject-with-reason path; confirm the reason is visible
- [ ] `records/` is clean, so the run's record is unambiguous
- [ ] Rehearse once end to end before recording

## Before submission

- [ ] All four deliverables exist (`19_HACKATHON_COMPLIANCE.md`): video,
      problem/solution statements, Bob utilisation statement, repository **plus
      the exported IBM Bob report**
- [ ] Everything in English
- [ ] `ramana` merged to `main`; `main` is demoable
- [ ] Repository visibility matches what the rules require
- [ ] Full-history secret sweep — not just a working-tree grep
- [ ] Bob report contains no credentials and no absolute local paths
- [ ] README lets a stranger clone and run
- [ ] Pre-contest work disclosed honestly
- [ ] **No claim in the video that the code does not support** — especially
      "verified recovery"
- [ ] Tag `v1.0-submission`

## Recovering from a failed integration

1. Stop. Do not layer a second fix on an unknown state.
2. `git status`, `git stash` if dirty.
3. `python -m pytest -q` — is `agent/` still green? That is the floor.
4. If green, the fault is in the new layer. `git diff HEAD~1` and read it.
5. If red, `git revert <sha>` the last commit. Never rewrite pushed history —
   three people share these branches.
6. Re-run the tests. Confirm the floor is back.
7. Write down what happened in `21_DECISIONS.md` if it changed a decision.
8. Only then try again, smaller.

**The floor is `pytest -q` = 62 passed.** If that breaks, fix it before
anything else. It is the only objective evidence in the project.

---

## Troubleshooting table

| Symptom | Look here first | Likely cause |
|---|---|---|
| Bob returns `bob_unavailable` | `agent/bob.py:_rest_analyze` | `KUBEMEDIC_BOB_API_KEY` or `KUBEMEDIC_BOB_AGENT_ID` unset — the message says which |
| Bob 401 | same | Wrong or expired key |
| Bob output rejected | `agent/models.py:BobAnalysis.from_raw` | Action outside the allowlist, or `action_target` missing |
| Analysis parses as unavailable despite a 200 | `agent/bob.py:_extract_json` | Response wrapped or fenced in a shape the parser does not recognise |
| Tickets not correlating | `agent/correlation.py` | `named_workload` or `created_at` missing on `TicketReference` — a ticket then scores at most 1 of 3 and is excluded |
| `NameError: Enum` | `mcp_server/tickets.py:update_ticket` | Missing import — `MCP-005` |
| MCP tool "not found" | `mcp_server/server.py` list vs `.bob/mcp.json` | The three-name mismatch — `MCP-001` |
| Mutation tool visible on the evidence profile | `mcp_server/server.py` | `--profile` is ignored — `MCP-002` |
| `ImportError: orchestrator` | `mcp_server/{models,tools,watcher}.py` | Track 1 dependency — `MCP-003` |
| Dashboard shows data that is not in the cluster | `dashboard/app.py:/api/detect` | It is hardcoded — `DASH-001` |
| Dashboard records list is empty | `dashboard/app.py:RECORDS_DIR` | Reads `agent/records/`; the agent writes `records/` |
| Execution raises "requires APPROVED" | `agent/executor.py:require_approval` | Working as designed — the incident was not approved |
| Verification `INCONCLUSIVE` | `agent/verification.py` | A reader call raised. Not a failure — "could not tell" |
| Verification `FAIL` after a successful rollback | `verify()` signal 1 | `ready` mapping — use `rollout_complete`, not `healthy` |
| `data/kubemedic.db` always dirty | `.gitignore` | It is tracked — `REPO-001` |
| `validate.sh` fails immediately | `scripts/validate.sh:18-19` | Absolute paths to a machine-specific venv — `REPO-004` |
| Pods crash-loop instead of NotReady | `k8s/deployment.yaml` | Liveness should be TCP, not HTTP — check the manifest was applied |
| Namespace not found | `.env.example` says `kubemedic`; everything else says `opspilot` | `NAME-002` |

---

## The seven questions the repository must always answer

| Question | Where the answer lives |
|---|---|
| What is the system doing? | `01_SYSTEM_OVERVIEW.md`, `04_RUNTIME_FLOW.md` |
| Why is each module responsible for its behaviour? | `03_MODULE_MAP.md`, `AGENTS.md` "The AI boundary" |
| What context does each module receive? | `05_CONTEXT_MODEL.md` |
| What does IBM Bob do? | `06_AGENT_REASONING_FLOW.md` |
| What does MCP do? | `07_MCP_CONTRACT.md` |
| What does the human do? | `08_HUMAN_REVIEW.md` |
| What happens after rejection? | `08_HUMAN_REVIEW.md` — **stored today; the loop is `REVIEW-002`** |
| How is remediation controlled? | `10_REMEDIATION_AND_VERIFICATION.md` |
| How do we know it worked? | Same — dual-signal verification |
| How do we test it? | `12_TEST_STRATEGY.md`, `13_TEST_MATRIX.md` |
| How do we reproduce it? | `18_DEMO_RUNBOOK.md` |
| How do we demonstrate it? | Same |
| What remains before submission? | `16_TASK_BACKLOG.md`, `19_HACKATHON_COMPLIANCE.md` |

---

## Standing judgement calls

**When the deadline pressures a shortcut, protect these four:**

1. Never claim a verification that did not run.
2. Never let a rejected plan reach execution.
3. Never fabricate an analysis when Bob is down.
4. Never let a model compose a command.

All four are currently enforced in `agent/` and tested. They are also the
project's entire differentiation. A submission that ships less but keeps these
is stronger than one that ships more and breaks them — and under the rules'
honest-and-good-faith clause, safer.

**When something is unknown, write UNKNOWN / NEEDS VERIFICATION.** There are
three open ones right now: the Bob endpoint's legitimacy (`G-B2`), the exact
submission deadline in local time, and whether pre-contest work needs
disclosure. All three are in `19_HACKATHON_COMPLIANCE.md`.
