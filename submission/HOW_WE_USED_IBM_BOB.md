# How IBM Bob Was Used

## Bob as the reasoning engine

KubeMedic calls exactly one model boundary, and IBM Bob 2.0 sits behind it.
`agent/providers/ibm_bob.py` drives **Bob Shell 2.0.5** headlessly (`bob run`),
never a shell: a dedicated tool-less `kubemedic-reasoner` workspace so
analysis is pure reasoning over evidence our own read-only layer collected,
cost/turn caps on every call (Bob usage is metered), the API key passed to the
child process's environment only. Whatever Bob returns is validated: a closed
action allowlist, a required target matching the incident's own workload. Any
failure produces "analysis unavailable" and no plan.

## Document understanding: a real operational runbook

`docs/RUNBOOK_TICKET_BOOKING.md` names known failure classes and which of the
three allowed actions the team prefers for each, and why, fenced separately
from cluster evidence with instructions to weigh it, not obey it blindly. Run
live, Bob's `reason` field read: *"The playbook explicitly names this failure
class ... and mandates rollback_deployment rather than restart_deployment,
because a restart would recreate pods on the same broken image."* Bob citing
a real document by name and rule — `INC-20260926T213503-001.json`.

## Two things running Bob taught us — one we fixed, one we didn't

With tools disabled, Bob still tried to call MCP tools our `.bob/` rules
mention, then **invented the responses, including tickets not in the
evidence** — the exact failure this project exists to prevent. Fixed with a
dedicated tool-less workspace and a check in `agent/reasoning.py` that treats
an analysis citing an unknown ticket as unavailable, with tests.

Later, we ran Bob adversarially (`kubemedic-auditor`) against our own safety
code and our own submission docs. It found a stale test-count evidence file
and three small real security findings — all fixed, each now tested. It also
proposed scoping our audit hash chain per incident rather than sharing one
chain across all incidents. We wrote a test before touching anything: **the
proposed fix would have let an attacker forge one incident's history in
isolation** — the opposite of what was asked for. We kept the design.
Verifying a plausible, wrong recommendation before acting on it is the same
discipline this project asks of its own reasoning engine.

## Who wrote the code, and who made one small edit

The hardening was written with Claude Code (Sonnet 5); Bob's real behaviour
drove the fixes. An earlier headless attempt to have Bob implement one stalled
on an edit approval. Given `--trust` and one narrow instruction this time, Bob
edited a file directly — the first change here Bob actually made. Small, but
real. The `.bob/` pack is committed: four modes, seven skills, six
investigator personas, standing rules, a read-only evidence MCP server,
asserted by CI.

## What is shown

`INC-20260926T213503-001.json` / `validate-run-runbook.txt`: a live cluster,
fallback disabled, real tickets, Bob's analysis citing the runbook, a
rejection, Bob asked again, approval, a real rollback restoring the full pod
template, both recovery signals passing. 34 assertions, 0 failures. Bob's
proposal was already correct before and after the rejection here;
`INC-20260926T192815-001.json` (fixture cluster) shows an objection that does
change the recommended action.
