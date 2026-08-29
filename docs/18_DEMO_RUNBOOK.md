# 18 — Demo Runbook

> **Status: this runbook cannot be executed end to end today.** Steps 1-5 work
> against a real cluster. Steps 6 onward describe the target after Phases 3-8
> of `14_INTEGRATION_PLAN.md`. Steps that do not yet work are marked
> **[NOT YET]**. Do not record a demo video against the current dashboard —
> see the warning at the end.

Commands are for Git Bash on Windows. `scripts/*.sh` prepend
`$HOME/.rd/bin` to `PATH`, so they assume **Rancher Desktop**. On another
distribution, drop that line or adjust it.

---

## Prerequisites

```bash
kubectl version --client
kubectl get nodes                 # a reachable cluster
python --version                  # 3.13.9 on the audited machine
```

Environment — copy and fill, never commit:

```bash
cp .env.example .env
```

Required for a real Bob analysis:

```
KUBEMEDIC_BOB_API_KEY=<from the IBM Bob cloud console>
KUBEMEDIC_BOB_AGENT_ID=<agent id>
KUBEMEDIC_BOB_API_BASE=https://cloud.manufact.com
```

Without both the key and the agent id, `agent/bob.py` returns
`bob_unavailable` and the incident stops before a plan. That is correct
behaviour, not a bug — but it means **no demo of the reasoning step**.

> **`.env.example` sets `KUBERNETES_NAMESPACE=kubemedic`, while every manifest,
> script and code default uses `opspilot`.** Use `opspilot`, or fix the example
> first (task `NAME-002`).

---

## 1. Build the two images

```bash
cd workload
docker build --build-arg APP_VERSION=1.0 --build-arg HEALTHY=true  -t ticketbooking:1.0 .
docker build --build-arg APP_VERSION=1.1 --build-arg HEALTHY=false -t ticketbooking:1.1 .
cd ..
```

Same source, two build args. `:1.1` bakes `HEALTHY=false`, so `/health`
returns 503 and the readiness probe fails.

> On Rancher Desktop / kind, the images must be visible to the cluster.
> `imagePullPolicy: IfNotPresent` means a locally built image is used if the
> node can see it. With kind: `kind load docker-image ticketbooking:1.0`.

## 2. Deploy the healthy baseline

```bash
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
kubectl -n opspilot rollout status deployment/ticket-booking --timeout=120s
```

## 3. Confirm health

```bash
kubectl -n opspilot get pods
kubectl -n opspilot port-forward svc/ticket-booking 8080:80 &
curl -s localhost:8080/health     # {"status":"healthy","version":"1.0"}
curl -s localhost:8080/           # seats_total 50, seats_remaining 50
```

Expected: 2/2 pods Ready.

## 4. Start the MCP evidence server

```bash
python -m mcp_server.server --profile evidence
```

**[PARTIAL]** The server starts and serves ten tools. The `--profile` flag is
accepted and **ignored** — no argparse exists (task `MCP-002`). Two ticket
mutation tools are exposed on a profile documented as read-only.

Importing this module also creates `data/kubemedic.db` as a side effect.

## 5. Inject the failure

```bash
bash scripts/inject_incident.sh
kubectl -n opspilot get pods -w
```

What happens, and why it is a good demo failure:

- `kubectl set image` ships `ticketbooking:1.1`.
- New pods start, `/health` returns 503, the readiness probe fails.
- Liveness is a plain TCP check, so the pods do **not** crash-loop. They sit
  `Running` but `0/1 Ready`.
- `maxUnavailable: 0` keeps the two healthy old pods serving, so the rollout
  **stalls** instead of causing an outage.

Result: a stuck rollout with a clean, fully reversible cause.

## 6. Tickets appear **[PARTIAL]**

`mcp_server/watcher.py` polls every 15s and opens a ticket. Today it creates
**exactly one** ticket per burst, with every anomaly joined into the title,
then suppresses duplicates. Task `TICKET-001` changes this to one ticket per
distinct signal so correlation has real input.

