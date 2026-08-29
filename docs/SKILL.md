---
name: incident-ui-flow
description: >-
  The screen-by-screen contract for rendering a KubeMedic incident from
  detection to closure, so a judge follows the whole lifecycle without reading
  source. Activates on incident dashboard, incident view, rendering incident
  state, showing evidence or Bob analysis in the UI, or incident timeline.
user-invocable: true
---

# The incident screen contract

The dashboard has one job: a stranger with ninety seconds understands what
broke, why, what was proposed, who decided, and whether it worked.

## The nine questions

Every one of these is answerable from the incident screen without scrolling
hunting or clicking into a submenu. If a question has no answer on screen, the
screen is incomplete.

1. What broke? — workload name, prominent
2. Why? — root cause statement
3. What evidence supports it? — the supporting evidence array, visible
4. What does IBM Bob recommend? — action and target, labelled as Bob's
5. What will it affect? — blast radius
6. What is the risk? — level *and* the sentence explaining it
7. What gets checked afterwards? — the verification plan, before execution
8. Who approved it? — approver and timestamp
9. Did it work? — verification result, PASS or FAIL, with which signals

## States that must render

Take these from the incident state machine. Each needs a distinct visual
treatment — a judge should identify the state from across a room.

```
DETECTED → EVIDENCE_COLLECTED → ANALYZED → PLAN_PROPOSED
  → AWAITING_HUMAN_REVIEW
      ├─ APPROVED → EXECUTING → VERIFYING → VERIFIED → RESOLVED
      └─ REJECTED → FEEDBACK_REQUIRED → FEEDBACK_RECORDED → NOT_EXECUTED
```

**The failure states matter as much as the happy path.** Build all of these,
because each one is a moment where a lesser project would show a spinner:

- `EVIDENCE_COLLECTION_FAILED` — "Evidence collection failed", naming which
  signal was unavailable. No diagnosis is shown, because none was made.
- `bob_unavailable` — "IBM Bob unavailable". Do not render an analysis panel.
  Do not show a placeholder that could be mistaken for a real analysis.
- `VERIFICATION_FAILED` — loud, and the incident stays open. Name which of the
  two signals failed and what was observed.

A verification panel that can only ever show PASS is not a verification panel,
and it is the first thing a skeptical reviewer will poke at.

## Panel order on the incident screen

Top to bottom, because this is the order the story happens in:

1. **Header** — incident id, status badge, workload, time window
2. **Tickets** — the correlated ones, showing they were merged
3. **Evidence** — pods with ready counts and images, events, health, revisions
4. **IBM Bob Analysis** — explicitly labelled as Bob's, with root cause,
   confidence *and its reason*, supporting evidence, and contradicting
   evidence. Render the contradicting-evidence field even when it says "none
   found" — its presence is the point.
5. **Proposed Remediation** — action, target, blast radius, risk with reason,
   reversibility, expected effect, verification plan
6. **Human Final Review** — the two controls, or the recorded decision
7. **Verification** — the two signals, separately, with what each returned
8. **Timeline** — the whole thing, ordered, with timestamps
9. **Audit** — the structured record

## The dual-signal panel

Give this real visual weight. During a bad rollout you will show:

```
Kubernetes rollout:   DEGRADED
Application health:   200 OK
```

Both true, and neither sufficient alone. Show them side by side as two
independent readings, never merged into one "health" indicator. After
remediation both read healthy and only then does the incident resolve.

This is the clearest argument in the entire project and it is made almost
entirely by layout. Do not bury it.

## Rendering rules

- **Never compute.** Severity, confidence, root cause and verification result
  arrive as data. If you find yourself deriving one in JavaScript, the API is
  missing a field — file a handoff, do not patch around it.
- **Never call Bob from the browser.** The dashboard reads incident state from
  the agent's API. Nothing else.
- **Label inference as inference.** The analysis carries `is_inference`. When
  it is true, the UI says so. A judge who sees a model's guess presented as an
  observed fact will discount everything else on the page.
- **Show timestamps.** Every state transition carries one.

## Vocabulary

Incident · Evidence · Correlation · Root Cause · IBM Bob Analysis ·
Remediation Plan · Human Final Review · Approve · Reject · Rejection Reason ·
Executing · Verification · Verified · Resolved.

Never: AI Fix, Auto-Heal, Self-Healing, Magic Repair, autonomous. These
contradict the product's central claim and a judge will notice the mismatch
between the label and the architecture.
