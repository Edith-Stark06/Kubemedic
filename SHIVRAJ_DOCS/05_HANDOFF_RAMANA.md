# Handoff → Ramana

Your consolidation held up. Everything built on top of it this session —
adapters, live client, API, review loop — needed no changes to `agent/models.py`
contracts beyond adding `feedback_history` and `revision_count`.

Three things are yours now, and the first one is the only remaining blocker on
the whole submission.

---

## 1. `BOB-001` — get one real Bob analysis · **P0, blocks everything**

**IBM Bob has never returned a live analysis.** Every run produces
`analysis_source: "unavailable"`. The theme is *"Build with purpose using IBM
Bob 2.0"*, and the rules let Sponsors disqualify a submission that does not
show a credible or feasible use of watsonx. This is the gap.

### What is needed

```bash
# in .env — never commit this file
KUBEMEDIC_BOB_API_KEY=<from the IBM Bob cloud console>
KUBEMEDIC_BOB_AGENT_ID=<agent id>
KUBEMEDIC_BOB_API_BASE=https://cloud.manufact.com
```

### Verify in one command

```bash
python -c "
from agent.bob import analyze
r = analyze({'deployment_name':'ticket-booking','pod_states':[]}, [])
print('ok:', r.ok, '| error:', r.error)
print('analysis:', r.analysis)
"
```

`ok: True` means it works. Then:

```bash
bash scripts/validate.sh
```

With keys present it asserts `analysis_source == "ibm-bob"` and exercises the
real revision loop instead of substituting an operator plan. **Save the
resulting `records/*.json` — that file is the single best piece of evidence in
the whole submission.** Copy it to `submission/evidence/`.

### The open question, and please answer it before sinking hours in

`agent/bob.py` posts to `https://cloud.manufact.com/api/v1/chats`. Your commit
`26aa0b8` says the protocol came from the IDE extension's `RemoteAgent` class.
**Nothing in the repository establishes that this is the sanctioned IBM Bob API
for the contest.** If it is not, no amount of debugging will help.

Check it against IBM Bob's own documentation or the hackathon guide *first*.

### The stop rule

**If you cannot get a live analysis by ~11:00 IST, stop and tell Shivraj.**
The submission then gets written around what is true. That is a worse outcome
than Bob working, and a far better one than missing the deadline chasing an
endpoint that may not be ours. `SUB-002` already has a draft for both cases.

---

## 2. `SUB-001` and `SUB-002` — the written statements · P0

Drafts are in `SHIVRAJ_DOCS/`. They need your review, not a rewrite.

- `SUB-001_PROBLEM_AND_SOLUTION.md` — ready; check the framing is what you want
- `SUB-002_HOW_WE_USED_IBM_BOB.md` — **has two variants**, one for Bob working
  and one for Bob unavailable. Pick after `BOB-001` resolves. Do not soften the
  second variant if that is the one that applies.

---

## 3. `ADR-007` — who owns correlation? · P2, but a judge will ask

`agent/correlation.py` correlates deterministically in Python, and its
docstring says *"Bob receives the correlated evidence; it does not perform the
correlation."* But `PROMPT_TEMPLATE` asks Bob to use the `incident-correlation`
skill, and `BobAnalysis.correlation` holds Bob's own result. Two correlations
are produced per incident and nothing reconciles them.

It matters because the demo line is "Bob understood that three symptoms were
one problem". Right now the honest answer to *"who decided these tickets are
one incident?"* is "a regex, and also Bob, and we don't compare them."

Options are in `docs/21_DECISIONS.md` ADR-007. With the time left, the cheapest
honest fix is a sentence in `SUB-002` and the video: *"deterministic correlation
groups the candidates; Bob confirms the grouping and explains the causal link."*
That is true of what the code does today.

---

## What changed under you

`agent/models.py` gained `feedback_history: list[str]`, `revision_count: int`
and `MAX_REVISIONS = 3`. `IncidentRecord` carries both.

`agent/bob.py` gained `build_prompt(evidence, tickets, feedback=None)` and a
`FEEDBACK_BLOCK`; `analyze()` takes an optional `feedback` argument.

`agent/reasoning.py` passes `incident.feedback_history` through.
`agent/audit.py` appends the rejection reason to it.
`agent/pipeline.py` gained `request_revision()`.

Nothing was weakened. `_ILLEGAL_TRANSITIONS` still blocks
`FEEDBACK_RECORDED → EXECUTING`, `require_approval()` still gates the executor,
and `TestTheLoopCannotReachTheCluster` asserts the new loop opened no path from
a rejection to the cluster.

New modules in your lane: `agent/k8s_client.py` (the only module that changes a
cluster), `agent/adapters.py`, `agent/api.py`.

---

## Paste into chat

```
Ramana — everything is done except one thing, and it's yours.

IBM Bob has never returned a live analysis. Every run says
analysis_source: "unavailable". That's the last blocker on the whole entry.

Need in .env (don't commit):
  KUBEMEDIC_BOB_API_KEY=...
  KUBEMEDIC_BOB_AGENT_ID=...

Check with:
  python -c "from agent.bob import analyze; r=analyze({'deployment_name':'ticket-booking','pod_states':[]},[]); print(r.ok, r.error)"

Then: bash scripts/validate.sh  → asserts analysis_source == "ibm-bob" and
runs the real revision loop. Save the records/*.json it writes, that's our
best evidence.

First though — please confirm cloud.manufact.com is actually the sanctioned
IBM Bob API. Your commit says it came from the extension's RemoteAgent class,
but nothing proves it's the contest endpoint. If it isn't, debugging won't help.

Stop rule: if no live analysis by ~11:00 IST, tell me and we write the
submission around what's true. Draft covers both cases.

Also yours: SUB-001 and SUB-002 drafts in SHIVRAJ_DOCS/ — review, don't rewrite.

Your consolidation held up completely. The API, adapters, live k8s client and
review loop all built on it without changing your contracts.

Details: SHIVRAJ_DOCS/05_HANDOFF_RAMANA.md
```
