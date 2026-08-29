# Handoff → Verona

**You are unblocked.** The API exists, it is tested, and it drives a real
cluster. `DASH-001` is now a wiring job, not an integration job.

Paste-ready summary for chat is at the bottom.

---

## Start the API

```bash
git fetch && git checkout main && git pull      # after Shivraj merges
pip install -r requirements.txt
python -m agent.api                              # http://127.0.0.1:8100
```

Interactive docs at <http://127.0.0.1:8100/docs> — every schema is there.

---

## The endpoints

| Method | Path | Returns |
|---|---|---|
| `GET` | `/api/cluster` | Live workload, pods, app health — or `reachable: false` and why |
| `GET` | `/api/tickets` | Real tickets from SQLite |
| `POST` | `/api/incidents` | Collect evidence, correlate, ask Bob, propose. `201` |
| `GET` | `/api/incidents` | Summaries |
| `GET` | `/api/incidents/{id}` | **Everything** — evidence, correlation, hypotheses, root cause, plan, decision, execution, verification, audit log |
| `POST` | `/api/incidents/{id}/review` | `{decision, approver, feedback?}` |
| `POST` | `/api/incidents/{id}/revise` | Revised plan after a rejection |
| `POST` | `/api/incidents/{id}/execute` | Execute, then verify |
| `GET` | `/api/incidents/{id}/record` | The audit artifact |
| `GET` | `/api/limits` | `max_revisions`, allowed actions |

---

## The screen a judge needs

```
POST /api/incidents  →  render GET /api/incidents/{id}
```

That single object has every panel:

| Panel | Field |
|---|---|
| Tickets | `tickets[]` |
| **Many-to-one correlation** | `correlation.member_tickets`, `.excluded_tickets`, `.correlation_basis`, `.rationale` |
| Evidence | `evidence.pod_states`, `.events`, `.rollout_history`, `.application_health` |
| Bob's reasoning | `analysis.hypotheses[]` — each with `rank`, `statement`, `confidence`, `confidence_reason`, `supporting_evidence`, `contradicting_evidence` |
| Root cause | `analysis.root_cause.statement`, `.confidence`, `.is_inference` |
| Plan | `plan.action`, `.target`, `.blast_radius`, `.risk`, `.reversible`, `.reason` |
| Review history | `feedback_history[]`, `revision_count` |
| Execution | `execution.success`, `.message`, `.raw_response` |
| Verification | `verification.outcome`, `.signals[]` — each `name`, `passed`, `detail` |
| Audit | `audit_log[]` |

**`correlation.correlation_basis` is the money shot.** It is a list of plain
English strings explaining *why* each ticket joined:

```
"TKT-...-6896 references ticket-booking"
"TKT-...-6896 created within incident window (2026-08-29T18:51:46+00:00)"
"TKT-...-6896 describes known failure symptoms"
```

Render those under the many-to-one diagram. It turns "trust us, they're
related" into a shown argument.

---

## The reject dialog — `DASH-002`

```js
// Approve: no reason needed
await fetch(`/api/incidents/${id}/review`, {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({decision: 'APPROVED', approver: name})
});

// Reject: reason REQUIRED
const res = await fetch(`/api/incidents/${id}/review`, {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({decision: 'REJECTED', approver: name, feedback: reason})
});
if (res.status === 400) {
  // {detail: {error: "feedback_required", message: "..."}}
  // The server refuses regardless of what the UI allows.
}

// Then ask for a revised plan that answers the objection
await fetch(`/api/incidents/${id}/revise`, {method: 'POST'});
```

Disable the Reject button until a reason is typed — but understand the button
is not the control. The server refuses a reasonless rejection whatever the UI
does. Worth saying out loud in the video.

After rejecting, show `feedback_history` on the incident so the reviewer can
see what was objected to before judging the revised plan.

---

## States you must render

`OPEN` · `EVIDENCE_COLLECTED` · `ANALYSED` · **`BOB_UNAVAILABLE`** ·
`PENDING_APPROVAL` · `APPROVED` · `REJECTED` · `FEEDBACK_RECORDED` ·
`EXECUTING` · `EXECUTED` · `RESOLVED` · `VERIFICATION_FAILED`

**`BOB_UNAVAILABLE` is the one that matters and the one that will show up in
testing right now**, because no Bob credentials are configured yet. Render it
as a visible, non-alarming state: *"IBM Bob could not be reached. No analysis
was produced and no action can be approved."*

Do not hide it or fall back to placeholder content. That the system refuses to
invent a diagnosis when its reasoner is down is one of the strongest things
about it — show it deliberately.

---

## What to delete from `dashboard/app.py`

| Lines | What |
|---|---|
| 17-19 | Imports of `agent.bob.BobAgent` and `agent.record` — neither exists; the `except ImportError` hides it |
| 57-72 | `/api/status`, marked `# Mock live cluster status` → use `GET /api/cluster` |
| 149-488 | `/api/detect` — ~340 lines of fabricated tickets and evidence → use `POST /api/incidents` |
| 489-597 | `_decide()` — **priority.** `"passed": approved` on six named verification checks. Approving writes a record claiming the rollout completed, replicas are ready and three services returned 200, with nothing checked |
| 202, 299, 389 | `"source": "gemini"` |
| `index.html` 263 | "Gemini LLM for hypothesis generation" |
| `index.html` 834 | `rep.source === 'gemini'` chip |

Done when `git grep -n '"passed": approved'` returns nothing.

---

## Two things the demo cannot fake

**Health stays 200 during the incident.** `maxUnavailable: 0` keeps old pods
serving, so the app endpoint is fine while the rollout is stalled. The health
signal alone would miss it; the rollout signal catches it. If your UI shows a
red "app down", it will contradict the API. Show both signals separately.

**One real failure currently yields two tickets, not three** — rollout stalled
and pod not ready. Health does not fail, for the reason above. Do not build a
layout that assumes three.

---

## Paste into chat

```
Verona — the API is live and DASH-001 is unblocked.

  git checkout main && git pull
  pip install -r requirements.txt
  python -m agent.api        → http://127.0.0.1:8100/docs

POST /api/incidents  then render GET /api/incidents/{id} — that one object has
tickets, correlation, evidence, Bob's hypotheses, root cause, plan, decision,
execution, verification and the audit log.

correlation.correlation_basis is a list of plain-English reasons each ticket
joined the incident. Render those under the many-to-one view.

Reject: POST /api/incidents/{id}/review {decision:"REJECTED", feedback:"..."}.
No feedback → 400 feedback_required, enforced server-side. Then POST /revise
for a plan that answers the objection.

You will see state BOB_UNAVAILABLE until Ramana gets the Bob keys — that is
correct, not a bug. Render it visibly: "IBM Bob could not be reached, no
analysis produced." Don't fall back to placeholder content.

Priority is deleting _decide() in dashboard/app.py. It writes audit records
saying six verification checks passed based purely on whether Approve was
clicked. Nothing is checked. We can't show that to a judge.

Details: SHIVRAJ_DOCS/04_HANDOFF_VERONA.md
```
