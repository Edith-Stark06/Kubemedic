# KubeMedic — 3-Minute Demo Video Script

**Hard limit:** 3:00
**Live solution on screen:** 1:30 – 3:00 (90 s minimum)
**Evidence files:** `INC-20260926T213503-001.json`, `validate-run-runbook.txt`

---

## Pre-roll checklist (not filmed)

- Terminal A: `python -m agent.api` running, console at `http://127.0.0.1:8100/ui/`
- Terminal B: ready at repo root
- Browser tab 1: operator console `/ui/` showing no open incidents
- Browser tab 2: `submission/evidence/INC-20260926T213503-001.json` open in an editor
- Font size: 18 px terminal, 16 px browser — legible at 1080p
- Resolution: 1920 × 1080, 30 fps

---

## Shot-by-shot

### 0:00 – 0:20 | THE PROBLEM

**On screen:** Title card with the KubeMedic logo, then a split showing a Kubernetes rollout stalled at `2/3 ready`, and two separate tickets side by side — one about a stalled rollout, one about a pod not ready.

**Narration:**
> "A bad deployment arrives as three separate alerts at once: a stalled rollout, a pod that won't become ready, a checkout page returning errors. Someone has to recognise these as one incident, work out the cause, and decide what to do — at a bad hour, under pressure.
> Most teams won't let a model just fix it. A model can be confidently wrong, and it can't prove the fix worked."

### 0:20 – 0:35 | THE ARCHITECTURE IN ONE SENTENCE

**On screen:** The ASCII flow diagram from `README.md`. Highlight in sequence: **MCP evidence → IBM Bob → human final review → bounded execution → independent verification**.

**Narration:**
> "KubeMedic makes the reasoning fast and the acting bounded. A read-only MCP server collects evidence. IBM Bob 2.0 correlates the symptoms and proposes a remediation. A human decides. Only then does a single allowlisted action execute — and we re-read the cluster independently to confirm recovery."

### 0:35 – 0:52 | INJECT THE FAULT

**On screen:** Terminal:
```
kubectl set image deployment/ticket-booking ticket-booking=ticketbooking:1.1 -n opspilot
kubectl -n opspilot get pods -w
```
Watch the rollout stall at `2/3 Ready`; the new pod shows `0/1 Ready`.

**Narration:**
> "We push a bad image — ticketbooking:1.1. Its readiness probe returns HTTP 500. The rolling update stalls: old pods keep serving because maxUnavailable is zero, the new pod never becomes ready. The service is degraded, not down."

### 0:52 – 1:10 | WATCHER FILES TICKETS → CORRELATION → IBM BOB INVOKED

**On screen:** Operator console (`/ui/`). Two tickets appear (`Rollout stalled`, `Pod not ready`) merging into one incident. Reasoning spinner appears. Cut to `validate-run-runbook.txt` steps 4–6 scrolling:
```
[PASS] at least one ticket filed :: 2 created
[PASS] every open ticket joined the incident :: 2 members, 0 excluded
[PASS] one master incident id :: INC-20260926T213503-001
[PASS] Bob produced an analysis
[PASS] a plan was proposed :: rollback_deployment
```

**Narration:**
> "The watcher files two tickets. The correlator collapses them into one incident. IBM Bob receives the MCP evidence — rollout history, pod states, readiness events, application health — and produces a ranked analysis."

### 1:10 – 1:35 | BOB'S ANALYSIS — RUNBOOK CITATION

**On screen:** Operator console, expanded incident view. Highlight the `root_cause` (labelled **inference**), then zoom on the `reason` field:

> *"The playbook explicitly names this failure class (Failure Class 1: readiness regression immediately following a deployment) and mandates rollback_deployment rather than restart_deployment, because a restart would recreate pods on the same broken image."*

Inset: `docs/RUNBOOK_TICKET_BOOKING.md` open, showing the Failure Class 1 entry.

**Narration:**
> "Bob's reasoning cites our operational runbook by name and rule. It knows to prefer rollback over restart — a restart would recreate pods on the same broken image. The root cause is labelled as inference, not fact. This is document understanding against a real playbook we wrote."

### 1:35 – 1:55 | HUMAN REJECTS — BOB REVISES

**On screen:** Console shows `PENDING_APPROVAL`. Click **Reject**, type: *"Confirm the rollout history names a healthy revision before acting."* Console shows `FEEDBACK_RECORDED`, then a revised plan. Cut to `validate-run-runbook.txt` steps 8–9:
```
[PASS] rejection without a reason refused
[PASS] incident recorded the rejection :: FEEDBACK_RECORDED
[PASS] the reason was stored
[PASS] a rejected plan never reached the cluster :: ticketbooking:1.1
[PASS] a revised plan was produced
[PASS] the revision is awaiting review :: PENDING_APPROVAL
```

