# How IBM Bob Was Utilised

**Project:** KubeMedic — Evidence-driven Kubernetes incident response with a human in the loop
**Contest:** IBM TechXchange 2026 Pre-conference Dev Day Hackathon
**Theme:** Build with purpose using IBM Bob 2.0

---

## 1. IBM Bob is the reasoning layer — the only one

KubeMedic has exactly one module that calls a model: [`agent/providers/`](../agent/providers/).
Nothing else in the codebase talks to any model provider. That is a deliberate
architectural boundary enforced in code, not stated in a README.

The system's division of labour is defined in [`AGENTS.md`](../AGENTS.md), the
standing instruction file Bob loads in every session, and mirrored in the code:

| Layer | Question answered | What it cannot do |
|---|---|---|
| **MCP server** | *What is happening?* Returns cluster evidence | Change the cluster, decide a cause |
| **IBM Bob** | *What does this evidence mean?* Correlation, root cause, plan | Execute anything |
| **Executor** | *Is this exact action permitted?* | Run without approval |
| **Human reviewer** | *Should this happen at all?* | Be bypassed |
| **Verifier** | *Did it actually work?* | Trust the execution response |

Bob occupies the position in that chain that genuinely requires judgement.
Everything around it is deterministic by design, so Bob's contribution is
legible rather than diffused through the system.

---

## 2. IBM Bob as the development environment

Before Bob was the runtime reasoning layer, it was the environment in which the
entire system was built. The `.bob/` directory at the repository root is a
purpose-built asset pack — committed, reviewable, and part of the submission:

### Custom modes (4)

| Mode | Purpose |
|---|---|
| `KubeMedic Analyst` | Runtime incident reasoning — the mode `agent/providers/` targets headlessly. Read-only; can only write to `records/`. |
| `KubeMedic Dev` | Implementation sessions — used to build the agent pipeline, executor, verification, API, and dashboard seam |
| `KubeMedic Architect` | Planning sessions — consolidation of two competing implementations, API design, submission documents |
| `KubeMedic Auditor` | Adversarial review — sweeping for Gemini references, committed secrets, unsupported claims |

### Skills (7)

| Skill | Used for |
|---|---|
| `incident-correlation` | Core procedure: gather evidence, correlate N tickets → 1 incident, rank hypotheses with contradicting evidence required |
| `remediation-planning` | Seven-field impact-aware plan with blast radius, risk, reversibility and verification plan |
| `verification-review` | Two-signal independent recovery confirmation |
| `runbook-bad-rollout` | Operational runbook for the demo incident class |
| `track-consolidation` | Merge the legacy orchestrator without losing working logic |
| `submission-audit` | Score the submission against the four judging criteria |
| `gemini-audit` | Sweep for leftover Google/Gemini provider references |

### Personas (6)
Pod-state, events, change-history, health, ticket, and provider-auditor investigators — subagent personas Bob spawns during correlation.

### Standing rules
[`AGENTS.md`](../AGENTS.md) loads into every session. Its four rules — never fabricate evidence; separate fact from inference from recommendation; never claim success without evidence; never execute anything a model composed — are the same four properties enforced in code and tested in the suite.

### What Bob built in Dev mode
- Consolidated two competing implementations (`orchestrator/` Track 1 and `agent/` Track 2) into the submitted architecture
- Implemented `agent/executor.py`, `agent/verification.py`, `agent/audit.py`, `agent/api.py`
- Built the provider registry (`agent/providers/`) with five pluggable engines and a single validated contract
- Fixed three bugs found during the Verona branch merge (missing `ARG` in Dockerfile, unawaited `httpx` calls, duplicate workload entrypoint)
- Authored the submission documents, demo script, and submission checklist

### What Bob found in Auditor mode
- No Google SDK, no Gemini import, no `GOOGLE_API_KEY` anywhere in the codebase (confirmed by `git grep`)
- No committed credentials or absolute local paths
- Findings from that pass are documented in [`docs/20_KNOWN_GAPS.md`](../docs/20_KNOWN_GAPS.md)

