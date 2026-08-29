# 06 — Agent Reasoning Flow

## The target separation (from `AGENTS.md`)

```
MCP        deterministic evidence and tools     "what is happening"
IBM Bob    reasoning, correlation, planning     "what does this mean"
Executor   controlled deterministic mutation    "is this action permitted"
Human      authorisation and control            "should this happen at all"
Verifier   independent recovery evidence        "did it actually work"
```

## Ownership as implemented

| Responsibility | Owner in code | Correct layer? |
|---|---|---|
| Observation | `orchestrator/evidence.py` via `mcp_server/tools.py` | **Yes** |
| Anomaly detection | `mcp_server/watcher.py` — threshold rules | **Yes** (deterministic, not reasoning) |
| Correlation | `agent/correlation.py` — deterministic Python | **Disputed** — see below |
| Correlation (again) | Requested from Bob in `PROMPT_TEMPLATE` | **Duplicated** |
| Hypothesis | Bob, parsed into `BobAnalysis.hypotheses` | **Yes** |
| Root cause | Bob, parsed into `BobAnalysis.root_cause` | **Yes** |
| Action selection | Bob, constrained to `AllowedAction` | **Yes** |
| Plan construction | `RemediationPlan.from_analysis()` — mechanical copy | **Yes** |
| Human decision | `agent/audit.py:record_decision()` | **Yes** in `agent/`; **violated** by `dashboard/app.py` |
| Execution | `agent/executor.py` | **Yes** |
| Verification | `agent/verification.py` | **Yes** in `agent/`; **violated** by `dashboard/app.py` |

---

## Violation 1 — correlation is done twice

`agent/correlation.py` computes a `CorrelationResult` deterministically:
workload-name match, a two-hour time window, and a symptom-keyword regex, with
a ticket joining at 2 of 3 signals. Its module docstring is explicit:

> This is deterministic Python logic, not an LLM call. Bob receives the
> correlated evidence; it does not perform the correlation.

But `agent/bob.py:PROMPT_TEMPLATE` sends `<open_tickets>` and asks Bob to
"Analyze this Kubernetes incident using the incident-correlation skill", and
`BobAnalysis` carries its own `correlation: CorrelationResult | None`.

So per incident there are two correlation results:

- `incident.correlation` — from Python, always set.
- `incident.analysis.correlation` — from Bob, may be set.

Nothing compares or reconciles them. `IncidentRecord.correlation` persists the
**Python** one; `IncidentRecord.bob_analysis` persists the Bob one inside the
analysis snapshot. If they disagree, the record contains both and says nothing
about the conflict.

**This matters for judging.** The many-to-one correlation is the project's
headline innovation. If a judge asks "who decided these three tickets are one
incident?", the honest answer today is "a regex, and also Bob, and we do not
reconcile them."

**Options, none yet chosen — see `21_DECISIONS.md` ADR-007:**

- **(a)** Python correlates; Bob is told the grouping and only reasons about
  cause. Removes the duplicate, weakens the "Bob correlates" claim.
- **(b)** Python pre-filters to plausible candidates; Bob makes the final
  grouping call and must justify it. Keeps the claim, costs a prompt change.
- **(c)** Keep both and record agreement/disagreement explicitly as a
  confidence signal. Most honest, most work.

Recommendation: **(b)**, because the demo narrative is "Bob understood that
three symptoms were one problem", and (b) is the only option where that
sentence is literally true.

---

## Violation 2 — the dashboard bypasses every layer

`dashboard/app.py` performs observation (fabricated), correlation
(hardcoded `_MASTER_INCIDENTS`), reasoning (hand-written `correlation.summary`
strings), execution (claimed, never performed) and verification (six checks
whose result is the `approved` boolean). It is every layer at once and none of
them honestly. P0-1.

---

## Reasoning call contract

**Request.** `analyze(evidence: dict, tickets: list[dict]) -> BobResult`.
Transport: two HTTPS POSTs — create a chat, then execute. Auth: `x-api-key`.
Timeout: `KUBEMEDIC_BOB_TIMEOUT_SECONDS`, default 180.

**Response handling.** `_extract_json` tries, in order: the whole payload as
JSON; a known envelope key (`result`, `response`, `output`, `content`, `text`);
then `_last_object`, which scans for the last balanced top-level JSON object
containing `hypotheses` or `status`, correctly skipping braces inside strings.
This is defensive parsing for a model that may wrap or fence its output.

**Validation.** `BobAnalysis.from_raw` rejects any `recommended_action`
outside the allowlist *before* pydantic validation, and a model validator
requires `action_target` whenever an action is present.

**Failure policy — the strongest property in the system.** Every failure path
converges on `analysis_source="unavailable"`:

| Failure | Result |
|---|---|
| No API key | `bob_unavailable` |
| No agent id | `bob_unavailable` |
| HTTP 401 | `bob_unavailable`, message names the key |
| Any HTTP error | `bob_unavailable` with status and truncated body |
| Timeout / network | `bob_unavailable` |
| Unparseable output | `bob_unavailable` |
| Schema validation failure | `bob_unavailable` |

The incident then stops before a plan is built. Covered by
`test_analyze_no_key_returns_unavailable`,
`test_reasoning_on_bob_unavailable_does_not_fabricate`,
`test_reasoning_on_malformed_output_does_not_fabricate`,
`test_bob_unavailable_stops_pipeline`.

**Secret handling.** `_redact()` truncates any argv element over 120
characters so the prompt (which carries cluster detail) is never logged. The
API key is only ever placed in a header, never in `invocation`.

---

## The reasoning loop that does not exist

```
                   Proposed remediation
                           |
                    Human Final Review
                    /                \
              APPROVE                REJECT
                 |                      |
              Execute            feedback required   <-- enforced by HumanDecision
                 |                      |
          Independent verify     persist feedback    <-- done, in audit_log + record
                 |                      |
              Resolve            add to Bob context  <-- MISSING
                                        |
                                   revised plan      <-- MISSING
                                        |
                                 Human Final Review  <-- MISSING (no loop back)
```

Everything above the dashed line is implemented and tested. Everything below
`persist feedback` does not exist. `run_full_pipeline` returns as soon as the
state reaches `REJECTED` or `FEEDBACK_RECORDED`.

Implementing it requires, at minimum:

1. A `feedback_history: list[str]` on `Incident` (or reuse `audit_log`).
2. A `<human_feedback>` section in `PROMPT_TEMPLATE`.
3. A `previous_feedback` parameter threaded through `run_analysis()` into
   `analyze()`.
4. A legal transition `FEEDBACK_RECORDED -> ANALYSED` — note that
   `record_decision()` currently only accepts `{ANALYSED, PENDING_APPROVAL}`,
   which happens to permit re-review after re-analysis.
5. A revision counter, so an unbounded reject/revise loop cannot spin.

`_ILLEGAL_TRANSITIONS` already blocks `FEEDBACK_RECORDED -> EXECUTING`, so
adding the loop cannot accidentally create a path from rejection to execution.
That guard is what makes this change safe to attempt. See task `REVIEW-002`.
