# How IBM Bob Was Utilised

> **DRAFT — pending Ramana's review, and one open decision.** Section 4 has two
> variants: keep the one that matches whether `BOB-001` (a live IBM Bob
> analysis) succeeded, and delete the other. Do not soften Variant B if that is
> the one that applies.

---

## 1. IBM Bob is the reasoning layer, and it is the only one

KubeMedic has exactly one module that calls a model: `agent/bob.py`. Nothing
else in the codebase talks to a model provider. That is a deliberate
architectural boundary, and it is why "what does IBM Bob do here" has a
one-file answer.

The system's division of labour is stated in `AGENTS.md`, the standing
instruction file Bob loads in every session, and enforced in code:

- **MCP** answers *what is happening.* It returns evidence. It never decides a
  cause, and it has no tool that can change the cluster.
- **IBM Bob** answers *what this evidence means* — correlation, likely cause,
  proposed remediation, and the reasoning a human needs to judge it.
- **The executor** answers *is this exact action permitted.*
- **The human** answers *should this happen at all.*
- **The verifier** answers *did it actually work.*

Bob occupies the position in that chain that actually requires judgement.
Everything around it is deterministic on purpose, so that Bob's contribution is
legible rather than diffused through the system.

## 2. What Bob is asked, and what it must return

Bob receives the correlated evidence — pod states, events, rollout history,
application health — and the open tickets, and is told explicitly to treat that
as the complete set of observed facts and assume nothing beyond it.

It returns one JSON object matching
`.bob/skills/incident-correlation/references/evidence-schema.md`:

- **Ranked hypotheses**, each with a confidence level, the reason for that
  confidence, and the specific evidence supporting *and contradicting* it
- **A root cause**, explicitly flagged as an inference rather than a fact
- **A timeline** of what happened when
- **One recommended action** from a closed allowlist of three:
  `rollback_deployment`, `restart_deployment`, `scale_workload` — with
  permission to recommend nothing and say what a human should do instead

The prompt names the allowlist literally. Anything outside it is rejected
before parsing, by a check that runs ahead of schema validation. A test asserts
that a `kubectl delete ...` string offered as an action is refused.

**Contradicting evidence is a required field.** A reasoner that only reports
what supports its conclusion is not helping a human decide.

## 3. Bob as the development environment, not only the runtime

`.bob/` in the repository root is an asset pack we authored for this project,
and it is reviewable evidence of how Bob was used to build the system:

- **`AGENTS.md`** — standing instructions Bob loads in every session, including
  the four rules that override everything else: never fabricate evidence;
  separate fact from inference from recommendation; never claim success without
  evidence; never execute anything a model composed.
- **Custom modes** — `kubemedic-analyst` for incident reasoning,
  `kubemedic-dev` for building, `kubemedic-auditor` for adversarial review.
- **Seven skills** — `incident-correlation`, `remediation-planning`,
  `verification-review`, `runbook-bad-rollout`, `track-consolidation`,
  `submission-audit`, `gemini-audit`.
- **Six investigator personas** — pod state, events, change history, health,
  tickets, and a provider auditor.
- **`mcp.json`** — the tool surface Bob is given, deliberately read-only.

Bob in `kubemedic-dev` mode was used to consolidate two competing
implementations into the submitted architecture. Bob in `kubemedic-auditor`
mode was used adversarially against our own work — sweeping for leftover
provider references, for secrets, and for claims in documentation not backed by
code. Several findings in `docs/20_KNOWN_GAPS.md` came out of that.

## 4. Honesty about the runtime path

> **Ramana: keep ONE of the following. Delete the other.**

---

### Variant A — `BOB-001` succeeded

We ran the full loop against a live Kubernetes cluster with IBM Bob connected.
IBM Bob received the correlated evidence and returned ranked hypotheses, a root
cause, and a recommended action from the allowlist. A human reviewer rejected
the first plan with a written reason; that reason was added to the incident
context and sent back to Bob, which produced a revised plan answering the
objection; the reviewer approved it; the action executed; and recovery was
verified independently on two signals.

The audit record for that run is included at
`submission/evidence/INC-<id>.json`. Its `analysis_source` field reads
`ibm-bob`, and the full analysis Bob returned is embedded in the record.

---

### Variant B — `BOB-001` did not succeed

**IBM Bob's runtime reasoning path is implemented and tested, but we were not
able to complete a live model call before the deadline.** We are stating that
plainly rather than implying otherwise.

What is true:

- `agent/bob.py` implements the full invocation against the IBM Bob cloud
  RemoteAgent REST API, including response parsing that tolerates fenced,
  enveloped or prose-wrapped output.
- The response contract is enforced: `BobAnalysis` validates the schema and
  rejects any action outside the allowlist before parsing.
- The failure policy is tested and observed working. Every failure mode — no
  credentials, authentication failure, timeout, unparseable output, schema
  violation — produces `analysis_source: "unavailable"`, and the incident stops
  before a plan is built. Four tests cover this, and it is what our live runs
  actually did.
- The rejection-feedback loop is implemented and tested: a reviewer's reason is
  rendered into a `<human_feedback>` block in Bob's prompt, and a revised plan
  is requested, capped at three revisions.

What is not true, and we will not imply it is: **no live IBM Bob analysis was
observed.** In our live cluster runs, the system reported `BOB_UNAVAILABLE`,
produced no diagnosis, and refused to build a plan. To demonstrate the approval
gate, executor and verifier end to end, the validation harness substitutes an
operator-specified rollback — and labels it as operator-specified in both its
output and the audit record.

We think that behaviour is the right one to have built. A system that invents a
diagnosis when its reasoner is unreachable is more dangerous than one that says
nothing, and the fact that ours refuses is tested rather than asserted. But it
means the reasoning layer, which is the part IBM Bob owns, is demonstrated by
its contract and its tests rather than by a live run, and a judge should weigh
it on that basis.

---

## 5. Where to look in the code

| What | Where |
|---|---|
| The only module that calls a model | `agent/bob.py` |
| The prompt, including the feedback block | `agent/bob.py:PROMPT_TEMPLATE`, `FEEDBACK_BLOCK` |
| Response contract | `agent/models.py:BobAnalysis` |
| Allowlist enforced before parsing | `agent/models.py:BobAnalysis.from_raw` |
| The bridge, and the no-fabrication rule | `agent/reasoning.py` |
| Feedback into reasoning | `agent/pipeline.py:request_revision` |
| Bob's tool surface, read-only | `.bob/mcp.json`, `mcp_server/server.py` |
| Standing instructions | `AGENTS.md` |
| Modes, skills, personas | `.bob/` |
| Session export | `submission/bob-report/` |
