# Problem and Solution

## The workflow that costs too much

A bad Kubernetes deployment does not announce itself as one failure. It arrives
as a stalled rollout, pods that never become ready, and a checkout page
returning errors, each filed separately, none naming the cause. Someone then has
to recognise these as one incident, work out what changed, and decide what to
do, at a bad hour, under pressure. That is the slow part of post-deploy
regression triage, and it is where outages get longer.

The usual answer is to let a model fix it. Most teams won't run that on anything
that matters: a model can be confidently wrong, removing the person who would
have caught it, and it cannot prove the fix worked.

## Solution

KubeMedic makes the reasoning fast and the acting boring, bounded and
human-authorised.

1. **Evidence.** A read-only MCP server collects rollout state, pods, events,
   revision history and application health. It never proposes a cause.
2. **Correlation.** Tickets sharing a workload, time window and failure
   signature become one incident.
3. **IBM Bob reasons.** It receives the evidence and returns ranked hypotheses
   with contradicting evidence, a root cause labelled as inference, one action
   from a closed list of three, and an impact assessment: blast radius, risk,
   reversibility, and how recovery will be checked.
4. **A human decides.** Approve, or reject with a mandatory reason. The reason
   goes back to Bob, which revises the plan.
5. **Bounded execution.** Only after approval, one allowlisted action through
   the Kubernetes API. No shell, no model-composed command. A rollback restores
   the whole pod template.
6. **Independent verification.** Recovery means the rollout is healthy *and* the
   application answers 200, re-read after the fact. Never the API's own reply.

## What we enforce, not just claim

- A plan against any workload other than the incident's is refused, twice.
- If Bob is unreachable or answers with something invalid, the incident stops
  with no plan. If it cites tickets it was never given, its analysis is rejected.
- Approver identity comes from an authenticated token, not the request body.
- Incidents and every audit event persist, in a hash chain that reveals edits.
- The deployment grants least-privilege RBAC: `patch` on Deployments, nothing else.

## Evidence

465 tests run without a cluster. A live-cluster run asserts the whole loop: an
unapproved execution is refused with the cluster unchanged, a reasonless
rejection is refused, a real rollback executes, and both recovery signals pass.
During the incident `/health` stays 200 because old pods keep serving; only the
rollout signal catches it. That is why verification needs two signals.

## Honest limits

The project began before this hackathon; this window added the hardening above
and the Bob 2.0 integration. Correlated tickets come from one watcher about one
deployment, so many-to-one is shown on staged input. Prompt injection is reduced,
not eliminated. It handles one workload, one replica.
