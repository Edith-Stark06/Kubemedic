# Problem and Solution

## Problem statement

A bad Kubernetes deployment does not announce itself as one failure. It arrives
as a scatter of symptoms: a rollout that never completes, pods that never
become ready, a dependent service timing out, a checkout page returning errors.
Each is filed separately, often by different people, and none of them names the
cause.

Someone then has to do three things under time pressure: recognise that the
symptoms are one incident rather than four, work out what changed, and decide
what to do about it. That work is slow, it happens at bad hours, and it is
where outages get longer.

The obvious response is to automate remediation. That response is why most
teams will not run these tools on anything that matters. Handing a language
model the ability to change a production cluster fails on three counts:

1. **It can be wrong confidently.** A model that has not been given the right
   evidence will still produce a fluent, plausible diagnosis.
2. **It removes the person who would have caught the mistake.** Speed is not
   worth much if the fast action is the wrong one.
3. **It cannot prove it worked.** "The rollback command returned 200" is not
   recovery. A tool that reports success without re-checking is worse than no
   tool, because it stops the investigation.

The real problem is not that incident response is unautomated. It is that the
reasoning is slow and the acting is dangerous, and most systems get this exactly
backwards — they automate the acting and leave a human to do the reasoning.

## Solution statement

**KubeMedic inverts that.** It uses IBM Bob to do the reasoning, and it makes
the acting boring, bounded and human-authorised.

An MCP server collects operational evidence from the cluster — rollout state,
pod conditions, events, revision history, application health — and does nothing
else. It has no opinion about causes and, deliberately, no tool that can change
anything.

Deterministic correlation groups the open tickets that share a workload, a time
window and a failure signature into a single incident. IBM Bob receives that
evidence and reasons over it: ranked hypotheses with confidence and the specific
evidence for and against each, a root cause labelled as an inference, and one
recommended action drawn from a fixed allowlist of three.

Then it stops and asks a person.

The reviewer sees the tickets, the evidence, Bob's reasoning and the proposed
action, and either approves it or rejects it. **A rejection must state a
reason** — the API returns `400 feedback_required` otherwise, enforced
server-side rather than by a disabled button. That reason is not filed away.
It is added to the incident's context and sent back to IBM Bob, which produces
a revised plan answering the objection, for a second review. The reviewer's
knowledge becomes part of the system's reasoning instead of being lost.

Only after approval does anything change, and then only one named operation
from the allowlist, through the Kubernetes API, with a validated target. No
shell, no command a model composed.

Recovery is then confirmed independently, on two signals from different
sources: the control plane's view of the rollout, and the application answering
HTTP through the Service. Both must pass. The execution API's own response is
never accepted as proof.

Every incident leaves an audit record: which tickets, what Bob concluded, who
approved or rejected it and why, what executed, and how recovery was verified.
When IBM Bob cannot be reached, the record says so and the incident produces no
plan at all — the system reports the outage rather than inventing a diagnosis.

### What makes it different

Most of this category automates the dangerous half and leaves the hard half to
a human. KubeMedic does the opposite, and enforces the boundary in code rather
than stating it in a README:

| Claim | How it is enforced | Verified by |
|---|---|---|
| Bob cannot change the cluster | No mutation tool is registered on the MCP evidence profile | CI asserts it on every push |
| Nothing executes without approval | `require_approval()` guards the executor | Test, plus a live run showing the refusal and the cluster unchanged |
| A rejected plan can never execute | The state machine refuses the transition | Test — the path is structurally unreachable |
| Rejection requires a reason | Model validator plus `400 feedback_required` | Test, and a live refusal |
| No model-composed commands | Actions are a closed enum of three, dispatched to typed API calls | A test asserts a `kubectl ...` string is rejected as an action |
| Recovery is never assumed | Verification re-reads the cluster on two independent signals | Live run: both signals checked, `PASS` observed |
| No fabricated diagnosis | Every Bob failure yields `analysis_source: "unavailable"` and no plan | Four tests, and observed live |

### Demonstrated, not asserted

A ticket-booking service runs on Kubernetes. A bad image ships — same source,
built with `HEALTHY=false`, so the readiness probe fails and the rollout stalls
while the healthy pods keep serving.

`scripts/validate.sh` runs the whole loop against a live cluster with hard
assertions and exits non-zero on any failure. On our k3s cluster, every check
passes: the failure is injected and observed, tickets are filed and correlated
into one incident, an unapproved execution is refused with the cluster asserted
unchanged, a reasonless rejection is refused, a rejection with a reason is
recorded with the cluster still unchanged, approval executes a real rollback,
and recovery is verified on both signals before the incident resolves.

One detail from that run is worth stating, because it is the argument for the
whole design: **the application health endpoint returned 200 throughout the
incident**, since the old pods kept serving. A system checking only application
health would have missed the failure completely. The rollout signal caught it.
That is why verification requires two independent signals rather than trusting
one.

The project ships 238 tests. Its known limitations are written down in the
README and in `docs/20_KNOWN_GAPS.md` rather than left to be discovered.
