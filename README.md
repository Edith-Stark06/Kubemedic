# KubeMedic

**Evidence-driven incident response for Kubernetes, with a human in the loop.**

KubeMedic watches a Kubernetes workload. When a deployment goes bad it collects
evidence through an MCP server, uses IBM Bob to correlate several symptoms into
one incident and reason about the cause, proposes an impact-aware remediation,
**pauses for a human decision**, executes only an allowlisted action after
approval, and independently verifies that the service actually recovered.

It is not an autonomous healing platform, and it is careful not to pretend to
be one.

```
tickets ─┐
tickets ─┼──► MCP evidence ──► IBM Bob ──► root cause ──► remediation plan
tickets ─┘                                                      │
                                                        human final review
                                                        ╱             ╲
                                                  approve            reject
                                                     │            (reason required)
                                                 execute                │
                                                     │          feedback → Bob
                                              independent               │
                                              verification        revised plan
                                                     │                  │
                                                 resolved  ◄────  review again
                                                     │
                                              audit record
```

## The four rules

From `AGENTS.md`, and they are enforced in code, not just stated:

1. **Never fabricate evidence.** If a tool call failed, say so.
2. **Separate fact from inference from recommendation.** Label them.
3. **Never claim success without evidence.** Recovery is the rollout reporting
   healthy *and* the application answering 200, re-read after the fact.
4. **Never execute anything a model composed.** Every mutation is a named,
   allowlisted operation with a validated target, performed through the
   Kubernetes API after a recorded human approval.

Where the code enforces each:

| Rule | Enforced by | Test |
|---|---|---|
| No fabricated analysis | `agent/reasoning.py` — every Bob failure yields `analysis_source: "unavailable"` | `test_reasoning_on_bob_unavailable_does_not_fabricate` |
| No unapproved mutation | `Incident.require_approval()` in `agent/executor.py` | `test_execute_without_approval_raises` |
| A rejected plan can never execute | `_ILLEGAL_TRANSITIONS` in `agent/models.py` | `test_rejected_to_executing_is_unreachable` |
| Rejection requires a reason | `HumanDecision` validator; `400 feedback_required` in `agent/api.py` | `test_rejection_without_feedback_is_400_feedback_required` |
| No shell, ever | `AllowedAction` enum + `_dispatch` in `agent/executor.py` | `test_action_enum_rejects_kubectl_string` |
| Verification is independent | `agent/verification.py` re-reads the cluster on two signals | `test_tool_error_inconclusive` |

## Layout

```
agent/          reasoning, correlation, planning, execution, verification, audit, API
  bob.py            the only module that knows how IBM Bob is invoked
  models.py         every contract; the allowlist and the illegal transitions
  api.py            HTTP surface over the lifecycle
  k8s_client.py     the only module that changes a cluster
  providers/        pluggable reasoning engines, one failure policy
  secrets.py        every credential resolves through here
mcp_server/     the evidence surface Bob is allowed to see
  evidence.py       read-only Kubernetes inspection
  server.py         MCP stdio server; --profile evidence is read-only
k8s/            the ticket-booking demo workload
workload/       the demo app; HEALTHY=false is the incident lever
scripts/        inject, reset, and the end-to-end validation harness
tests/          282 tests
docs/           architecture, contracts, gaps, compliance
```

## Setup

Requires Python 3.12+ and a Kubernetes cluster (developed on k3s via Rancher
Desktop).

```bash
git clone https://github.com/Edith-Stark06/Kubemedic.git
cd Kubemedic
python -m venv .venv && source .venv/Scripts/activate   # Linux/macOS: .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest
```

Expected: `282 passed`. The suite needs no cluster and no credentials — the
Kubernetes API is mocked and every ticket test uses a temporary database.

### Choosing the reasoning engine

The engine is a configuration choice. Everything downstream is unchanged,
because every provider returns the same validated contract.

```bash
KUBEMEDIC_REASONING_PROVIDER=ibm-bob   # default
#                            watsonx   IBM watsonx.ai
#                            anthropic Claude (development / fallback)
#                            manual    an analysis from an interactive Bob session
```

`GET /api/provider` reports which engine is active, whether each is configured,
and per-provider call and failure counters. It never probes the network and
never echoes a credential.

The `manual` provider needs **no credentials at all**: IBM Bob reasons
interactively in the workspace, calling the read-only MCP evidence server
itself, and its JSON is fed to the same pipeline through the same validation.

### Configuration

```bash
cp .env.example .env
```

| Variable | Purpose |
|---|---|
| `KUBEMEDIC_BOB_API_KEY` | IBM Bob cloud API key. **Without it, no analysis is produced.** |
| `KUBEMEDIC_BOB_AGENT_ID` | Bob agent id from the cloud console |
| `KUBEMEDIC_NAMESPACE` | Default `opspilot` |
| `KUBEMEDIC_DEPLOYMENT` | Default `ticket-booking` |

