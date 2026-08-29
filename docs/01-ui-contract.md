# UI mode contract

## The dashboard renders. It does not reason.

- It never calls IBM Bob. Incident state arrives from the agent's API.
- It never computes severity, confidence, root cause, correlation or
  verification result. Those are data.
- It never executes a Kubernetes action.

If you need a value the API does not provide, **do not derive it in
JavaScript.** Write a handoff request to `docs/handoffs.md` naming the owner,
the endpoint and the field. Deriving it client-side means the dashboard and
the audit record can disagree, and the audit record is the thing that has to
be true.

## Stay in lane

Writable: `dashboard/`, `workload/`, `reports/`, demo documents.

Readable but never writable: `agent/`, `mcp_server/`, `k8s/`, `scripts/`,
`.bob/`. Read them freely to confirm a contract. If one needs a change, file a
handoff. Mid-hackathon, an unannounced edit in someone else's directory costs
more time than it saves.

## No new dependencies

No new framework, no build step, no npm install, no CDN link. Whatever the
dashboard is written in today, it stays. A toolchain change this close to a
deadline is the most expensive mistake available, and it is the kind that
looks small when you start it.

## Honest states are required, not optional

These three must render properly, because each is a moment where a weaker
project shows a spinner:

- **IBM Bob unavailable** — render this, not a placeholder analysis. Never
  show anything that could be mistaken for a real analysis.
- **Evidence collection failed** — name the missing signal. Show no diagnosis,
  because none was made.
- **Verification FAILED** — loud, incident stays open, name which of the two
  signals failed and what was observed.

A verification panel that can only show PASS is not a verification panel.

## Client-side validation is UX, never enforcement

Disabling the reject button on an empty reason is good UX. The actual check is
server-side and returns 422. Never describe the JavaScript guard as the
safety mechanism, and never build a flow that depends on it holding.

## Build it to be filmed

16px body minimum, 7:1 contrast, no truncation on root cause statements,
rejection reasons, evidence citations or errors. No animation on information.
Status readable at a glance in a fixed position. See the `filmable-ui` skill.

## Vocabulary

Incident, Evidence, Correlation, Root Cause, IBM Bob Analysis, Remediation
Plan, Human Final Review, Approve, Reject, Rejection Reason, Executing,
Verification, Verified, Resolved.

Never: AI Fix, Auto-Heal, Self-Healing, autonomous, Magic Repair.
