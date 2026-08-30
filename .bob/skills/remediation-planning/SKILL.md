---
name: remediation-planning
description: >-
  Turns a root-cause conclusion into an impact-aware remediation plan with
  target, blast radius, risk, reversibility, expected effect and a concrete
  verification plan. Activates when proposing a fix, a remediation, a
  rollback, a restart, or a scaling change for a Kubernetes workload.
user-invocable: true
---

# Impact-aware remediation planning

A recommendation without impact is just an opinion. Every plan carries all
seven fields below. If you cannot fill one, say so explicitly rather than
leaving it out — a missing field is what the reviewer will notice.

## The seven fields

**1. Action.** One of `rollback_deployment`, `restart_deployment`,
`scale_workload`. Nothing else exists. If the right fix is outside this set,
return `null` and describe what a human should do by hand.

**2. Target.** The exact resource name, taken from evidence, never invented.
If the deployment name did not appear in a tool result, you do not know it.

**3. Blast radius.** What is affected and for how long. Be concrete:
"deployment/ticket-booking, 3 pods, rolling replacement, roughly 20 seconds of
reduced capacity, no other workload in the namespace references it."

**4. Risk.** Low / Medium / High, **with the sentence that justifies it.**
"Medium" alone tells the reviewer nothing.

**5. Reversibility.** Yes/no plus the actual undo path. "Yes — revision 4
remains in rollout history and can be re-applied with a forward rollout."

**6. Expected effect.** What should be observably different afterwards, stated
as something checkable, not as a hope.

**7. Verification plan.** Numbered, and it must include **at least two
independent signals**. The standard set for this project:

1. Kubernetes rollout reports healthy
2. All required replicas are Ready
3. No pod is running the suspect image
4. Application `/health` returns 200 on a fresh request

## Choosing the smallest sufficient action

Prefer the least invasive action that addresses the identified cause:

- **Rollback** when evidence points at a specific recent revision.
- **Restart** when the workload is in a bad in-memory state with no recent
  change to blame.
- **Scale** when the workload is healthy but saturated.

Do not stack actions. One action, verified, then reassess. Proposing "roll
back and also scale up" hides which one worked.

## Write for the human who has to decide at 2am

The reviewer is going to press Approve or Reject on the strength of your
`reason` and `risk_explanation`. Write those two fields for a tired engineer
who did not read the evidence. Say what you are about to do, why, and what it
costs if you are wrong.

Include `notes_for_reviewer` whenever there is a plausible reason a human
would reject this — a maintenance window, a deliberate rollout, a change that
might be intentional. Anticipating the rejection is what makes the human gate
feel like a real decision rather than a rubber stamp.

## When this skill is wrong

If the root-cause confidence is `low`, do not propose a mutation. Propose the
`cheapest_next_check` from the top hypothesis instead and say the evidence is
not yet sufficient to act on. Acting on a low-confidence diagnosis is how
automated remediation earns its bad reputation.
