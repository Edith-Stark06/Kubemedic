---
name: human-review-ui
description: >-
  Specification for the approve and reject controls, the mandatory rejection
  reason dialog, and how a recorded human decision is displayed. Activates on
  approve reject buttons, human review UI, rejection dialog, rejection reason,
  or approval state display.
user-invocable: true
---

# The human review controls

This is where the product's central claim becomes visible. Build it carefully;
it is roughly fifteen seconds of the video and it decides whether the safety
story reads as real or as decoration.

## What must never exist

There is no path from an AI recommendation to execution without a human
control in between. No "auto-approve" toggle, no "apply recommendation"
shortcut, no keyboard accelerator that skips the dialog. If the UI has a way
to go straight from analysis to execution, the architecture's whole argument
collapses at the one place a judge is looking.

## Before the decision

Show the two controls only when state is `AWAITING_HUMAN_REVIEW`. Directly
above them, and visible without scrolling, the reviewer can see: the action,
the target, the blast radius, the risk with its reason, and the verification
plan.

They are approving a specific change. Make the change legible before asking
for the decision.

If the analysis carries `notes_for_reviewer`, render it prominently. That
field exists to name the reason a human might reasonably reject — a
maintenance window, a deliberate rollout — and surfacing it is what makes the
gate feel like a real decision rather than a rubber stamp.

## The rejection dialog

```
REJECT REMEDIATION

You are about to reject:
  Rollback deployment/ticket-booking to revision 3

Why are you rejecting this remediation?
  [ textarea, autofocused ]

This feedback is stored with the incident and becomes part of
the audit history.

              [ Cancel ]  [ Reject and Record Reason ]
```

Requirements:

- The submit control is **disabled while the textarea is empty or whitespace**.
- Whitespace-only does not count as a reason. Trim before checking.
- The proposed action is restated inside the dialog. The reviewer should not
  have to remember what they are rejecting.
- Cancel closes with no state change at all.
- Autofocus the textarea. On camera this saves a click and looks deliberate.

**The disabled button is UX, not enforcement.** The real check is server-side
in Ramana's API, which returns 422 on empty feedback. Never treat the
JavaScript guard as the gate — if you find yourself relying on it, say so out
loud so the backend check gets tested.

## After a decision

Replace the controls with the recorded outcome. Never leave a live Approve
button on a decided incident.

Approved:
```
Decision:   APPROVED
Approved by: <approver>
At:          <timestamp>
Execution:   <state>
```

Rejected:
```
Decision:      REJECTED
Rejected by:   <approver>
At:            <timestamp>
Reason:        "<the human's words, verbatim>"
Action executed: NO
```

Render the reason **verbatim**. Do not summarize it, do not truncate it
without an expand control. Those are the human's words and their presence in
the audit record is the feature.

## The rejection is a demo moment, not an error state

Do not style a rejection as a failure — no red, no warning icon, no
apologetic copy. A rejection is the system working exactly as designed. Style
it as a recorded decision, equal in weight to an approval.

The strongest fifteen seconds available to this project is: Bob recommends a
rollback, the reviewer types "this deployment is an approved maintenance
activity, do not roll back", presses reject, and the screen shows the reason
recorded and **Action executed: NO**. Build for that shot.

## Idempotency in the UI

After a decision is submitted, disable both controls immediately. A double
click must not send two requests. The backend is idempotent as well, but do
not make it prove that on camera.
