# Working Code Repository / Technology Proof of Concept

**Repository:** <https://github.com/Edith-Stark06/Kubemedic>
**Branch:** `main` · **Tag:** `v1.0-submission`
**Tests:** 346 passing · **Live end-to-end:** 29 assertions, 0 failures

---

## What it is

KubeMedic watches a Kubernetes workload. When a deployment goes bad it collects
evidence through an MCP server, correlates several symptoms into one incident,
asks a reasoning engine what happened, proposes an impact-aware remediation,
**pauses for a human decision**, executes only an allowlisted action after
approval, and independently verifies that the service actually recovered.

It is not an autonomous healing platform, and it is careful not to claim to be.

```
tickets ─┐
tickets ─┼─► MCP evidence ─► reasoning ─► root cause ─► remediation plan
tickets ─┘                                                     │
                                                     human final review
                                                     ╱               ╲
                                               approve              reject
                                                  │           (reason required)
                                              execute                 │
                                                  │           feedback → engine
                                           independent                │
                                           verification         revised plan
                                                  │                   │
                                              resolved  ◄──────  review again
                                                  │
                                            audit record
```

---

## Reproducing from a clean checkout

```bash
git clone https://github.com/Edith-Stark06/Kubemedic.git
cd Kubemedic
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest                          # 346 passed
python scripts/dry_run.py --non-interactive
```

The suite needs **no cluster and no credentials** — the Kubernetes API is
mocked and every ticket test uses a temporary database. The dry run needs no
cluster either.

Verified from a clean clone: 140 tracked files, no build artifacts, all
modules import.

## Running it

```bash
python -m agent.api        # console at http://127.0.0.1:8100/ui/
python -m agent.cli status # or drive it from the terminal
```

With a Kubernetes cluster, `bash scripts/validate.sh` reproduces the live
end-to-end evidence.

---

## The four properties, and where each is enforced

The project's claim is discipline, not automation. Each property is enforced in
code and has a test — none is a promise in a README.

| Property | Enforced by | Test |
|---|---|---|
| The reasoning engine has no tool that can change the cluster | No mutation tool registered on the MCP evidence profile | CI asserts it every push |
| Nothing executes without approval | `Incident.require_approval()` | `test_execute_without_approval_raises` |
| A rejected plan can never execute | `_ILLEGAL_TRANSITIONS` — structurally unreachable | `test_rejected_to_executing_is_unreachable` |
| A rejection must state why | Model validator, plus `400 feedback_required` | `test_rejection_without_feedback_is_400` |
| No model-composed commands | Closed `AllowedAction` enum, typed API calls, no shell | `test_action_enum_rejects_kubectl_string` |
| Recovery is never assumed | Two independent signals, re-read after the action | `test_tool_error_inconclusive` |
| An unreachable engine never yields a diagnosis | Every failure → `analysis_source: "unavailable"`, no plan | 4 tests |

---

## Evidence in this submission

Everything in [`evidence/`](evidence/) is output from running the submitted
code. Nothing is hand-written.

| File | Shows |
|---|---|
| `evidence/pytest-run.txt` | 346 tests passing |
| `evidence/validate-run.txt` | 29 assertions, 0 failures, live k3s cluster |
| `evidence/dry-run.txt` | Full lifecycle, no cluster required |
| `evidence/INC-*.json` | Real audit records, including one with `analysis_source: "gemini"` |

### What the live run proves

```
healthy 2/2 → bad image shipped → rollout stalls 2/3
  → watcher files tickets from distinct signals
  → they correlate into ONE incident, 0 excluded
  → execute without approval        REFUSED, cluster asserted unchanged
  → reject without a reason         REFUSED
  → reject with a reason            recorded, cluster still unchanged
  → approve
  → rollback executed through the Kubernetes API
  → verified on TWO independent signals
  → RESOLVED, audit record written
```

### One detail worth reading

In every live run the application health endpoint returned **200 throughout the
incident**, because `maxUnavailable: 0` kept the healthy old pods serving. A
system checking only application health would have missed the failure entirely;
the rollout signal caught it.

That is not a design story — it is what the runs showed, and it is why
verification requires two independent signals rather than trusting one.

---

## Architecture

| Module | Owns |
|---|---|
| `agent/models.py` | Every contract, the allowlist, the state machine |
| `agent/api.py` | HTTP surface; holds incident state across requests |
| `agent/pipeline.py` | Stage sequencing, `request_revision()` |
| `agent/providers/` | Pluggable reasoning engines, one shared failure policy |
| `agent/secrets.py` | Every credential — env, file, k8s Secret, vault |
| `agent/k8s_client.py` | The only module that changes a cluster |
| `agent/verification.py` | Two independent signals |
| `mcp_server/` | Read-only evidence, tickets, incident history |
| `static/`, `dashboard/` | Operator console |

Two rules hold the design up. **MCP is passive** — it answers questions, has no
loop, no state, no plan. And **`agent/` coordinates**, not MCP and not the
model: the pipeline decides what happens next, the model supplies an opinion,
the human supplies the authority.

Full detail: [`docs/23_SYSTEM_WORKFLOW.md`](../docs/23_SYSTEM_WORKFLOW.md).

---

## Known limitations

Stated here rather than left to be discovered.

**No live IBM Bob or watsonx analysis was completed.** watsonx returns
`403 invalid_instance_status_error` — the WML instance is Inactive and could
not be reactivated on this account. The Bob REST base URL is unresolved: a real
Inference-scoped key returns 401 on every path of `cloud.manufact.com`, and
`bob.ibm.com` serves 404 HTML. Both are flagged out of the default provider
order with the reason recorded next to the flag, and restore with one
environment variable. See
[`docs/AI_PROVIDER_SETUP.md`](../docs/AI_PROVIDER_SETUP.md) and
[`HOW_WE_USED_IBM_BOB.md`](HOW_WE_USED_IBM_BOB.md).

**Incidents live in memory.** The API and CLI each hold their own; audit
records on disk are the durable artifact.

**`scripts/dry_run.py` uses a fixture cluster.** Correlation, the approval
gate, the executor allowlist, the verifier and the audit trail are the real
code paths; only the thing being observed and mutated is simulated.
`scripts/validate.sh` is the live proof.

**Correlation is performed twice** — deterministically in Python, and again by
the model — and the two are not reconciled. Open decision, recorded as ADR-007
in [`docs/21_DECISIONS.md`](../docs/21_DECISIONS.md).

**Prior work disclosure.** Early exploratory work on the Kubernetes evidence
layer predates the contest window (files dated 2026-08-25; the contest opened
2026-08-28 10:00 ET). The submitted architecture — agent, MCP contract, human
review loop, API, dashboard and test suite — was built during the contest, and
the git history shows it.
