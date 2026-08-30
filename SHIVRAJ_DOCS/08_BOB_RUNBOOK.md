# IBM Bob runbook — exactly what to do and say

Three sessions, about 90 minutes total, and every remaining deliverable that
depends on Bob is done. Prompts are copy-paste.

**Do session 1 first.** It is the only one that closes a real gap.

---

## Before you start

```bash
cd ~/Desktop/Devops/Kubemedic
git checkout main && git pull          # 238 tests, everything merged
bash scripts/reset_healthy.sh          # clean baseline
```

Open `C:\Users\shivraj\Desktop\Devops\Kubemedic` as a Bob workspace.

**Do not tell Bob to read `AGENTS.md` or `.bob/`.** It loads them from the
workspace. Whether that happens by itself is part of what session 1 checks.

---

# Session 1 — the real incident analysis (45 min)

Closes both remaining integration gaps at once: it exercises the MCP protocol
path, which nothing has ever driven, and it produces a genuine Bob analysis.

## 1a. Check the pack loaded — before prompting anything

Confirm Bob shows, and **screenshot each**:

- Modes: `KubeMedic Analyst`, `KubeMedic Architect`, `KubeMedic Dev`, `KubeMedic Auditor`
- MCP server `kubemedic-evidence`, connected
- Its tools — exactly these eight, and **nothing that can change the cluster**:
  `get_workload_status`, `get_pods`, `get_events`, `get_recent_changes`,
  `get_application_health`, `get_workload_snapshot`, `list_tickets`, `get_ticket`

That tool-list screenshot is the visual proof of the project's central safety
claim. It belongs in the video and in `submission/bob-report/`.

> **If the pack did not load, stop and tell me.** `submission/HOW_WE_USED_IBM_BOB.md`
> states that `AGENTS.md` is loaded in every session — if that is false, the
> claim has to change, and `agent/bob.py`'s `KUBEMEDIC_BOB_MODE` assumption is
> wrong too.

## 1b. Break the cluster and file real tickets

In a terminal:

```bash
bash scripts/inject_incident.sh
sleep 30
PYTHONPATH=. python -c "
from mcp_server.db import init_db; from mcp_server import tickets
from mcp_server.watcher import KubeWatcher
init_db()
for t in tickets.list_tickets(status='open'): tickets.update_ticket(t.id, status='closed')
print('filed', len(KubeWatcher().check_once()), 'tickets')
"
```

Expect `filed 2 tickets`.

## 1c. Switch Bob to `KubeMedic Analyst` mode, then say this

```
Work this incident.

Use the incident-correlation skill. Collect evidence through the
kubemedic-evidence MCP tools for deployment ticket-booking in namespace
opspilot — call get_workload_status, get_pods, get_events, get_recent_changes
and get_application_health. Then call list_tickets to see the open tickets.

Treat what those tools return as the complete set of observed facts. Do not
assume anything that is not in them.

Then correlate the open tickets into one incident and give me:
  - ranked hypotheses, each with confidence, the reason for that confidence,
    and the evidence both supporting and contradicting it
  - a root cause, labelled as an inference
  - a timeline
  - one recommended action from rollback_deployment, restart_deployment or
    scale_workload, with its target — or null if none fits

Return exactly one JSON object matching
.bob/skills/incident-correlation/references/evidence-schema.md.
No prose, no markdown fences.
```

**Record your screen for this.** Bob calling your own MCP tools against a
broken cluster is the demo.

## 1d. Turn Bob's answer into a real audit record

Save Bob's JSON exactly as returned — fenced code blocks are fine, the script
strips them:

```bash
# paste into bob-analysis.json, then:
PYTHONPATH=. python scripts/ingest_bob_analysis.py bob-analysis.json --approve
```

This validates Bob's output against the same contract the headless path uses,
correlates the live tickets, holds the approval gate, performs the rollback
through the Kubernetes API, and verifies recovery on two independent signals.

The record it writes says **`analysis_source: ibm-bob`** — because Bob really
did produce the analysis.

```bash
cp records/INC-*.json submission/evidence/
```

