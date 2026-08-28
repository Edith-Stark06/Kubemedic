# Analyst output contract

`agent/reasoning.py` parses this. Field names are frozen — if you need a
change, change it here and in the Pydantic model in the same commit.

## Success shape

```json
{
  "schema_version": "1.0",
  "analysis_source": "ibm-bob",
  "correlation": {
    "master_incident_id": "INC-501",
    "member_tickets": ["TICKET-101", "TICKET-102", "TICKET-103"],
    "excluded_tickets": [],
    "correlation_basis": [
      "all three reference deployment/ticket-booking",
      "all onset within 4 minutes of first Warning event at 09:38:12Z",
      "a stalled rollout is the known upstream cause of the readiness failures in TICKET-102 and the intermittent 5xx in TICKET-103"
    ],
    "rationale": "One deployment regression presenting as three symptoms."
  },
  "timeline": [
    {"t": "09:37:04Z", "event": "rollout of revision 4 begins", "source": "rollout_history"},
    {"t": "09:38:12Z", "event": "Warning Unhealthy on ticket-booking-7f4-abc", "source": "events"},
    {"t": "09:41:30Z", "event": "TICKET-101 filed", "source": "tickets"}
  ],
  "hypotheses": [
    {
      "rank": 1,
      "statement": "Revision 4 of deployment/ticket-booking ships an image whose containers never pass the readiness probe, stalling the rollout.",
      "confidence": "high",
      "confidence_reason": "Corroborated by three independent sources — rollout history, pod readiness, and cluster events — with no contradicting signal.",
      "supporting_evidence": [
        "rollout revision 4 created 09:37:04Z, immediately before first symptom",
        "pods ticket-booking-7f4-abc and -def report 0/1 Ready on image ticket-booking:1.1",
        "event Warning/Unhealthy, readiness probe failed, first seen 09:38:12Z"
      ],
      "contradicting_evidence": ["none found in available evidence"],
      "cheapest_next_check": "Compare the container image on the not-ready pods against revision 3's pod template."
    },
    {
      "rank": 2,
      "statement": "A transient node-level resource shortage is delaying readiness.",
      "confidence": "low",
      "confidence_reason": "Timing fits, but no FailedScheduling or eviction events, and old pods on the same nodes remain healthy.",
      "supporting_evidence": ["symptom onset is clustered in time"],
      "contradicting_evidence": [
        "no FailedScheduling or Evicted events in the window",
        "revision 3 pods on the same nodes remain 1/1 Ready"
      ],
      "cheapest_next_check": "Check node conditions and pod scheduling events."
    }
  ],
  "root_cause": {
    "statement": "Deployment revision 4 introduced a regression that prevents container readiness.",
    "confidence": "high",
    "is_inference": true
  },
  "dual_signal_note": "Kubernetes rollout is DEGRADED while application health returns 200, because revision 3 pods are still serving traffic. Either signal alone would be misleading.",
  "recommended_action": "rollback_deployment",
  "action_target": "ticket-booking",
  "action_parameters": {"to_revision": 3},
  "reason": "Rollback restores the last revision with confirmed passing readiness. It is the smallest reversible action that addresses the identified cause.",
  "risk_explanation": "Medium. Rolling back discards revision 4 entirely, including any intended change in it. If revision 4 carried a needed fix, that fix is lost until it is reshipped.",
  "requires_human_approval": true,
  "notes_for_reviewer": "If revision 4 was a deliberate maintenance rollout, reject this and say so — the rejection reason will be recorded against the incident."
}
```

## Evidence-unavailable shape

Return this rather than guessing. `agent/reasoning.py` treats it as a hard
stop and the dashboard shows "Evidence collection failed".

```json
{
  "schema_version": "1.0",
  "analysis_source": "ibm-bob",
  "status": "evidence_unavailable",
  "missing_signals": ["get_workload_snapshot returned error: connection refused"],
  "partial_evidence": ["tickets retrieved successfully"],
  "hypotheses": [],
  "recommended_action": null,
  "requires_human_approval": true,
  "reason": "Cluster evidence could not be collected. No diagnosis is offered."
}
```

## Allowlisted actions

`recommended_action` must be one of exactly these, or `null`:

| Action | Parameters | Reversible |
|---|---|---|
| `rollback_deployment` | `to_revision` (int, optional) | Yes |
| `restart_deployment` | none | Yes |
| `scale_workload` | `replicas` (int) | Yes |

Any other value is rejected by the executor as an invalid action. If none of
these fits the diagnosis, return `null` and explain what a human should do
instead. **A null recommendation with a good explanation is a correct answer**,
and it is a far better demo moment than a confident wrong one.
