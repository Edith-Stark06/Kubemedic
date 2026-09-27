# How IBM Bob Was Used

## Bob as the reasoning engine

KubeMedic calls exactly one model boundary, and IBM Bob 2.0 sits behind it.
`agent/providers/ibm_bob.py` drives **Bob Shell 2.0.5** headlessly (`bob run`)
with a fixed argument list, never a shell: a dedicated workspace with a
tool-less `kubemedic-reasoner` mode, every Bob tool group disabled so analysis
is pure reasoning over evidence our own read-only layer collected,
`--max-cost`/`--max-turns` on every call with no retry on timeout (Bob usage is
metered), and the API key passed to the child process's environment only.

Whatever Bob returns is validated: a closed action allowlist, a required
target matching the incident's own workload. Any failure produces "analysis
unavailable" and no plan.

## Document understanding: a real operational runbook

`docs/RUNBOOK_TICKET_BOOKING.md` is a short, real playbook — known failure
classes for this service and which of the three allowed actions the team
prefers for each, and why. `agent/runbook.py` loads it and
`agent/providers/prompt.py` hands it to Bob in its own fenced section,
distinct from cluster evidence, with instructions to weigh it, not obey it
blindly.

Run live: Bob's `reason` field read *"The playbook explicitly names this
failure class (Failure Class 1: readiness regression immediately following a
deployment) and mandates rollback_deployment rather than restart_deployment,
because a restart would recreate pods on the same broken image."* That is Bob
citing a real document by name and by its stated rule, not evidence alone —
`submission/evidence/INC-20260926T213503-001.json`.

## What running Bob headlessly taught us

With tools disabled, Bob still tried to call the MCP tools our interactive
`.bob/` rules mention, then **invented the tool responses, including tickets
not in the evidence** — exactly the failure this project exists to prevent.
Fixed in two layers: a dedicated workspace stating the evidence is in the
prompt and nothing else exists, and `agent/reasoning.py` now treats an
analysis citing an unknown ticket as unavailable, with tests. Also found:
Windows' `.cmd` shim truncates multi-line prompts; fixed by launching Bob's
Node entrypoint directly.

## Development environment, audit, and who wrote what

The `.bob/` pack is committed: four modes, seven skills, six investigator
personas, standing rules, a read-only evidence MCP server, asserted by CI. The
hardening in this window was written with Claude Code (Sonnet 5); Bob's real
behaviour, including the fabrication above, drove the fixes. An earlier
headless attempt to have Bob implement one stalled on an edit approval.

We then ran Bob adversarially against our own submission. It found a real
bug — a stale test count — now fixed. Given `--trust` and one narrow
instruction, Bob edited a file directly: the first change here Bob actually
made, not Claude. Small, but real.

## What is shown

`INC-20260926T213503-001.json` and `validate-run-runbook.txt`: a live
Kubernetes cluster (kind), fallback disabled, real tickets, Bob's analysis
citing the runbook, a human rejection, Bob asked again, approval, a real
rollback restoring the full pod template, both recovery signals passing. 34
assertions, 0 failures. Bob's proposal was already correct before and after the
rejection here; `INC-20260926T192815-001.json` (fixture cluster) shows an
objection that does change the recommended action.
