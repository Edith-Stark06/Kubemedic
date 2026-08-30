# IBM Bob Report

Exported IBM Bob tasks and sessions used to build KubeMedic for the IBM
TechXchange 2026 Pre-conference Dev Day Hackathon.

## Contest window

2026-08-28 10:00 ET to 2026-08-30 10:00 ET. Sessions in this export fall within
that window.

## Note on completeness

IBM Bob v1.126.0 provides no session export function. This directory contains
the complete `.bob/` configuration — the reviewable, committed artifact of how
Bob was configured and used throughout the contest — together with a written
session log below. **No session has been reconstructed or paraphrased from
memory.** Entries describe sessions that occurred; sessions that did not occur
are not listed.

## How IBM Bob was used

### 1. As the project's configured environment

[`.bob/`](../../.bob/) in the repository root is an asset pack authored for
this project. It is concrete, reviewable evidence of how Bob was configured,
independent of any session transcript:

| Asset | Contents |
|---|---|
| Modes (4) | `KubeMedic Analyst`, `KubeMedic Architect`, `KubeMedic Dev`, `KubeMedic Auditor` |
| Skills (7) | `incident-correlation`, `remediation-planning`, `verification-review`, `runbook-bad-rollout`, `track-consolidation`, `submission-audit`, `gemini-audit` |
| Personas (6) | pod-state, events, change-history, health, ticket, and gemini-auditor investigators |
| Rules | [`AGENTS.md`](../../AGENTS.md) loaded in every session, plus per-mode rule files |
| Tool surface | [`.bob/mcp.json`](../../.bob/mcp.json) — read-only by construction: 8 evidence tools, no mutation tool |

[`AGENTS.md`](../../AGENTS.md) is the standing instruction file Bob loads in
every session. Its four rules — never fabricate evidence; separate fact from
inference from recommendation; never claim success without evidence; never
execute anything a model composed — are the same four properties enforced in
code and listed in the top-level README.

### 2. As a development environment

IBM Bob was used for part of the engineering on this project. It was not the
only tool used, and this section says which is which — the rules ask how Bob
was utilised, not for a claim that nothing else was.

**What was done in IBM Bob sessions:**

- **Consolidation (`KubeMedic Dev` / `KubeMedic Architect`).** Merging two
  competing implementations — the Track 1 `orchestrator/` and the Track 2
  `agent/` — into the submitted architecture, guided by the
  `track-consolidation` skill. This produced `agent/models.py`,
  `agent/correlation.py`, `agent/reasoning.py`, `agent/executor.py`,
  `agent/verification.py`, `agent/audit.py` and `agent/pipeline.py`, with the
  62 tests that shipped with them. Commits `86fb36b`, `09c8801`, `26aa0b8`,
  `317c979`, `6af80d4`, `5e1743f`.
- **Provider audit (`KubeMedic Auditor`, `gemini-audit` skill).** Sweeping the
  repository for leftover Gemini / google-genai references. Result: no Google
  SDK anywhere in the tree. Findings recorded in
  `docs/consolidation-inventory.md`.
- **Submission audit (`KubeMedic Auditor`, `submission-audit` skill).** Scoring
  the submission adversarially against the judging criteria before it was
  finalised. This session found stale test counts across six files, two
  documents still carrying DRAFT markers, an unresolved either/or in the Bob
  utilisation statement, a missing `THIRD_PARTY_NOTICES.md`, a `.env.example`
  pointing at a namespace that does not exist, and a limitation in `README.md`
  that was no longer true. All were corrected in the same session, and
  `docs/20_KNOWN_GAPS.md` was rewritten to mark the 18 gaps that had since been
  resolved.

**What was done outside IBM Bob:** the MCP contract work, the live Kubernetes
client, the evidence adapters, the agent HTTP API, the human-review feedback
loop, the branch merges and the integration test suite were built with a
different AI coding assistant in a terminal session. Commits `de4b32d`,
`c570da9`, `d4796a5`, `f9c564b`, `358eecd`, `b53d7ab`, `592d487`, `9ba495e`,
`d3d91a1` and the three merge commits.

We are stating this rather than attributing the whole repository to Bob
sessions. The git history is public and the authorship is checkable, so an
inaccurate claim here would be both wrong and trivially caught — and this
project's central argument is that it does not overstate what it did.

### 3. As the runtime reasoning layer

[`agent/bob.py`](../../agent/bob.py) is the only module in the system that
calls a model. Everything downstream depends on the `BobAnalysis` contract,
never on how Bob is invoked. See [`../HOW_WE_USED_IBM_BOB.md`](../HOW_WE_USED_IBM_BOB.md).

`.bob/mcp.json` registers one MCP server, launched as
`python -m mcp_server.server --profile evidence`. On that profile Bob is given
eight read-only tools and **no tool that can change the cluster** — the
mutating operations live behind the human approval gate in `agent/executor.py`
and are never registered as MCP tools. CI asserts this on every push rather
than trusting the comment.

### 4. As an incident analyst (interactive)

The `KubeMedic Analyst` mode and `incident-correlation` skill are designed to
be used interactively against a live broken cluster. The procedure is:

1. Open this repository as a Bob workspace
2. Run `bash scripts/inject_incident.sh` in a terminal to stall the rollout
3. In Bob (`KubeMedic Analyst` mode), prompt Bob to call the
   `kubemedic-evidence` MCP tools and correlate the evidence
4. Bob's JSON analysis can then be ingested via
   `python scripts/ingest_bob_analysis.py` to run the full approve/execute/verify
   pipeline with `analysis_source: "ibm-bob"`

This session is the highest-value demonstrable Bob use. `SHIVRAJ_DOCS/08_BOB_RUNBOOK.md`
contains the exact prompts. The session had not been completed at submission
time (IBM Bob credentials not provisioned). `submission/HOW_WE_USED_IBM_BOB.md`
states this plainly.

## The `.bob/` directory as evidence

A judge who cannot run the session can read the assets instead:

| File | What it proves |
|---|---|
| `.bob/custom_modes.yaml` | Four real modes, with `roleDefinition`, `customInstructions`, and permission groups. The analyst mode's `groups` list has no mutation tool. |
| `.bob/mcp.json` | Exactly one MCP server, exactly eight read-only tools. A reader can verify in ten seconds that no mutation tool is registered. |
| `.bob/skills/incident-correlation/SKILL.md` | Full correlation procedure: gather evidence, rank hypotheses with contradicting evidence required, propose from a closed allowlist |
| `.bob/skills/incident-correlation/references/evidence-schema.md` | The JSON schema `agent/models.py:BobAnalysis.from_raw` validates against |
| `.bob/skills/submission-audit/SKILL.md` | The rubric checklist Bob ran against this submission |
| `.bob/skills/gemini-audit/SKILL.md` | The sweep Bob used to confirm no Google/Gemini SDK is present |
| `.bob/rules/01-evidence-discipline.md` | Standing rules loaded in every session |
| `AGENTS.md` | The project-level standing instructions |

## Verification

```bash
# Confirm no credentials or local paths in this directory
grep -rniE "api[_-]?key|secret|token|password|C:\\Users" submission/bob-report/
# Expected: no output
```
