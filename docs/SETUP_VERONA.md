# Bob environment setup — Verona

Frontend, workload, demo and story lane. Copy this pack into your **home**
`~/.bob/` directory, not the repo.

---

## Why global and not the repo

Ramana owns `.bob/` in the repository exclusively — that directory is the
graded asset pack a judge reads, and it holds the product's runtime
configuration. Your modes and skills are tooling for *building* the UI. They
are not product config, they do not belong in the submission pack, and putting
them there creates a merge conflict on the one directory that must not have
one.

Global and project configuration both load, and none of your slugs collide
with his, so all seven modes appear in your mode picker. You can install this
right now without waiting on his branch.

If the team later decides one of these skills belongs in the repo, it goes in
through Ramana as a handoff, not by editing `.bob/` yourself.

---

## Install

```bash
mkdir -p ~/.bob/settings ~/.bob/skills ~/.bob/agents

cp -r kubemedic-bob-pack-verona/.bob/skills/*  ~/.bob/skills/
cp -r kubemedic-bob-pack-verona/.bob/agents/*  ~/.bob/agents/
cp -r kubemedic-bob-pack-verona/.bob/rules-kubemedic-ui        ~/.bob/
cp -r kubemedic-bob-pack-verona/.bob/rules-kubemedic-ui-critic ~/.bob/
cp -r kubemedic-bob-pack-verona/.bob/rules-kubemedic-story     ~/.bob/
```

For the two settings files, **merge rather than overwrite** — you may already
have content in them:

- `~/.bob/settings/custom_modes.yaml` — append the three modes under the
  existing `customModes:` key
- `~/.bob/settings/mcp_settings.json` — add the servers to the existing
  `mcpServers` object

Then restart Bob.

**Verify:** mode picker shows `KubeMedic UI`, `KubeMedic UI Critic`,
`KubeMedic Story`. Settings → Skills shows 8 global skills. Settings → MCP
shows `playwright` connected.

Then check the lane boundary actually holds. In `kubemedic-ui`, ask Bob to
edit `agent/executor.py`. It should refuse — the `fileRegex` blocks it. That
is not a formality; it is what stops a 2am "quick fix" in Ramana's directory
from becoming a merge conflict at 4am.

---

## What's in the pack

**Three modes.**

| Mode | For | Can write |
|---|---|---|
| `kubemedic-ui` | Dashboard and workload implementation | `dashboard/`, `workload/`, `reports/`, demo docs |
| `kubemedic-ui-critic` | Judge's-eye review of a screen | Nothing — reports only |
| `kubemedic-story` | Video script, shot list, narration | `docs/`, `DEMO.md`, `submission/writeup/` |

**Eight skills.** `incident-ui-flow` (the nine questions every screen must
answer) · `human-review-ui` (approve/reject and the mandatory reason dialog) ·
`correlation-viz` (many-to-one, made obvious) · `demo-workload` (the
ticket-booking app and its failure lever) · `demo-reset` · `filmable-ui` ·
`demo-script` · `ui-consistency-audit`.

**Four personas.** `judge-eye-reviewer` · `endpoint-contract-checker` ·
`ui-copy-reviewer` · `screen-legibility-checker`.

---

## Playwright MCP — the one worth setting up

This is the highest-leverage tool for your lane specifically. It lets Bob open
the dashboard in a real browser, click through the incident flow, screenshot
each state, and actually verify things like *does the reject submit button
stay disabled on whitespace*. That is a class of check you would otherwise do
by hand, forty times, at midnight.

```
Open the dashboard at http://localhost:<port>. Walk the full incident
lifecycle: detected, analysed, awaiting review, rejected with a reason,
approved, executing, verified. Screenshot each state at 1920x1080.

For each: report what renders, what is missing against the incident-ui-flow
skill, and anything that overflows, truncates or sits at low contrast.

Then test the reject dialog specifically:
  - submit disabled on empty
  - submit disabled on whitespace only
  - submit enabled on real text
  - cancel closes with no state change
  - after rejecting, the reason renders verbatim and "Action executed: NO"
    appears
```