---

## 3. IBM Bob as the runtime reasoning engine

### The architecture

```
MCP evidence server  ──►  IBM Bob (kubemedic-analyst mode)
  get_workload_status           │
  get_pods                      │  ranked hypotheses
  get_events                    │  root cause (labelled inference)
  get_recent_changes            │  one action from allowlist of 3
  get_application_health        ▼
  list_tickets          BobAnalysis (validated contract)
  get_ticket                    │
                                ▼
                        Human review gate
                                │
                        ┌───────┴───────┐
                      APPROVE        REJECT (reason required)
                        │                │
                     Execute         reason → Bob → revised plan
                        │
                 Independent verification
                 (two signals: rollout + health endpoint)
                        │
                   Audit record
```

### What Bob receives

A structured prompt containing:
- Live pod states, readiness, restart counts, images
- Kubernetes events (Warning/Unhealthy, reason, timestamps)
- Rollout revision history with change-cause annotations
- Application `/health` response through the Service proxy
- All open tickets with titles and reported symptoms

Bob is told explicitly: *"treat this as the complete set of observed facts and assume nothing beyond it."*

### What Bob must return

One JSON object validated against [`.bob/skills/incident-correlation/references/evidence-schema.md`](../.bob/skills/incident-correlation/references/evidence-schema.md):

```json
{
  "analysis_source": "ibm-bob",
  "hypotheses": [
    {
      "rank": 1,
      "statement": "...",
      "confidence": "high",
      "confidence_reason": "...",
      "supporting_evidence": ["..."],
      "contradicting_evidence": ["..."],
      "cheapest_next_check": "..."
    }
  ],
  "root_cause": {
    "statement": "...",
    "confidence": "high",
    "is_inference": true
  },
  "recommended_action": "rollback_deployment",
  "action_target": "ticket-booking",
  "requires_human_approval": true
}
```

**`contradicting_evidence` is a required field.** A reasoner that only reports what supports its conclusion is not helping a human decide.

**`is_inference: true` on the root cause is mandatory.** The system separates observed facts from Bob's reasoning, always.

### Safety enforcement on Bob's output

Every response Bob returns is validated through `agent/models.py:BobAnalysis.from_raw` before any other code sees it:

| Check | What happens on failure |
|---|---|
| Action outside the allowlist (`rollback_deployment`, `restart_deployment`, `scale_workload`) | Rejected before schema validation. A test asserts a `kubectl delete ...` string is refused. |
| Missing `action_target` when an action is recommended | Rejected |
| Schema violation | `analysis_source` set to `"unavailable"`, incident stops |
| Any Bob failure (timeout, auth error, unparseable output) | Same: `"unavailable"`, no plan built |

**Bob cannot cause an execution.** Even a perfectly valid Bob analysis only reaches `PENDING_APPROVAL`. A human must explicitly approve before anything touches the cluster.

### The rejection-feedback loop

When a human rejects a plan, they must state why (`400 feedback_required` if they do not — enforced server-side in `agent/api.py`). That reason is:

1. Stored in `feedback_history` on the incident
2. Rendered into a `<human_feedback>` block in Bob's next prompt
3. Bob is asked to produce a revised plan answering the objection
4. The revised plan goes back to human review

This means the reviewer's domain knowledge becomes part of Bob's reasoning context rather than being discarded. The loop is capped at three revisions.

### The provider system

`agent/providers/` makes IBM Bob one of five pluggable engines behind a single contract:

```
KUBEMEDIC_REASONING_PROVIDER=ibm-bob   # IBM Bob cloud REST API (default)
                             watsonx   # IBM watsonx.ai
                             anthropic # Claude (development)
                             manual    # JSON from an interactive Bob session
                             host      # The IDE hosting this workspace
                             auto      # First configured engine wins
```

Every provider returns the same `BobAnalysis` — validated, allowlist-enforced, and stamped with `analysis_source` so an audit record always names what reasoned. The system downstream is unchanged by the choice of engine.

