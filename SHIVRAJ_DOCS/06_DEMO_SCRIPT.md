# SUB-004 — Demo video script

**Owner:** Verona (recording), Shivraj (cluster) · **Target: 4-5 minutes**
· Must be in **English** and must state **how IBM Bob was used**.

Two versions. Pick by 15:00 IST based on what actually works.

- **Version A — dashboard.** Only if `DASH-001` has landed and the dashboard
  renders real API data.
- **Version B — terminal.** Works today. Entirely real. Use this if A is not
  ready, and do not apologise for it.

**Never demo the current mocked dashboard.** `_decide()` writes audit records
asserting six verification checks passed based on whether Approve was clicked.
Presenting that as verified recovery is a false claim to a judge.

---

## Before recording

```bash
bash scripts/reset_healthy.sh
kubectl -n opspilot get pods            # expect 2/2 Running
rm -f records/INC-*.json                # so the run's record is unambiguous
python -m pytest                        # expect 238 passed
```

Close Slack, silence notifications, and rehearse once. The injected failure
takes ~25 seconds to appear — know that so you do not fill the silence with
"um, it should be loading".

---

## Version B — terminal demo (works today)

### 0:00-0:30 — The problem

> "When a bad deployment goes out, you don't get one alert. You get five, from
> five different places, and someone has to work out at 3am that they're all
> the same problem. KubeMedic uses IBM Bob to do the correlation and the
> reasoning — but it never touches your cluster without a human saying yes."

Show the repo tree briefly. `README.md` diagram on screen.

### 0:30-1:00 — Healthy baseline

```bash
kubectl -n opspilot get pods
curl -s localhost:8080/health
```

> "Two replicas, healthy. A ticket-booking service — the app returns healthy
> and is serving."

### 1:00-1:30 — Inject a real failure

```bash
bash scripts/inject_incident.sh
kubectl -n opspilot get pods -w
```

> "I'm shipping a bad image. Same source, built with HEALTHY=false, so the
> readiness probe fails."

Wait for the new pod at `0/1 Running`.

> "Notice what happens: the old pods keep serving. The rollout stalls instead
> of taking the service down. And that matters in a second."

### 1:30-2:15 — Evidence and correlation

```bash
python -c "
from mcp_server.watcher import KubeWatcher
from mcp_server import tickets
from mcp_server.db import init_db
init_db()
for t in KubeWatcher().check_once():
    print(tickets.get_ticket(t).title)
"
```

> "The MCP server observes the cluster and files a ticket per distinct signal —
> the rollout is stalled, and a pod isn't becoming ready. Two separate
> complaints, from two different sources."

Then:

```bash
curl -s -X POST localhost:8100/api/incidents | python -m json.tool
```

> "Both tickets correlate into one incident. Here's *why* each one joined —
> same workload, same time window, matching failure symptoms. That's the
> many-to-one: several symptoms, one underlying problem."

### 2:15-3:00 — IBM Bob

**If `BOB-001` landed:**

> "The evidence goes to IBM Bob. Bob returns ranked hypotheses with confidence
> and the evidence supporting each, a root cause, and one recommended action
> from a fixed allowlist of three. Here's what it said."

Show `analysis.hypotheses` and `analysis.root_cause`.

**If Bob is unavailable — say this, do not skip it:**

> "IBM Bob is the reasoning layer — `agent/bob.py` is the only place in the
> system that calls a model. Right now our credentials aren't provisioned, and
> watch what the system does: it reports `BOB_UNAVAILABLE`, produces no
> diagnosis, and refuses to build a plan. It won't invent an answer because its
> reasoner is down. That refusal is tested — four tests exist purely to prove
> it never fabricates."

Then continue with an operator-specified plan and say so.

### 3:00-3:45 — The human gate

```bash
curl -s -X POST localhost:8100/api/incidents/$ID/execute
# 409: Execution requires APPROVED state
```

> "First, try to execute without approval. Refused. And the cluster is
> unchanged — that's asserted, not assumed."

```bash
curl -s -X POST .../review -d '{"decision":"REJECTED"}'
# 400 feedback_required
```

> "Now reject the plan without saying why. Also refused — 400,
> `feedback_required`. That's server-side, not a disabled button. And it's not
> bureaucracy: the reason gets added to the incident context and sent back to
> Bob to produce a revised plan. A rejection with no reason leaves the agent
> unable to do anything different."

```bash
curl -s -X POST .../review -d '{"decision":"REJECTED","feedback":"Check the rollout history first."}'
```

> "With a reason, it's recorded — and the cluster is still untouched. A rejected
> plan can't execute. That's structural: the state machine refuses the
> transition."

### 3:45-4:30 — Approve, execute, verify

```bash
curl -s -X POST .../review -d '{"decision":"APPROVED","approver":"shivraj"}'
curl -s -X POST .../execute | python -m json.tool
```

> "Approved. Now it rolls back — through the Kubernetes API, one of three
> allowlisted actions. No shell, no kubectl the model wrote."

> "And here's the part I care about most. Verification re-reads the cluster on
> two independent signals: the control plane's view of the rollout, and the
> application answering HTTP through the Service. Both have to pass."

> "Remember the app stayed healthy during the outage, because the old pods kept
> serving? That's exactly why one signal isn't enough. The health check alone
> would have missed this failure entirely."

### 4:30-5:00 — The record

```bash
cat records/INC-*.json | python -m json.tool | head -40
```

> "Every incident leaves an audit record: which tickets, what Bob said, who
> approved it, what was rejected and why, what executed, and how recovery was
> verified. If Bob was unavailable, the record says so. We never claim a
> verification we didn't run."

> "238 tests, and `scripts/validate.sh` runs that whole loop against a live
> cluster with hard assertions at every step."

---

## Version A — dashboard demo

Same narrative; replace 1:30-4:30 with the UI. Non-negotiable beats:

1. **The correlation view** with `correlation_basis` visible — the reasons, not
   just the grouping.
2. **Bob's hypotheses** with confidence and supporting evidence shown.
3. **Reject with no reason → the server refuses.** Show the 400. Say the button
   is not the control.
4. **The reason appears** on the incident afterwards.
5. **The revised plan** differs from the rejected one.
6. **Verification shows two named signals**, each pass/fail separately.

If any of those six cannot be shown for real, do that beat in the terminal
instead. A mixed demo is fine. A fabricated one is not.

---

## Lines worth keeping

- "It's not an autonomous healing platform. A human approves every change."
- "MCP answers *what is happening*. IBM Bob answers *what it means*. The human
  answers *should this happen*. The verifier answers *did it work*."
- "Bob has no tool that can change the cluster. Not a policy — there is no such
  tool registered. CI asserts it."
- "If Bob is down, the system says so. It doesn't guess."

## Lines to avoid

- "Automatically fixes" / "self-healing" / "AI-powered auto-remediation" —
  `AGENTS.md` bans this vocabulary, and it undersells the actual claim.
- Any statement that Bob diagnosed something if `BOB-001` did not land.
- Any claim about verification that the run on screen did not perform.

---

## Upload checklist

- [ ] English throughout
- [ ] States how IBM Bob was used (required by the rules)
- [ ] Under any length limit the portal specifies
- [ ] Link works **in a logged-out browser** — test in a private window
- [ ] No credentials, kubeconfig, or API keys visible on screen at any point
- [ ] Link added to `03_SUBMISSION_CHECKLIST.md`
