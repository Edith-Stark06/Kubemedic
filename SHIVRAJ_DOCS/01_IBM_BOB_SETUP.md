# What you must do inside IBM Bob

Everything here happens in the IBM Bob application. None of it can be done from
code, which is why it is the part most likely to be left until it is too late.

**Bob is at** `C:\Users\shivraj\AppData\Local\Programs\IBM Bob\bin\bobide.CMD`
— that is where `agent/bob.py` found it.

Ordered by value. **B1 is the one that changes the submission most.**

---

## B1 · Run a real incident analysis in Bob, using our MCP server

**~45 min · This is the highest-value hour left in the project.**

Right now the story is "IBM Bob is the reasoning layer" with no observed
instance of Bob reasoning. This closes that — and it does **not** depend on the
unverified `cloud.manufact.com` REST endpoint, which is the thing that might
never work.

`.bob/mcp.json` is already committed and already correct. When you open this
repository as a workspace, Bob launches our evidence server itself:

```
python -m mcp_server.server --profile evidence
```

I smoke-tested that exact command this session — it starts clean under the
profile and serves eight read-only tools.

### Do this

1. **Open the repo as a Bob workspace.**
   `C:\Users\shivraj\Desktop\Devops\Kubemedic`
2. **Confirm the MCP server connected.** Bob should list the
   `kubemedic-evidence` server with these tools and no others:
   `get_workload_status`, `get_pods`, `get_events`, `get_recent_changes`,
   `get_application_health`, `get_workload_snapshot`, `list_tickets`,
   `get_ticket`.
   **Screenshot this.** It is the visual proof of the central safety claim:
   Bob has no tool that can change the cluster.
3. **Break the cluster for real:**
   ```bash
   bash scripts/inject_incident.sh
   ```
4. **Switch Bob to the `KubeMedic Analyst` mode** and ask it to work the
   incident. Suggested prompt:

   > Use the incident-correlation skill. Call the kubemedic-evidence MCP tools
   > to collect evidence for deployment `ticket-booking` in namespace
   > `opspilot` — workload status, pods, events, recent changes and application
   > health. Correlate the open tickets into one incident, give me ranked
   > hypotheses with confidence and the evidence for and against each, a root
   > cause labelled as an inference, and one recommended action from
   > rollback_deployment, restart_deployment or scale_workload.

5. **Watch it call the tools.** That is Bob using purpose-built MCP tooling
   against a real cluster, live.
6. **Screenshot or record the whole exchange.**
7. Reset when done: `bash scripts/reset_healthy.sh`

### Why this matters more than fixing the REST path

The rules ask for a *"credible or feasible use"* — a judge watching Bob call
your own MCP evidence tools and reason over real cluster state is credible in a
way no amount of code is. It also produces the session that `B2` has to export,
and the footage `06_DEMO_SCRIPT.md` needs.

If the REST path lands too, better still — but this stands on its own, and it
is not blocked on an endpoint nobody has confirmed.

---

## B2 · Export the session report — **required deliverable (`SUB-003`)**

**~30 min.** ENTRY REQUIREMENTS, deliverable 4, verbatim:

> "...including **exported IBM Bob report of all relevant tasks/sessions used
> for the contest**"

Export **every** contest session, not just B1: the asset-pack work, the
consolidation sessions in `KubeMedic Dev`, any audit sessions. Save into
`submission/bob-report/`.

Full procedure and a README template are in
[`02_BOB_REPORT_EXPORT.md`](02_BOB_REPORT_EXPORT.md).

**If Bob has no export function**, capture screenshots of the session list and
of representative sessions, and say so plainly in the README. A labelled
best-effort export beats a missing deliverable — and beats a fabricated one.

> Check the export for pasted keys and absolute local paths before committing.
> `AGENTS.md` calls this out specifically.

---

## B3 · Get the API credentials — `BOB-001`

**~15 min, if they exist.** From the IBM Bob cloud console:

```
KUBEMEDIC_BOB_API_KEY=...
KUBEMEDIC_BOB_AGENT_ID=...
```

Put them in `.env` (never commit it), then:

```bash
bash scripts/validate.sh
```

It will assert `analysis_source == "ibm-bob"` and exercise the real revision
loop. Save the resulting `records/*.json` into `submission/evidence/`.

**Stop rule: if this is not working by ~11:00 IST, stop.** B1 already gives you
a demonstrable Bob integration. Do not spend the morning on an endpoint that
may not be the sanctioned one — confirm `cloud.manufact.com` against IBM Bob's
own documentation before debugging it at all.

---

## B4 · Prove the asset pack actually loads

**~10 min.** `.bob/` is real work and a judge will look at it, but only if it
demonstrably functions.

In Bob, confirm and screenshot:

| Asset | Expect |
|---|---|
| Modes | `KubeMedic Analyst`, `KubeMedic Architect`, `KubeMedic Dev`, `KubeMedic Auditor` |
| Skills (7) | `incident-correlation`, `remediation-planning`, `verification-review`, `runbook-bad-rollout`, `track-consolidation`, `submission-audit`, `gemini-audit` |
| Personas (6) | pod state, events, change history, health, ticket, provider auditor |
| Rules | `AGENTS.md` loaded, plus the per-mode rule files |

If a mode or skill does not appear, fix the file or drop the claim from
`SUB-002`. Claiming assets that do not load is the kind of thing an auditor
catches.

---

## B5 · Run the auditor against your own submission

**~20 min. Optional, high value if there is time.**

You already have a `submission-audit` skill and a `KubeMedic Auditor` mode
built for exactly this. Switch to that mode and ask it to audit the repository
against the Official Rules before you submit.

Two things happen: you may catch a real gap, and the session itself becomes
evidence in the Bob report that Bob was used adversarially on your own work —
which is a genuinely good story for the "how Bob was used" statement.

---

## Order, with the deadline in mind

```
tonight   B3 (ask Ramana for the keys — the message can wait for them)
morning   B1  ← do this first, it is the one that changes the submission
          B4  (10 min, while Bob is already open)
          B2  (export everything, including B1's session)
          B3  (only if the keys arrived; hard stop 11:00 IST)
midday    B5  (if time)
```

**If you only do one thing in Bob: B1.** It converts "the architecture puts
IBM Bob at the centre" from a design claim into something a judge watched
happen.

---

## What not to do

- **Do not reconstruct sessions that did not occur** to fill out the report.
  The rules have a good-faith clause, and a fabricated session log is exactly
  what it is for.
- **Do not claim in `SUB-002` that Bob produced a runtime analysis** unless B1
  or B3 actually happened. `SUB-002` ships two variants for this reason.
- **Do not paste credentials into a Bob chat.** They end up in the exported
  session.
