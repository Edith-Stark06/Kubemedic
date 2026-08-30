---
name: incident-correlation
description: >-
  Correlates Kubernetes operational evidence and multiple open tickets into a
  single incident with a ranked root-cause analysis. Activates on any mention
  of an incident, outage, degraded deployment, failing pods, stalled rollout,
  tickets about a service being down, or a request to analyze what is wrong
  with a workload. Produces structured JSON analysis only; never executes.
user-invocable: true
---

# Incident correlation and root-cause analysis

This is the procedure the KubeMedic analyst follows. Work through it in order.
Do not skip to step 5.

## Step 0 — Declare what you can see

Call `get_workload_snapshot` first. If it fails, stop and return the
`evidence_unavailable` shape from `references/evidence-schema.md`. Do not
continue on partial evidence without saying which part is missing.

## Step 1 — Gather

Emit a todo list, then gather in parallel. Spawn the five investigator
subagents — they have isolated context windows, so log noise never crowds out
deployment state:

| Persona | Question it answers |
|---|---|
| `pod-state-investigator` | Which pods exist, what phase, ready, restarts, image |
| `events-investigator` | What did the cluster complain about, and when first |
| `health-investigator` | Does the application itself answer, independent of pod state |
| `change-history-investigator` | What changed, which revision, and when relative to the first symptom |
| `ticket-investigator` | What did humans report, in what words, at what times |

Each returns a fixed-field contract. Wait for all five before converging.

## Step 2 — Correlate the tickets (this is the differentiator)

Do not treat N tickets as N incidents. Merge tickets into one incident when
they share **two or more** of:

- the same workload, or a workload downstream of it
- an onset time inside the same window as the first anomalous cluster event
- symptoms that are known consequences of one another (a stalled rollout
  *produces* not-ready pods *produces* intermittent request failures)
- the same change in the rollout history sitting just before all of them

State the merge explicitly and name the tickets you merged and why. If a
ticket does **not** belong, say that too and keep it separate. A correlation
that quietly swallows an unrelated ticket is worse than no correlation.

Output a `correlation` block: `master_incident_id`, `member_tickets`,
`excluded_tickets` with reasons, and `correlation_basis` listing the shared
signals above.

## Step 3 — Establish the timeline

Merge cluster events, rollout revision timestamps, and ticket creation times
into one ordered list. Mark `T+0` as the first anomalous cluster event, not
the first ticket — humans notice late.

## Step 4 — Rank hypotheses

At least two. Each carries:

- `statement` — one sentence, specific, naming the resource
- `confidence` — high / medium / low, **with the reason for that level**
- `supporting_evidence` — array of citations: pod name, event reason plus
  timestamp, revision number, or health status code
- `contradicting_evidence` — array. If genuinely empty, say
  `["none found in available evidence"]`, never omit the field
- `cheapest_next_check` — the single check that would most quickly settle it

Ranking rules, in priority order:

1. A cause corroborated by two or more independent evidence sources outranks
   a single-source one.
2. Direct evidence (a Warning event, a failed probe, an image mismatch)
   outranks inference.
3. Anything contradicted by the timeline is demoted regardless of other
   support.

**Temporal proximity is not proof of causation.** When your ranking leans on a
change happening shortly before a symptom, write that sentence into the
hypothesis and say what would distinguish coincidence from cause.

## Step 5 — Hand off to planning

Load the matching runbook skill for the incident class. For a degraded rollout
after a deployment change, that is `runbook-bad-rollout`. Then follow the
`remediation-planning` skill to produce the plan.

## Step 6 — Stop

You are in a read-only mode with no tool capable of changing the cluster.
State that plainly. Do not offer to execute. Do not ask for permission to
execute. The human decides in the dashboard.

## Step 7 — Output

Return exactly one JSON object matching `references/evidence-schema.md`. No
prose before or after it, no markdown fences. `agent/reasoning.py` parses this
directly.

## When this skill is wrong

If the evidence shows two genuinely independent faults in the same window, do
not force them into one incident to make the correlation story neater. Report
two incidents and say why they are separate. A false merge sends a human to
fix the wrong thing.