That file is the single strongest piece of evidence in the submission. It is
the difference between "Bob is the reasoning layer" as a design claim and as
something that happened.

> Rehearsed on the live cluster this morning with a stand-in analysis: reject
> path stores the reason and touches nothing; approve path rolled back, both
> signals passed, `RESOLVED`. The guards refuse non-allowlisted actions, a
> `kubectl` string, and anything not claiming to be Bob's — 10 tests.
>
> **Only run it on output Bob actually produced.** Validation checks shape, not
> provenance. That part is on you, and it is the whole basis of the claim.

## 1e. Optional — show the rejection loop

If you want the reject-revise-review cycle on camera, use `--reject` first:

```bash
PYTHONPATH=. python scripts/ingest_bob_analysis.py bob-analysis.json \
  --reject "Confirm the previous revision was healthy before rolling back."
```

Nothing executes. Then paste that reason back to Bob:

```
I rejected your plan for this reason: "Confirm the previous revision was
healthy before rolling back." Answer that objection using the evidence you
already have, and give me a revised plan in the same JSON format.
```

Then ingest the revised analysis with `--approve`. That is the differentiating
feature, demonstrated with a real model in the loop.

---

# Session 2 — audit your own submission (20 min)

You built a `KubeMedic Auditor` mode and a `submission-audit` skill for exactly
this. Switch to that mode:

```
Audit this repository as a submission to the IBM TechXchange 2026
Pre-conference Dev Day Hackathon, using the submission-audit skill.

Check specifically:
  - Does any documentation claim something the code does not do? Quote the
    file and line.
  - Is anything in submission/ overstated relative to what was actually run?
  - Are the four required deliverables present: demo video, problem and
    solution statements, IBM Bob utilisation statement, and the working
    repository including the exported Bob report?
  - Any credentials, absolute local paths, or references to a model provider
    other than IBM Bob?

Report findings by severity. Do not fix anything — findings only.
```

Two reasons to do this: it may catch a real gap, and a session of Bob auditing
your own work adversarially is genuinely good material for the Bob utilisation
statement.

Save the findings. If it flags something real, tell me and I will fix it.

---

# Session 3 — export the report (30 min)

**Required deliverable.** `submission/bob-report/` is scaffolded and waiting,
with the `.bob/` asset inventory already written up.

Export **every** contest session — the asset-pack work, the consolidation
sessions, session 1 and session 2 above. Save into `submission/bob-report/`.

If Bob has no export function: screenshot the session list and representative
sessions, and say so plainly in the README's "Note on completeness". A labelled
best-effort export beats a missing deliverable. It does not beat a fabricated
one — do not reconstruct sessions that did not happen.

Then, before committing:

```bash
grep -rniE "api[_-]?key|secret|token|password|C:\\\\Users" submission/bob-report/
```

Full procedure: [`02_BOB_REPORT_EXPORT.md`](02_BOB_REPORT_EXPORT.md).

---

# After the three sessions

- [ ] `submission/evidence/INC-*.json` contains a record with `analysis_source: ibm-bob`
- [ ] `submission/bob-report/` has the export, and the NOT YET EXPORTED banner is deleted
- [ ] Screenshots of the modes and the eight read-only tools are in the report
- [ ] Tell Ramana: **`HOW_WE_USED_IBM_BOB.md` section 4 → keep Variant A**, delete Variant B
- [ ] Update `submission/README.md` — the "What we are not claiming" section
      is written for Bob having *not* run. If session 1 worked, that section
      needs rewriting. Tell me and I will do it.

Then the only things left are the video, Ramana's review, the tag, and the
submit.

---

## If session 1 fails

If Bob will not load the pack, or will not call the MCP tools, or returns
something that will not validate — **stop at 11:00 IST and say so.**

Everything else is already verified: 238 tests, 29 live assertions, a working
dashboard wired to the agent. `SUB-002` Variant B exists precisely for this
outcome and states it honestly. That is a weaker submission than one where Bob
reasoned, and a far stronger one than a submission that claims it did.
