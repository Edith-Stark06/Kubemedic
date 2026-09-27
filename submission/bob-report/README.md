# IBM Bob Report

**Project:** KubeMedic — evidence-driven Kubernetes incident response with a human in the loop
**Event:** IBM Bob 2.0 hackathon (Sep 25–27, 2026)

## Correction to an earlier version

An earlier version of this report overstated Bob's role in building the
codebase, attributing implementation work to Bob that was not done by Bob.
This version corrects that: Bob was used for analysis, correlation, and
reasoning tasks, as documented in the sessions below.

## Sessions in this window

Bob Shell 2.0.5 was installed from IBM's official installer (integrity-checked
by the installer against IBM's published SHA-256) and used headlessly with an
Inference-scoped API key.

| # | What ran | Outcome |
|---|---|---|
| 1 | `bob run` connectivity check, agent mode, tools and MCP disabled, cost cap 0.5 | Succeeded. Reply `OK`, session cost 0.025 |
| 2 | Same check in a custom read-only mode | Succeeded. Session cost 0.023 |
| 3 | Headless "implement a fix" task in the repository | Stalled waiting for an edit approval; killed. No change was made by Bob |
| 4 | Full incident-analysis prompt, repository workspace, 10 turns | 13 tool calls; the final message was a file dump, not an analysis. Cost 0.395 |
| 5 | Same prompt, all tool groups disabled | Bob invented MCP tool calls **and their responses, including tickets not in the evidence**. Cost 0.025 |
| 6 | Same prompt in a dedicated tool-less workspace | Skill-activation replies, then a truncated prompt on Windows (a `.cmd` shim cuts multi-line arguments). Fixed by launching Bob's Node entrypoint directly |
| 7 | Dry run with Bob as the engine: initial analysis and a revision after scripted feedback, fallback disabled | Succeeded. Two calls, about 0.010 cost each (Bob Shell logs). Fixture cluster. Recorded in `../evidence/INC-20260926T192815-001.json` |
| 8 | `scripts/validate_incident.py` against a live kind cluster, Bob as the engine | 34 assertions, 0 failures. `analysis_source: "ibm-bob"`. Recorded in `../evidence/INC-20260926T205136-001.json` and `../evidence/validate-run.txt` |
| 9 | Same as 8, plus `docs/RUNBOOK_TICKET_BOOKING.md` handed to Bob as reference material alongside the evidence (`agent/runbook.py`, the "document understanding" feature) | 34 assertions, 0 failures. Bob's `reason` field names the playbook's failure class by number and states its specific rule (rollback, not restart) rather than deriving it from evidence alone. Recorded in `../evidence/INC-20260926T213503-001.json` and `../evidence/validate-run-runbook.txt` |
| 10 | Adversarial audit of this submission's own documents (`kubemedic-auditor` mode, read-only) | Read `AGENTS.md`, `README.md` and every `submission/*.md`. Found a real, undisclosed bug: `evidence/pytest-run.txt` still read "351 passed" after the docs had been updated to claim 465. Fixed in the next commit. Cost 0.425, 18 tool calls |
| 11 | Direct edit, `kubemedic-dev` mode, `--trust`: rewrite this file's own "Correction to an earlier version" section, nothing else | **Succeeded.** Bob edited the file directly -- the first change in this repository actually made by Bob rather than described by it. Diff was exactly the requested section. Task `f61b18304336e3255ee006ede3750199`, cost 0.084, 2 tool calls |

Sessions 4–6 are why the provider uses a dedicated workspace and a tool-less
mode, and why `agent/reasoning.py` rejects an analysis that cites tickets it was
not given. Each has a test. Sessions 7–11 ran with `KUBEMEDIC_BOB_MAX_COST`
between 1.0 and 2.0. Session 11's `--trust` flag is what session 3 was missing
-- session 3 was run without it and stalled on an edit approval that never
resolved headlessly.

## Not yet done

- Session summary screenshots from each team member. Add them here as
  `screenshots/<member>-<session>.png` from real Bob 2.0 sessions. Do not
  reconstruct sessions that did not happen.

## The `.bob/` asset pack

Committed at the repository root, and part of the submission:
`custom_modes.yaml` (four modes), `skills/` (seven), `agents/` (six investigator
personas), `rules/`, and `mcp.json`, which registers one read-only evidence
server. The application's headless mode is separate, in
`agent/providers/bob_workspace/.bob/custom_modes.yaml`.

## Checking this report

```bash
grep -rniE "api[_-]?key *[:=]|secret|token *[:=]|password|Users[/\\]" submission/bob-report/
```

Expected: no output.
