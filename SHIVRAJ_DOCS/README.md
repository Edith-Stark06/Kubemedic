# Owner notes

The hackathon is over.

Everything here is forward-looking. The team-allocation layer — per-person
handoffs, cross-owner blocking requests, submission-deadline checklists — has
been removed; it described a three-person sprint that no longer exists. It is
in git history if it is ever wanted.

| File | What it is |
|---|---|
| [`01_IBM_BOB_SETUP.md`](01_IBM_BOB_SETUP.md) | What has to be done inside the IBM Bob application, and why the API path is still unresolved |
| [`02_BOB_RUNBOOK.md`](02_BOB_RUNBOOK.md) | Copy-paste prompts for running an incident through Bob interactively |
| [`03_ROADMAP.md`](03_ROADMAP.md) | The remaining engineering work, in dependency order |

Project documentation is in [`docs/`](../docs/) — that describes the system as
built. `docs/23_SYSTEM_WORKFLOW.md` is the entry point.

---

## Current state

`main` is the only branch that matters. 351 tests pass. The end-to-end loop is
verified against a live k3s cluster and reproducible without one via
`python scripts/dry_run.py`.

**Working:** MCP evidence layer, ticket generation, many-to-one correlation,
human review with mandatory rejection feedback, the feedback-to-revision loop,
allowlisted remediation through the Kubernetes API, dual-signal verification,
audit records, the operator console, the CLI, and a pluggable reasoning layer
with a runtime engine switch.

**Not working, and why:**

| Engine | Blocker |
|---|---|
| IBM watsonx | The `KUBEMEDIC` project has no runtime associated. The active WML instance is `8f0fcd06`; the two projects that *are* associated point at Inactive instances. One console step from working — see `01_IBM_BOB_SETUP.md` |
| IBM Bob | Endpoint unresolved. `cloud.manufact.com` returns 401 on every path, `bob.ibm.com` serves 404 HTML. The base URL came from the IDE's `extension.js` and was never confirmed |
| Gemini | Works. Free-tier quota is 20 requests, so it rate-limits under repeated demo runs |

## A note on the submission record

`submission/` describes an entry that was made, including who wrote which part.
That is a historical record, not a work assignment, and it stays accurate
regardless of who owns the project now. Changing ownership going forward does
not change who did what.
