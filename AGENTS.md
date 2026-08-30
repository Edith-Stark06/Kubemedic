# AGENTS.md — KubeMedic

Standing instructions for any Bob session in this repository. Bob loads this
automatically. It applies in every mode.

## What this project is

KubeMedic is a Kubernetes incident-response proof of concept. It gathers
operational evidence through an MCP server, uses IBM Bob to correlate multiple
symptoms into a single incident and reason about the cause, proposes an
impact-aware remediation, **pauses for a human decision**, executes only an
allowlisted action after approval, and independently verifies that the service
actually recovered.

It is not an autonomous healing platform. Do not describe it as one.

## The four rules that override everything else

1. **Never fabricate evidence.** If a tool call failed or returned nothing,
   say so. A diagnosis built on a gap is worse than no diagnosis.

2. **Separate facts from inference from recommendation.** Label them. "Pod
   `ticket-booking-7f4-abc` reports 0/1 Ready" is a fact. "This is likely the
   new revision failing readiness" is an inference. "Roll back to revision 3"
   is a recommendation. Never let one wear the clothes of another.

3. **Never claim success without evidence.** "The rollback command returned
   200" is not recovery. Recovery is the rollout reporting healthy AND the
   application health endpoint returning 200, re-read after the fact.

4. **Never execute arbitrary shell or kubectl that a model composed.** Every
   mutation is a named, allowlisted operation with a validated target,
   performed through the Kubernetes API by `agent/executor.py`, and only after
   the dashboard has recorded an APPROVED human decision.

## Inspect before you modify

This repository already contains working correlation, planning, execution,
verification, audit and test code. Read it before proposing a change. Prefer
consolidating what exists to rewriting it. We are mid-contest; a rewrite that
half-lands is worse than a consolidation that fully lands.

## The AI boundary

- **MCP** answers *what is happening*. It returns evidence. It never decides a
  root cause.
- **IBM Bob** answers *what this evidence means* — correlation, likely cause,
  proposed remediation, and the reasoning a human needs to judge it.
- **The executor** answers *is this exact action permitted*.
- **The human** answers *should this happen at all*.
- **The verifier** answers *did it actually work*.

Do not blur these. If code in one layer starts doing another layer's job, flag
it rather than extending it.

## Vocabulary

Use: Incident · Evidence · Correlation · Root Cause · IBM Bob Analysis ·
Remediation Plan · Human Final Review · Approve · Reject · Rejection Reason ·
Executing · Verification · Verified · Resolved.

Do not use: AI Fix, Auto-Heal, Self-Healing, Magic Repair, autonomous.

## Never commit

Credentials of any kind, `.env`, kubeconfig, API keys, tokens, `.venv/`,
`__pycache__/`, absolute local paths. This includes inside the exported Bob
report in `submission/bob-report/`.