```bash
python -c "from mcp_server import tickets; [print(t.id, t.status, t.title) for t in tickets.list_tickets()]"
```

## 7. Evidence collection **[NOT YET wired to the agent]**

MCP returns real evidence today, but nothing converts it into
`agent.models.EvidenceSnapshot`. Task `MCP-008`.

## 8. Bob reasons **[NOT YET observed]**

`agent/bob.py` posts the evidence and open tickets to the Bob REST API and
parses one JSON object matching
`.bob/skills/incident-correlation/references/evidence-schema.md`: hypotheses
with confidence and supporting/contradicting evidence, a root cause, a
timeline, and one allowlisted `recommended_action`.

**No successful live response has ever been observed.** Task `BOB-001`.

## 9. The human sees the plan **[NOT YET]**

Target: the dashboard shows tickets, the correlation that grouped them,
the evidence, Bob's hypotheses ranked with confidence, the root cause, and the
proposed remediation with its blast radius and risk.

Today the dashboard shows hardcoded data — three fabricated tickets across
`ticket-booking`, `payment-service` and `frontend-gateway`, two of which are
not deployed by `k8s/`.

## 10. Reject **[NOT YET]**

Target: clicking Reject opens a dialog that **requires** a reason. The reason
is `POST`ed as `feedback`, stored on the incident and in the audit record, and
added to the next Bob prompt, producing a revised plan for a second review.

Today: `POST /api/reject` has no `feedback` field at all, and no re-analysis
loop exists. Tasks `REVIEW-001`, `REVIEW-002`, `DASH-002`.

**Where feedback would be stored, once implemented:** on the incident
(`human_decision.feedback`), in `audit_log` as a `rejection_recorded` entry,
and in `records/<id>.json` as `rejection_feedback`. The model and record
support this today — it is the transport and the loop that are missing.

## 11. Approve and execute **[NOT YET]**

`agent/executor.py` checks `require_approval()`, then dispatches one
allowlisted action through a `KubernetesClient`. **No such client exists**
(task `EXEC-001`). Nothing has ever mutated a cluster through this path.

## 12. Verification **[NOT YET]**

`agent/verification.py` re-reads two independent signals — rollout health from
the control plane, and `/health` through the Service — and returns `PASS` only
if both pass. **No `EvidenceReader` implementation exists** (task `VER-001`).

## 13. Audit record

```bash
ls records/
cat records/INC-*.json
```

`agent/audit.py` writes here. **The dashboard reads `agent/records/`** —
a different directory — because its `agent.record` import fails and falls back.
Task `DASH-001`.

## 14. Reset

```bash
bash scripts/reset_healthy.sh
```

---

## Manual fallback that works today

If the integration is not finished, this is honest and demonstrable:

```bash
bash scripts/reset_healthy.sh          # healthy baseline
bash scripts/inject_incident.sh        # real, visible failure
kubectl -n opspilot get pods           # 2 old Ready, new 0/1 NotReady
python -m pytest -q                    # 62 passed — the safety properties
python -c "from mcp_server import tools; import json; print(json.dumps(tools.get_full_snapshot(), indent=2, default=str))"
```

That shows a real cluster failure, real evidence collection, and a tested
safety model. It does not show Bob reasoning or remediation — **say so** rather
than showing the mocked dashboard.

---

## Warning about the current dashboard

Do not record the demo video against `dashboard/app.py` as it stands.
`_decide()` writes an audit record whose six verification checks each report
the value of the `approved` boolean. Clicking Approve produces a record
asserting that the rollout completed, all replicas are ready, no pods run the
suspect image, and three services returned health 200 — **with nothing
checked and no cluster contacted.**

Presenting that as a verified recovery is a false claim to a judge, and it
contradicts the project's own `AGENTS.md` rule 3. Fix `DASH-001` first, or
demo the manual fallback and state the limitation plainly.
