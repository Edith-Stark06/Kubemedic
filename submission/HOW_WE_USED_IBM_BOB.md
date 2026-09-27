# How IBM Bob Was Used

## Bob as the reasoning engine

KubeMedic calls exactly one model boundary, and IBM Bob 2.0 sits behind it.
`agent/providers/ibm_bob.py` drives **Bob Shell 2.0.5** headlessly (`bob run`),
never a shell: a tool-less `kubemedic-reasoner` workspace, cost/turn caps on
every call (Bob usage is metered), the API key passed to the child process's
environment only. Whatever Bob returns is validated: a closed allowlist, a
required target matching the incident's own workload. Any failure produces
"analysis unavailable" and no plan.

## Document understanding: a real operational runbook

`docs/RUNBOOK_TICKET_BOOKING.md` names failure classes and the preferred
action for each, fenced separately from evidence with instructions to weigh
it, not obey it blindly. Run live, Bob's `reason` field
read: *"The playbook explicitly names this failure class ... and mandates
rollback_deployment rather than restart_deployment, because a restart would
recreate pods on the same broken image."* Bob citing a real document by name
and rule (`INC-20260926T213503-001.json`).

## Two things running Bob taught us — one we fixed, one we didn't

With tools disabled, Bob still tried to call MCP tools our `.bob/` rules
mention, then **invented the responses, including tickets not in the
evidence**. Fixed with a tool-less workspace and a check in
`agent/reasoning.py` treating an analysis citing an unknown ticket as
unavailable, with tests.

We also ran Bob adversarially (`kubemedic-auditor`) against our own safety
code. It found a stale test-count file and three smaller security findings —
fixed, each now tested. It also proposed scoping our audit hash chain per
incident. We tested first: **the proposed fix would have let an attacker
forge one incident's history in isolation** — the opposite of what was asked
for. We kept the design. Verifying a plausible, wrong recommendation before
acting is the discipline this project asks of its own engine.

## watsonx.ai — implemented, contract-tested, not yet live

`agent/providers/watsonx.py` is a second engine behind the same boundary:
`ibm/granite-3-8b-instruct` via watsonx.ai's `text/chat` API, IAM
bearer-token exchange, `temperature=0` for reproducible analyses. One env var
selects it; nothing downstream changes. Specifically: **IAM auth works** —
the key exchanges for a valid token — **but the Watson Machine Learning
instance behind our account is inactive**, so no live watsonx analysis
completed. Provider-parity tests assert it returns the same contract as Bob.

## Who wrote the code, and who made one small edit

The hardening was written with Claude Code (Sonnet 5); Bob's real behaviour
drove the fixes. An earlier headless attempt to have Bob implement one
stalled on an edit approval. Given `--trust` and one narrow instruction, Bob
edited a file directly — the first change here Bob actually made. Small, but
real. The `.bob/` pack is committed: four modes, seven skills, six
investigator personas, a read-only evidence MCP server, asserted by CI.

## What is shown

`INC-20260926T213503-001.json` / `validate-run-runbook.txt`: a live cluster,
real tickets, Bob's analysis citing the runbook, a rejection, Bob asked
again, approval, a real rollback restoring the full pod template, both
signals passing. 34 assertions, 0 failures. `INC-20260926T192815-001.json`
(fixture cluster) shows a rejection that changes the recommended action.