**Narration:**
> "The reviewer rejects the plan with a mandatory reason — rejecting without one returns HTTP 400, because the reason is what Bob needs to revise. Nothing executes. Bob is called again with the feedback."

### 1:55 – 2:15 | APPROVE AND EXECUTE THE REAL ROLLBACK

**On screen:** Click **Approve**. Console: `APPROVED` → `EXECUTING`. Terminal:
```
[PASS] execution succeeded :: rollback_deployment on ticket-booking succeeded
  'from_revision': '4', 'to_revision': '3', 'image': 'ticketbooking:1.0'
  'restored': 'full pod template'
```
Cut to `kubectl -n opspilot get pods` — the 1.1 pod terminating, three 1.0 pods `1/1 Ready`.

**Narration:**
> "After approval the executor calls the Kubernetes API directly — no shell, no model-composed command. The rollback restores the full pod template to revision three, not just the image tag."

### 2:15 – 2:30 | INDEPENDENT VERIFICATION — TWO SIGNALS

**On screen:** Console: `RESOLVED`. Zoom on:
```
rollout_healthy:  PASS — ready=True, updated=2, desired=2
health_endpoint:  PASS — status_code=200, healthy=True
```

**Narration:**
> "Recovery is not the API's own reply. The verifier re-reads the cluster on two independent signals. During the incident the health endpoint was already returning 200, because old pods kept serving — only the rollout signal caught the failure. You need both."

### 2:30 – 2:50 | HOW IBM BOB WAS USED — AUDIT AND A REJECTED FINDING

**On screen:** Split view — `INC-20260926T213503-001.json` showing `"analysis_source": "ibm-bob"`, next to `submission/HOW_WE_USED_IBM_BOB.md`'s paragraph on the security audit.

**Narration:**
> "We also ran Bob adversarially, as a security auditor, against our own code. It proposed scoping our audit hash chain per incident. We wrote a test first: the proposed change would have let an attacker forge one incident's history in isolation — the opposite of the intent. We kept the design. Verifying a plausible but wrong recommendation before acting on it is the same discipline we ask of the reasoning engine itself."

### 2:50 – 3:00 | CLOSE

**On screen:** The resolved incident, audit log visible. Title card:
```
KubeMedic
Evidence-driven Kubernetes incident response, with a human in the loop.
470 tests · live IBM Bob run · human gate enforced
github.com/Edith-Stark06/Kubemedic
```

**Narration:**
> "Evidence. Reasoning. A mandatory human decision. Bounded execution. Independent verification. KubeMedic doesn't fix your cluster. It makes the evidence clear, keeps a human accountable, and proves the fix worked."

---

## Timing summary

| Range | Content | Duration |
|---|---|---|
| 0:00 – 0:20 | Problem statement | 20 s |
| 0:20 – 0:35 | Architecture overview | 15 s |
| 0:35 – 0:52 | Fault injection | 17 s |
| 0:52 – 1:10 | Tickets, correlation, Bob invoked | 18 s |
| 1:10 – 1:35 | Bob's analysis + runbook citation | 25 s |
| 1:35 – 1:55 | Human rejects, Bob revises | 20 s |
| 1:55 – 2:15 | Approve, real rollback executes | 20 s |
| 2:15 – 2:30 | Independent verification, RESOLVED | 15 s |
| 2:30 – 2:50 | How Bob was used / audit finding | 20 s |
| 2:50 – 3:00 | Close | 10 s |
| **Total** | | **3:00** |

Live solution on screen (0:35 – 3:00): **145 s** — above the 90s minimum.

## Evidence to have on screen (verified against the committed files)

| Shot | File | What to show |
|---|---|---|
| Stalled rollout | live `kubectl get pods -w` | `2/3 Ready`, bad pod `0/1 Ready` |
| Validate harness output | `submission/evidence/validate-run-runbook.txt` | Steps 4–13, `[PASS]` lines |
| Bob's runbook citation | `submission/evidence/INC-20260926T213503-001.json` | The `reason` field |
| Runbook document | `docs/RUNBOOK_TICKET_BOOKING.md` | Failure Class 1 entry |
| Rejection in audit log | `INC-20260926T213503-001.json` line 151 | `decision: rejected`, the feedback text |
| Execution result | `validate-run-runbook.txt` | `from_revision: 4, to_revision: 3, restored: full pod template` |
| Two-signal verification | `validate-run-runbook.txt` | Both signals `passed=True` |
| Analysis source | `INC-20260926T213503-001.json` line 25 | `"analysis_source": "ibm-bob"` |
| Security-audit rejection | `submission/HOW_WE_USED_IBM_BOB.md` | The hash-chain finding and why it was rejected |

---

*Drafted by IBM Bob (`kubemedic-architect` mode, task `3e325ae33be0b60ba1ebc25330b8f83c`, cost 0.457) from the repository's own README, submission statements, and the live-run evidence file. The `duration_ms` and line-number citations above were checked against the committed JSON before this file was saved.*