---

## 4. Honesty about the runtime path

**IBM Bob's runtime reasoning path is fully implemented and tested. A live REST API call was not completed before the submission deadline** because the correct REST endpoint for an Inference-scoped key from `bob.ibm.com` could not be confirmed. We are stating that plainly.

What is verifiably true:

- `agent/providers/ibm_bob.py` implements the full REST invocation, including response parsing that tolerates fenced, enveloped or prose-wrapped output
- The response contract is enforced: `BobAnalysis.from_raw` validates the schema and rejects any non-allowlisted action before downstream code runs
- The failure policy is **tested and observed working live**: every failure mode — no credentials, authentication failure, timeout, unparseable output, schema violation — produces `analysis_source: "unavailable"` and stops the incident before a plan is built. The audit record in `submission/evidence/INC-20260830T063901-001.json` shows this behaviour from a real cluster run.
- The rejection-feedback loop is implemented and tested: 343 tests pass, including tests that assert the reason reaches Bob's next prompt
- `scripts/ingest_bob_analysis.py` provides a complete ingestion path: run Bob interactively in the workspace (it launches our MCP evidence server itself, calls the read-only tools against the live cluster), paste the JSON, and the script runs the full approve/execute/verify pipeline with `analysis_source: "ibm-bob"` in the audit record — because Bob genuinely produced the analysis

What is not true and we will not imply it is: **no headless live Bob analysis was observed in this submission.** In our cluster runs the system reported `BOB_UNAVAILABLE`, produced no diagnosis, and refused to build a plan. The validation harness substituted an operator-specified rollback — labelled as such in both its output and the audit record — so the approval gate, executor and verifier could still be exercised end to end.

A system that invents a diagnosis when its reasoner is unreachable is more dangerous than one that says nothing. Ours refuses, and that refusal is tested rather than asserted.

---

## 5. The MCP tool surface — read-only by construction

`.bob/mcp.json` registers exactly one MCP server:

```bash
python -m mcp_server.server --profile evidence
```

On the `evidence` profile, Bob is given **eight read-only tools and no tool that can change the cluster**:

| Tool | What it returns |
|---|---|
| `get_workload_status` | Replica counts, current image, rollout conditions |
| `get_pods` | Phase, readiness, restart count, termination state |
| `get_events` | Recent Warning/Normal events for the deployment and its pods |
| `get_recent_changes` | ReplicaSet revision history with images and change-cause annotations |
| `get_application_health` | `/health` response through the Service proxy |
| `get_workload_snapshot` | All five above in one call |
| `list_tickets` | Open tickets from the store |
| `get_ticket` | One ticket by ID |

`rollback_deployment`, `restart_deployment`, and `scale_workload` are **not MCP tools**. They live in `agent/executor.py` behind the human approval gate and are never registered on any MCP profile. CI asserts this on every push rather than trusting the comment.

---

## 6. Where to look in the code

| What | Where |
|---|---|
| Provider registry and auto-selection | `agent/providers/__init__.py` |
| IBM Bob REST provider | `agent/providers/ibm_bob.py` |
| Host IDE / interactive provider | `agent/providers/host.py` |
| The prompt Bob receives | `agent/providers/prompt.py` |
| Response contract and allowlist enforcement | `agent/models.py:BobAnalysis.from_raw` |
| No-fabrication rule | `agent/reasoning.py` |
| Rejection feedback → Bob's next prompt | `agent/pipeline.py:request_revision` |
| Human review gate (400 if no reason) | `agent/api.py:/api/incidents/{id}/review` |
| Executor (allowlist + approval check) | `agent/executor.py` |
| Independent two-signal verification | `agent/verification.py` |
| Bob's read-only tool surface | `.bob/mcp.json`, `mcp_server/server.py` |
| Standing instructions | `AGENTS.md` |
| Modes, skills, personas | `.bob/` |
| Interactive ingestion path | `scripts/ingest_bob_analysis.py` |
| Session export | `submission/bob-report/` |
