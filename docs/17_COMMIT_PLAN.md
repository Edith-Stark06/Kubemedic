# 17 — Commit Plan

Each commit is logically coherent, buildable, testable and reversible. Stage
named files — never `git add .`.

## Sequence

| # | Commit | Task | Files | Test before committing |
|---|---|---|---|---|
| 01 | `chore(repo): untrack the runtime sqlite database` | REPO-001 | `.gitignore`, `git rm --cached data/kubemedic.db` | `git ls-files data/` empty |
| 02 | `chore(repo): declare project and dev dependencies` | REPO-002 | `requirements.txt`, `requirements-dev.txt` | clean venv install, then `pytest -q` |
| 03 | `fix(tickets): import Enum so scalar field updates work` | MCP-005 | `mcp_server/tickets.py`, `tests/test_tickets.py` | `pytest -q tests/test_tickets.py` |
| 04 | `refactor(mcp): move the evidence layer into mcp_server` | MCP-003 | `mcp_server/evidence.py`, `mcp_server/{models,tools,watcher}.py`, delete `orchestrator/` | `python -c "import mcp_server.tools"`; `pytest -q` still 62 |
| 05 | `fix(mcp): align tool names with mcp.json and EvidenceReader` | MCP-001 | `mcp_server/{server,tools}.py`, `tests/test_mcp_contract.py` | new contract test |
| 06 | `feat(mcp): enforce the read-only evidence profile` | MCP-002 | `mcp_server/server.py`, tests | 7 tools listed; mutation refused |
| 07 | `fix(mcp): return JSON rather than Python repr` | MCP-006 | `mcp_server/server.py` | contract test |
| 08 | `feat(agent): adapt MCP evidence and tickets to agent contracts` | MCP-008 | `agent/adapters.py`, `tests/test_adapters.py` | round-trip tests; correlation from adapted tickets |
| 09 | `feat(agent): Kubernetes client for the three allowlisted actions` | EXEC-001 | `agent/k8s_client.py`, tests | mocked API tests |
| 10 | `feat(agent): live dual-signal verification` | VER-001 | `agent/k8s_client.py` or `agent/adapters.py`, tests | verification against a fake reader |
| 11 | `feat(api): HTTP surface over the incident lifecycle` | API-001 | `agent/api.py`, `tests/test_api.py` | `TestClient` per endpoint |
| 12 | `feat(api): human review gate; rejection requires a reason` | REVIEW-001 | `agent/api.py`, tests | 400 without feedback, 200 with |
| 13 | `feat(agent): human feedback becomes reasoning context` | REVIEW-002 | `agent/{models,bob,reasoning,pipeline}.py`, tests | revised plan differs; feedback in prompt; revision cap |
| 14 | `feat(watcher): one ticket per anomaly signal` | TICKET-001 | `mcp_server/watcher.py`, tests | watcher unit tests |
| 15 | `feat: propagate incident state to member tickets` | TICKET-002 | `agent/api.py`, `mcp_server/tickets.py` | integration test |
| 16 | `refactor(dashboard): render real incidents from the agent API` | DASH-001 | `dashboard/app.py`, `templates/index.html` | `git grep '"passed": approved'` empty; manual run |
| 17 | `feat(dashboard): mandatory rejection reason` | DASH-002 | `dashboard/*` | manual + API test |
| 18 | `fix(dashboard): the reasoning engine is IBM Bob` | DASH-003 | `dashboard/app.py`, `index.html` | `git grep -i gemini dashboard/` empty |
| 19 | `test: end-to-end validation harness` | E2E-001 | `scripts/validate.sh` | `bash scripts/validate.sh` exits 0 |
| 20 | `ci: pull request validation` | CI-001 | `.github/workflows/ci.yml` | green on a PR |
| 21 | `docs: architecture, contracts and runbook` | this set | `docs/*` | links resolve |
| 22 | `docs: submission statements and IBM Bob utilisation` | SUB-001/002 | `submission/` | English, complete |
| 23 | `chore(submission): freeze v1.0-submission` | SUB-005 | tag | secret sweep clean |

## Rules

- One task per commit. If the message needs "and", split it.
- A commit that changes a safety property changes its test in the same commit.
- Run `pytest -q` before every commit. Paste the result in the PR, not from
  memory.
- Never commit `.env`, a kubeconfig, an API key, a `.venv`, `__pycache__`, a
  `.db`, or an absolute local path.
- Reversibility: every commit above can be `git revert`ed alone, except 04
  (a move) and 16 (a rewrite), which should be reverted together with their
  immediate follow-ups if needed.

## Already committed on this branch

| SHA | Message |
|---|---|
| `1448908` | Import the MCP, dashboard, workload and k8s layers |
| `5e1743f` | fix(audit): IncidentRecord stores full Bob analysis + root cause snapshot |
| `6af80d4` | feat(agent): complete lifecycle — executor, verification, audit, pipeline |
| `317c979` | feat(agent): core contracts, correlation, reasoning bridge |
| `26aa0b8` | fix(bob): wire real IBM Bob invocation — REST API path |
| `09c8801` | docs: consolidation inventory and provider audit |
| `86fb36b` | feat(bob): install KubeMedic Bob asset pack |

`1448908` carries two known defects introduced by the import, both fixed by
commits 01 and 19 above: `data/kubemedic.db` was tracked, and
`scripts/validate.sh` contains developer-local absolute paths.
