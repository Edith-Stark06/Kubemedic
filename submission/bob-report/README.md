# IBM Bob Report

> **STATUS: NOT YET EXPORTED.** This directory is scaffolded and the export is
> outstanding. It is a **required deliverable** — Official Rules, ENTRY
> REQUIREMENTS, deliverable 4:
>
> > "Working code repository or evidence of technology proof-of-concept
> > solution, **including exported IBM Bob report of all relevant
> > tasks/sessions used for the contest**"
>
> Procedure: `SHIVRAJ_DOCS/02_BOB_REPORT_EXPORT.md`.
> Delete this block once the export is in place.

Exported IBM Bob tasks and sessions used to build KubeMedic for the IBM
TechXchange 2026 Pre-conference Dev Day Hackathon.

## Contest window

2026-08-28 10:00 ET to 2026-08-30 10:00 ET. Sessions in this export fall within
that window.

## How IBM Bob was used

### 1. As the project's configured environment

[`.bob/`](../../.bob/) in the repository root is an asset pack authored for
this project. It is reviewable evidence of how Bob was configured, independent
of any session transcript:

| Asset | Contents |
|---|---|
| Modes | `KubeMedic Analyst`, `KubeMedic Architect`, `KubeMedic Dev`, `KubeMedic Auditor` |
| Skills | `incident-correlation`, `remediation-planning`, `verification-review`, `runbook-bad-rollout`, `track-consolidation`, `submission-audit`, `gemini-audit`, plus Verona's `demo-script`, `demo-workload`, `demo-reset`, `filmable-ui`, `human-review-ui`, `ui-consistency-audit` |
| Personas | pod state, events, change history, health, ticket, and provider auditor investigators |
| Rules | [`AGENTS.md`](../../AGENTS.md) plus per-mode rule files |
| Tool surface | [`.bob/mcp.json`](../../.bob/mcp.json) — read-only by construction |

[`AGENTS.md`](../../AGENTS.md) is the standing instruction file Bob loads in
every session. Its four rules — never fabricate evidence, separate fact from
inference from recommendation, never claim success without evidence, never
execute anything a model composed — are the same four properties enforced in
code and listed in the top-level README.

### 2. As the reasoning layer at runtime

[`agent/bob.py`](../../agent/bob.py) is the only module in the system that
calls a model. Everything downstream depends on the `BobAnalysis` contract,
never on how Bob is invoked. See
[`../HOW_WE_USED_IBM_BOB.md`](../HOW_WE_USED_IBM_BOB.md).

### 3. As the evidence surface

`.bob/mcp.json` registers one MCP server, launched as
`python -m mcp_server.server --profile evidence`. On that profile Bob is given
eight read-only tools and **no tool that can change the cluster** — the
mutating operations live behind the human approval gate in
`agent/executor.py` and are never registered as MCP tools. CI asserts this on
every push rather than trusting the comment.

## Files

| File | Session | Date | Mode |
|---|---|---|---|
| *(to be filled after export)* | | | |

## Note on completeness

*Delete whichever does not apply.*

- All contest sessions are included.
- IBM Bob v1.126.0 provides no session export function. This directory contains
  screenshots of the session history together with the complete `.bob/`
  configuration, which is the reviewable artifact of how Bob was configured and
  used. **No session has been reconstructed or paraphrased from memory.**

## Before committing an export

```bash
grep -rniE "api[_-]?key|secret|token|password|C:\\\\Users" submission/bob-report/
```

`AGENTS.md`: *"Never commit credentials of any kind... This includes inside the
exported Bob report."* A transcript can easily contain a pasted key or an
absolute local path.
