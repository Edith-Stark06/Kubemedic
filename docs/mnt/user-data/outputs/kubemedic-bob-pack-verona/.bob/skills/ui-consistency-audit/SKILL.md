---
name: ui-consistency-audit
description: >-
  Sweeps the dashboard and workload for leftover provider references, obsolete
  architecture terminology, broken endpoints and inconsistent vocabulary.
  Activates on dashboard audit, UI cleanup, removing legacy UI, or checking
  the frontend matches the architecture.
user-invocable: true
---

# Dashboard consistency audit

The implementation, documentation, UI and Bob report must tell one story. A UI
labelled with the wrong AI provider while the submission claims IBM Bob is not
a cosmetic problem — it tells a reviewer the Bob usage is decoration.

Run this early, and again before recording.

## Sweep for

**Provider references.** Search `dashboard/` and `workload/` for: gemini,
google-genai, google.generative, genai, GOOGLE_API_KEY, GEMINI_API_KEY, palm,
vertexai. Check places grep does not naturally reach — inline JS strings,
template literals, HTML comments, CSS class names, alt text, page titles,
favicon, and any diagram image files. An old PNG that says Gemini is a MAJOR
finding and greps clean.

**Obsolete architecture terms.** OpsPilot, orchestrator, Track 1, Track 2, and
any endpoint the old architecture exposed.

**Broken endpoints.** Every fetch call in the dashboard, checked against the
API the agent actually exposes. Read `agent/` to verify — read only, never
edit, it is Ramana's lane. A 404 during recording is unrecoverable.

**Vocabulary drift.** The approved terms are: Incident, Evidence, Correlation,
Root Cause, IBM Bob Analysis, Remediation Plan, Human Final Review, Approve,
Reject, Rejection Reason, Executing, Verification, Verified, Resolved.

Flag anything else, especially: AI Fix, Auto-Heal, Self-Healing, autonomous,
Magic Repair, "AI will fix this". These contradict the architecture and a
judge will notice the mismatch between the label and the claim.

**Development leftovers.** Placeholder copy, lorem ipsum, TODO comments
visible in rendered output, console.log statements, hardcoded localhost paths,
absolute local filesystem paths, test data with someone's real name in it.

**Unstyled states.** Load each incident state and look for the ones nobody
built: empty lists, long text overflowing, errors, and the three failure
states — evidence unavailable, Bob unavailable, verification failed.

## Report format

Per finding: file, line, quoted text, severity, and the fix in one line.

- **BLOCKER** — breaks the demo or is a compliance risk
- **MAJOR** — visible inconsistency a judge would spot
- **MINOR** — cosmetic

Then the summary question: **watching only the video, would a judge conclude
this project uses IBM Bob?** If not, list exactly what says otherwise.

## Do not

Do not edit `agent/`, `mcp_server/`, `k8s/` or `scripts/` to resolve a finding.
Read them to confirm the contract, then file a handoff naming the owner, the
file and the change needed.