Without Bob credentials the system still runs — it collects evidence,
correlates tickets, and reports `BOB_UNAVAILABLE`. It produces no plan and
nothing can be approved. That is the designed behaviour: it reports the outage
rather than inventing a diagnosis.

## Running the demo

```bash
# 1. Build both images from the same source
cd workload
docker build --build-arg APP_VERSION=1.0 --build-arg HEALTHY=true  -t ticketbooking:1.0 .
docker build --build-arg APP_VERSION=1.1 --build-arg HEALTHY=false -t ticketbooking:1.1 .
cd ..

# 2. Deploy the healthy baseline
kubectl apply -f k8s/namespace.yaml -f k8s/deployment.yaml -f k8s/service.yaml
kubectl -n opspilot rollout status deployment/ticket-booking

# 3. Prove the whole loop, with assertions
bash scripts/validate.sh
```

`validate.sh` resets to healthy, injects a real failure, lets the watcher file
tickets, correlates them into one incident, asserts that an unapproved
execution is refused and leaves the cluster untouched, rejects a plan without a
reason and confirms that is refused, rejects *with* a reason and confirms
nothing executed, approves, executes a real rollback, verifies recovery on two
independent signals, and writes an audit record. Exit code 0 only if every
check passes.

### The failure, and why it is a good one

`k8s/deployment.yaml` is built so the demo failure is clean and reversible:

- `maxUnavailable: 0` keeps the old healthy pods serving, so a bad revision
  shows up as a **stalled rollout**, not an outage.
- Readiness probes `/health`; the bad image bakes `HEALTHY=false`, so `/health`
  returns 503 and new pods never go Ready.
- Liveness is a plain TCP check, so a bad `/health` does **not** crash-loop the
  pod — it stays `Running` but `0/1 Ready`. A clean readiness regression.

A useful consequence: during this incident the application health endpoint
keeps returning **200**, because the old pods are still serving. The health
signal alone would miss the failure; the rollout signal catches it. That is the
argument for verifying on two independent signals rather than trusting one.

## The API

```bash
python -m agent.api        # http://127.0.0.1:8100
```

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/cluster` | Live cluster state, or why it cannot be read |
| `GET` | `/api/tickets` | Real tickets from the store |
| `POST` | `/api/incidents` | Collect evidence, correlate, ask Bob, propose |
| `GET` | `/api/incidents/{id}` | Evidence, hypotheses, root cause, plan, audit log |
| `POST` | `/api/incidents/{id}/review` | Approve, or reject **with a reason** |
| `POST` | `/api/incidents/{id}/revise` | Ask Bob for a plan answering the objection |
| `POST` | `/api/incidents/{id}/execute` | Execute the approved action, then verify |
| `GET` | `/api/incidents/{id}/record` | The audit artifact |

Rejecting without a reason returns `400 feedback_required`. That is not
bureaucracy: the reason is added to the incident context and sent to IBM Bob to
produce the revised plan, so a rejection without one leaves the agent unable to
do anything different.

## The MCP evidence surface

`.bob/mcp.json` starts the server as `python -m mcp_server.server --profile
evidence`. On that profile the tool list is read-only — eight evidence and
ticket-read tools, no writes.

**No tool at any profile can change the cluster.** `rollback_deployment`,
`restart_deployment` and `scale_workload` are not MCP tools at all; they live
in `agent/executor.py` behind the approval gate. CI asserts this rather than
trusting it.

## Known limitations

Stated plainly, because a proof of concept that hides its edges is harder to
evaluate:

- **Incidents live in memory.** The API loses them on restart. Audit records in
  `records/` are the durable artifact.
- **IBM Bob's endpoint needs verification.** `agent/bob.py` posts to the cloud
  RemoteAgent REST API; confirm the base URL against IBM Bob's own
  documentation before relying on it.
- **The dashboard falls back to mock data when the agent is not running.**
  Set `KUBEMEDIC_AGENT_BASE_URL=http://127.0.0.1:8100` to connect the dashboard
  to the live agent. Without it, `MockAdapter` serves fixture data for local
  development. Use `scripts/validate.sh` or the agent API directly to exercise
  the real system without the dashboard.
- **Correlation is deterministic Python**, and Bob is *also* asked to correlate.
  The two results are not yet reconciled — see `docs/21_DECISIONS.md` ADR-007.
- **Single workload scope.** One deployment, one service.

## Documentation

`docs/00_PROJECT_STATUS.md` is the entry point. `docs/02_ARCHITECTURE.md` has
the component diagram, `docs/07_MCP_CONTRACT.md` the tool contract,
`docs/08_HUMAN_REVIEW.md` the approval gate, `docs/20_KNOWN_GAPS.md` an honest
gap analysis, and `docs/22_ORCHESTRATOR_OPERATING_GUIDE.md` the troubleshooting
table.

## License

See `LICENSE`.
