# `.bob/` — the KubeMedic Bob asset pack

Everything in this directory is committed on purpose. It is not developer
configuration that happened to get checked in — it is part of the submission,
and a judge should be able to read it.

## Layout

```
.bob/
├── custom_modes.yaml              4 modes: 1 runtime, 3 build
├── mcp.json                       evidence MCP only — no mutation tool, by design
├── rules/                         standing rules, every mode
├── rules-kubemedic-analyst/       runtime mode contract
├── rules-kubemedic-dev/           implementation discipline
├── rules-kubemedic-auditor/       audit conduct
├── agents/                        6 subagent personas (5 investigators + 1 auditor)
└── skills/                        7 skills
```

## The safety claim, verifiable in ten seconds

Read `mcp.json`. There is exactly one MCP server registered with Bob, and it
serves read-only evidence tools. No mode in `custom_modes.yaml` has a tool
that can change the cluster.

Mutation happens in `agent/executor.py`, which takes an enum action and a
validated target, and raises unless the incident carries a human `APPROVED`
decision. Bob is never in that path.

This is stronger than "the agent is instructed not to mutate". It is
structural: there is no tool to misuse.

## The two families of mode

**`kubemedic-analyst` is the product.** `agent/bob.py` invokes it headless
with structured evidence and parses back a JSON analysis. It is read-only, can
write only to `records/`, and is restricted to the five investigator personas.

**`kubemedic-architect` / `kubemedic-dev` / `kubemedic-auditor` are how we
built this.** They shape our own sessions with Bob, and they are what the
exported Bob report shows.

## Skills

| Skill | Used by | Purpose |
|---|---|---|
| `incident-correlation` | analyst | The core procedure: gather, correlate N tickets into 1 incident, rank hypotheses |
| `remediation-planning` | analyst | Seven-field impact-aware plan |
| `runbook-bad-rollout` | analyst | Runbook for the demo incident class, with a "when this is wrong" section |
| `verification-review` | analyst / dev | Two-signal independent verification |
| `gemini-audit` | auditor | Provider sweep, findings bucketed by severity |
| `track-consolidation` | architect / dev | Merge the legacy orchestrator without losing logic |
| `submission-audit` | auditor | Rubric scoring and the six mandatory deliverables |
