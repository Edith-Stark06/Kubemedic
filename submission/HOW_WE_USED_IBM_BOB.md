# How IBM Bob Was Used

## Bob as the reasoning engine

KubeMedic calls exactly one model boundary, and IBM Bob 2.0 sits behind it. The
provider (`agent/providers/ibm_bob.py`) drives **Bob Shell 2.0.5** headlessly
(`bob run`) with a fixed argument list, never a shell:

- a dedicated workspace containing only a tool-less `kubemedic-reasoner` mode
- every Bob tool group disabled, so analysis is pure reasoning over evidence
  collected by our own read-only layer
- `--max-cost` and `--max-turns` on every call, and no retry on timeout,
  because Bob usage is metered
- the API key passed to the child process through its environment only

Whatever Bob returns is validated before anything else sees it: a closed action
allowlist, a required target, and a check that the target is the incident's own
workload. Failure of any kind produces "analysis unavailable" and no plan.

## What running Bob headlessly taught us

Connected with an Inference-scoped key, we read what Bob actually did. From the
repository root it behaved as a coding agent, reading files. With tools
disabled it still tried to call the MCP tools our interactive `.bob/` rules
mention, then **invented the tool responses, including tickets that were not in
the evidence** — exactly the failure this project exists to prevent.

Fixed in two layers: the application runs Bob in its own workspace whose mode
states the evidence is in the prompt and nothing else exists; and
`agent/reasoning.py` now treats any analysis citing a ticket it was not given as
unavailable, with tests. We also found Windows' `.cmd` shim truncating
multi-line prompts, and now launch Bob's Node entrypoint directly.

## Bob as the development environment

The `.bob/` pack is committed: custom modes, seven skills, six investigator
subagent personas, standing rules, and an evidence MCP server on a read-only
profile, which CI asserts contains no mutation tool.

## Who wrote what, plainly

Bob did not write the code changes made in this window. A headless attempt to
have Bob Shell implement one fix stalled waiting for an edit approval and was
not completed. The hardening (target validation, auth, persistence,
full-template rollback, prompt fencing, deployment manifests) was written with
Claude Code (Sonnet 5) and covered by tests. Bob's role here is the runtime
reasoner, and the tool whose real behaviour drove those fixes.

## What is shown, and what is not

`submission/evidence/INC-20260926T205136-001.json`, with
`submission/evidence/validate-run.txt`, is a full run against a **live
Kubernetes cluster** (kind) with IBM Bob as the reasoning engine, fallback
disabled: the watcher files real tickets from real cluster state, Bob reasons
over that evidence and proposes `rollback_deployment`, a human rejects it and
Bob is asked again, a human approves, the executor performs a real rollback that
restores the full pod template, and both recovery signals pass on a re-read of
the cluster. 34 assertions, 0 failures.

Bob's first proposal was already correct here, so this run doesn't show a
rejection changing the recommendation. An earlier fixture-cluster record,
`INC-20260926T192815-001.json`, does: the objection names an alternative and
Bob's revised plan follows it.