**Disable it before recording.** A browser session Bob controls is one more
process that can hang on camera, and you will not need it during a take.

---

## Your run order

**1. Audit before you build — `kubemedic-ui-critic`, ~30 min**

```
Run the ui-consistency-audit skill against dashboard/ and workload/.

Use the ui-copy-reviewer persona for the text sweep, the
endpoint-contract-checker persona to verify every dashboard fetch against the
API that agent/ actually exposes, and the screen-legibility-checker persona
for the CSS.

Report findings as BLOCKER / MAJOR / MINOR with file, line, fix and a cost in
minutes. Do not change anything.

End with the summary question: watching only this UI, would a judge conclude
the reasoning is done by IBM Bob?
```

Do this first. You need the written list of what is broken before you start
fixing, and the endpoint check will surface anything Ramana's consolidation
has already moved under you.

**2. The incident screen — `kubemedic-ui`, longest block**

```
Rebuild the incident view against the incident-ui-flow skill.

Read .bob/skills/incident-correlation/references/evidence-schema.md first —
that is the frozen contract for the analysis JSON you are rendering. Render
only fields that exist in it.

Panels top to bottom: header with status badge, correlated tickets, evidence,
IBM Bob Analysis, proposed remediation, human review, verification, timeline,
audit.

Give the dual-signal panel real weight — rollout status and application health
as two separate readings, side by side, never merged into one indicator.

Build the three failure states as well: evidence unavailable, IBM Bob
unavailable, verification FAILED. Do not build only the happy path.
```

**3. The review controls — `kubemedic-ui`, ~90 min**

```
Implement the approve and reject controls per the human-review-ui skill.

The rejection dialog restates the action, autofocuses the textarea, and
disables submit while the reason is empty or whitespace only. After a
decision, replace the controls with the recorded outcome, showing the human's
reason verbatim and "Action executed: NO".

Style rejection as a recorded decision, not an error. No red, no warning icon.

The client-side disable is UX. The real check is server-side in Ramana's API.
Confirm the field name you send matches what his endpoint validates — file a
handoff if it does not.
```

This is the fifteen seconds the demo turns on. Spend the time.

**4. Correlation visual — `kubemedic-ui`, ~45 min**

```
Build the many-to-one correlation visual per the correlation-viz skill.
Plain SVG or CSS, no charting library.

Three tickets converging into one incident, with the correlation_basis
reasons rendered beside it, and any excluded_tickets shown outside the funnel
with the reason they were kept separate.

Static. No animation.
```

**5. Judge's-eye pass — `kubemedic-ui-critic`, ~20 min, twice**

```
Use the judge-eye-reviewer persona. Review the incident screen as a judge with
ninety seconds and no source access. Answer the nine questions, score design
and usability out of 5, and give the cheapest fix that would raise it.

Be harsh.
```

Run it once mid-build and once before recording. The second one always finds
something.

**6. Script, then record — `kubemedic-story`**

```
Write the demo script and shot list per the demo-script skill. Structure:
app working, break it, tickets arrive, evidence, Bob correlates three into
one, the plan, REJECT with a real typed reason, approve, execute, independent
verification, then how IBM Bob was used.

Narration must claim only what the recording shows. Mark where the narration
goes silent.
```

Start the script Saturday, not Sunday morning.

---

## Four things worth knowing before you start

**The dashboard renders, it never reasons.** It does not call Bob. It does not
compute severity, confidence, root cause or verification result. If you need a
value the API does not send, file a handoff — do not derive it in JavaScript.
A dashboard that computes something the audit record computes differently is a
bug you will find on camera.

**The ticket-booking app is the patient, not the product.** It needs to be
believable, not good. If it already works, change as little as possible. Every
hour there is an hour not spent on the dashboard, which is the thing actually
being judged.

**Do not build an agent UI.** Bob is the interface for the agent. You render
the incident record. A custom orchestrator UI would replace exactly the
capability the hackathon grades.

**Build the failure states.** Verification FAILED, Bob unavailable, evidence
unavailable. A verification panel that can only show PASS is not a
verification panel, and it is the first thing a skeptical reviewer pokes at.
Showing a caught failure is more persuasive than three clean passes.
