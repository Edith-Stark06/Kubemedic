---
name: submission-audit
description: >-
  Scores the repository as a skeptical hackathon judge across the four IBM
  TechXchange criteria and checks the six mandatory deliverables. Activates on
  submission audit, judge review, are we ready to submit, or scoring against
  the rubric.
user-invocable: true
---

# Pre-submission audit

Run this with hours left to act on it, not at the end. Be harsh. The point is
to hear it here rather than from the judges.

## Part 1 — Mandatory deliverables

Six items. Each is present-or-absent, no partial credit. Any missing item is a
BLOCKER regardless of how good the code is.

1. Video demonstrating the solution **and** explaining how IBM Bob was used
2. Written problem statement
3. Written solution statement
4. Written statement on how IBM Bob was utilized
5. Working repository / proof of concept, opening without a login
6. **Exported IBM Bob report** with the tasks and sessions used for the contest

Item 6 is the one teams forget. Confirm the file exists in
`submission/bob-report/`, opens, reads sensibly, and carries no credentials.

All materials must be in English.

## Part 2 — Score the four criteria

Five points each, twenty total. For each: the score a skeptical judge gives
today, the one specific thing costing the most points, and the cheapest change
that would raise it, in minutes.

**Completeness and feasibility.** Does the full chain run — detection,
evidence, correlation, diagnosis, plan, human review, execution, verification,
audit? Does it run twice in a row from a clean state? Stopping at a
recommendation caps this criterion.

**Effectiveness and efficiency.** Is deterministic work done deterministically
and the model used only where reasoning is genuinely needed? Calling an LLM to
learn a pod's phase is a point lost. Is the action set narrow and typed?

**Design and usability.** Can a stranger follow the incident from ticket to
resolution in the dashboard without reading source? Are the current state, the
evidence, the recommendation, the risk, and the verification result all
visible without hunting?

**Creativity and innovation.** Are the three claimed capabilities actually
demonstrated — many-to-one correlation, impact-aware planning, and rejection
with recorded human context? A claim in the README that the demo does not show
scores zero here.

## Part 3 — Claim audit

Read the README and the written statements against the code. Every capability
claimed must be one you can point at a file for. Flag anything aspirational
and move it to a Limitations section. An overclaim a judge disproves in one
click costs more than the feature would have earned.

Particular things to check: does the repo claim production RBAC, multi-cluster,
Prometheus, autonomous healing, or enterprise SSO anywhere? If it does and
that thing is not implemented, that is a MAJOR finding.

## Part 4 — Hygiene

No secrets, no `.venv/`, no `__pycache__/`, no absolute local paths, no
kubeconfig — including inside the Bob export. `.gitignore` present and
effective. Third-party notices present. License present. CI green.

## Output

A table: finding, severity (BLOCKER / MAJOR / MINOR), file, fix, minutes. Then
one paragraph: the single highest-value thing to do with the time remaining.
