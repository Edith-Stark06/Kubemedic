# IBM Bob Report

**Project:** KubeMedic — evidence-driven Kubernetes incident response with a human in the loop
**Event:** IBM Bob 2.0 hackathon (Sep 25–27, 2026)

## Correction to an earlier version

An earlier version of this file described a six-session log in which Bob
"implemented" the live Kubernetes client, the API and the provider layer. It
also claimed no session was reconstructed from memory. That narrative disagreed
with our own attribution notes and with the account in
`../HOW_WE_USED_IBM_BOB.md`, so it has been removed rather than defended.
What follows is only what can be shown.

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
| 7 | Dry run with Bob as the engine: initial analysis and a revision after scripted feedback, fallback disabled | Succeeded. Two calls, about 0.010 cost each (Bob Shell logs). Recorded in `../evidence/INC-20260926T192815-001.json` |

Sessions 4–6 are why the provider uses a dedicated workspace and a tool-less
mode, and why `agent/reasoning.py` rejects an analysis that cites tickets it was
not given. Each has a test.


Session 7 ran against the fixture cluster, not a live one.

| 8 | `scripts/validate_incident.py` against a live kind cluster, Bob as the engine | 34 assertions, 0 failures. `analysis_source: "ibm-bob"`. Recorded in `../evidence/INC-20260926T205136-001.json` and `../evidence/validate-run.txt` |

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
