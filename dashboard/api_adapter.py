"""
API Adapter — the single seam between the dashboard and Ramana's agent backend.

When KUBEMEDIC_AGENT_BASE_URL is set, all calls forward to that real HTTP API.
When it is absent (local dev / demo without backend), the mock provider is used.

To wire up Ramana's backend once it ships:
    export KUBEMEDIC_AGENT_BASE_URL=http://localhost:8000

Expected agent endpoints (to be implemented by Ramana):
    GET  /incidents                          → list[Incident summary]
    GET  /incidents/{id}                     → full Incident JSON
    POST /incidents/{id}/decision            → updated Incident JSON
         body: { decision, approver, feedback }

The dashboard never calls anything else. All mutation goes through
/incidents/{id}/decision with a HumanDecision payload.
"""
from __future__ import annotations

import os
from typing import Any

import httpx

AGENT_BASE = os.getenv("KUBEMEDIC_AGENT_BASE_URL", "").rstrip("/")


def get_adapter() -> "RealAdapter | MockAdapter":
    if AGENT_BASE:
        return RealAdapter(AGENT_BASE)
    return MockAdapter()


# ---------------------------------------------------------------------------
# Real adapter — forwards to Ramana's HTTP API
# ---------------------------------------------------------------------------

class RealAdapter:
    def __init__(self, base_url: str) -> None:
        self.base = base_url

    async def list_incidents(self) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=10) as client:
            r = client.get(f"{self.base}/incidents")
            r.raise_for_status()
            return r.json()

    async def get_incident(self, incident_id: str) -> dict[str, Any] | None:
        async with httpx.AsyncClient(timeout=10) as client:
            r = client.get(f"{self.base}/incidents/{incident_id}")
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.json()

    async def record_decision(
        self,
        incident_id: str,
        decision: str,
        approver: str,
        feedback: str | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "decision": decision,
            "approver": approver,
            "feedback": feedback,
        }
        async with httpx.AsyncClient(timeout=10) as client:
            r = client.post(
                f"{self.base}/incidents/{incident_id}/decision",
                json=payload,
            )
            r.raise_for_status()
            return r.json()


# ---------------------------------------------------------------------------
# Mock adapter — used for local UI development before Ramana's API lands.
# Returns realistic fixture data shaped exactly like agent/models.py output.
# ---------------------------------------------------------------------------

_MOCK_INCIDENTS: dict[str, dict[str, Any]] = {
    "INC-501": {
        "incident_id": "INC-501",
        "state": "PENDING_APPROVAL",
        "created_at": "2026-08-30T09:37:00Z",
        "updated_at": "2026-08-30T09:42:05Z",
        "tickets": [
            {
                "ticket_id": "TICKET-101",
                "title": "Pods not starting after deploy",
                "reported_symptom": "New pods stuck in Pending, readiness probe failing since 09:38",
                "named_workload": "ticket-booking",
                "created_at": "2026-08-30T09:41:30Z",
                "severity": "high",
            },
            {
                "ticket_id": "TICKET-102",
                "title": "Checkout returning 503",
                "reported_symptom": "Intermittent 503 on /checkout since deploy, affecting ~30% of requests",
                "named_workload": "ticket-booking",
                "created_at": "2026-08-30T09:42:10Z",
                "severity": "high",
            },
            {
                "ticket_id": "TICKET-103",
                "title": "Booking page blank for some users",
                "reported_symptom": "Blank page on /book for users routed to new pods",
                "named_workload": "ticket-booking",
                "created_at": "2026-08-30T09:43:00Z",
                "severity": "medium",
            },
        ],
        "evidence": {
            "collected_at": "2026-08-30T09:40:00Z",
            "deployment_name": "ticket-booking",
            "namespace": "kubemedic",
            "pod_states": [
                {
                    "name": "ticket-booking-7f4-abc",
                    "ready": "0/1",
                    "status": "Running",
                    "image": "ticket-booking:1.1",
                    "restarts": 0,
                },
                {
                    "name": "ticket-booking-7f4-def",
                    "ready": "0/1",
                    "status": "Running",
                    "image": "ticket-booking:1.1",
                    "restarts": 0,
                },
                {
                    "name": "ticket-booking-6c3-old",
                    "ready": "1/1",
                    "status": "Running",
                    "image": "ticket-booking:1.0",
                    "restarts": 0,
                },
            ],
            "events": [
                {
                    "type": "Warning",
                    "reason": "Unhealthy",
                    "message": "Readiness probe failed: HTTP probe failed with statuscode: 500",
                    "first_seen": "2026-08-30T09:38:12Z",
                    "last_seen": "2026-08-30T09:40:55Z",
                    "count": 14,
                }
            ],
            "rollout_history": [
                {
                    "revision": 4,
                    "image": "ticket-booking:1.1",
                    "created_at": "2026-08-30T09:37:04Z",
                    "change_cause": "Deploy v1.1 hotfix",
                },
                {
                    "revision": 3,
                    "image": "ticket-booking:1.0",
                    "created_at": "2026-08-29T14:00:00Z",
                    "change_cause": "Release v1.0",
                },
            ],
            "application_health": {
                "status_code": 200,
                "healthy": True,
                "note": "Old revision pods still serving — rollout stalled with maxUnavailable: 0",
            },
        },
        "correlation": {
            "master_incident_id": "INC-501",
            "member_tickets": ["TICKET-101", "TICKET-102", "TICKET-103"],
            "excluded_tickets": [],
            "correlation_basis": [
                "All three tickets reference deployment/ticket-booking",
                "All onset within 4 minutes of first Warning event at 09:38:12Z",
                "A stalled rollout is the known upstream cause of the readiness failures in TICKET-102 and the intermittent 5xx in TICKET-103",
            ],
            "rationale": "One deployment regression presenting as three symptoms.",
        },
        "analysis": {
            "schema_version": "1.0",
            "analysis_source": "ibm-bob",
            "status": None,
            "root_cause": {
                "statement": "Deployment revision 4 introduced a regression that prevents container readiness — the new image ticket-booking:1.1 fails its readiness probe on every attempt.",
                "confidence": "high",
                "confidence_reason": "Corroborated by three independent sources — rollout history, pod readiness state, and cluster events — with no contradicting signal.",
                "is_inference": True,
            },
            "hypotheses": [
                {
                    "rank": 1,
                    "statement": "Revision 4 ships an image whose containers never pass the readiness probe, stalling the rollout.",
                    "confidence": "high",
                    "confidence_reason": "Three independent sources agree: rollout history, pod state, cluster events.",
                    "supporting_evidence": [
                        "Rollout revision 4 created 09:37:04Z, immediately before first symptom",
                        "Pods ticket-booking-7f4-abc and -def report 0/1 Ready on image ticket-booking:1.1",
                        "Event Warning/Unhealthy, readiness probe failed, first seen 09:38:12Z",
                    ],
                    "contradicting_evidence": ["none found in available evidence"],
                    "cheapest_next_check": "Compare the container image on the not-ready pods against revision 3's pod template.",
                },
                {
                    "rank": 2,
                    "statement": "A transient node-level resource shortage is delaying readiness.",
                    "confidence": "low",
                    "confidence_reason": "Timing fits, but no FailedScheduling or eviction events, and old pods on the same nodes remain healthy.",
                    "supporting_evidence": ["Symptom onset is clustered in time"],
                    "contradicting_evidence": [
                        "No FailedScheduling or Evicted events in the window",
                        "Revision 3 pods on the same nodes remain 1/1 Ready",
                    ],
                    "cheapest_next_check": "Check node conditions and pod scheduling events.",
                },
            ],
            "dual_signal_note": "Kubernetes rollout is DEGRADED while application health returns 200 OK, because revision 3 pods are still serving traffic with maxUnavailable: 0. Either signal alone would be misleading.",
            "timeline": [
                {"t": "09:37:04Z", "event": "Rollout of revision 4 begins", "source": "rollout_history"},
                {"t": "09:38:12Z", "event": "Warning/Unhealthy — readiness probe failed on ticket-booking-7f4-abc", "source": "events"},
                {"t": "09:41:30Z", "event": "TICKET-101 filed: pods not starting", "source": "tickets"},
                {"t": "09:42:10Z", "event": "TICKET-102 filed: checkout returning 503", "source": "tickets"},
                {"t": "09:43:00Z", "event": "TICKET-103 filed: booking page blank", "source": "tickets"},
            ],
            "recommended_action": "rollback_deployment",
            "action_target": "ticket-booking",
            "action_parameters": {"to_revision": 3},
            "reason": "Rollback restores the last revision with confirmed passing readiness. It is the smallest reversible action that addresses the identified cause.",
            "risk_explanation": "Medium. Rolling back discards revision 4 entirely, including any intended change in it. If revision 4 carried a needed fix, that fix is lost until it is reshipped.",
            "requires_human_approval": True,
            "notes_for_reviewer": "If revision 4 was a deliberate maintenance rollout, reject this and say so — the rejection reason will be recorded against the incident.",
            "missing_signals": [],
            "partial_evidence": [],
        },
        "plan": {
            "action": "rollback_deployment",
            "target": "ticket-booking",
            "action_parameters": {"to_revision": 3},
            "blast_radius": "deployment/ticket-booking — 3 pods, rolling replacement, ~20 seconds of reduced capacity. No other workload in the namespace references it.",
            "risk": "medium",
            "reversible": True,
            "expected_effect": "Revision 3 pods become ready, rollout reports healthy, readiness probe passes, 503s stop.",
            "verification_plan": [
                "Kubernetes rollout reports healthy",
                "All required replicas are Ready",
                "No pod running image ticket-booking:1.1",
                "Application /health returns 200 on a fresh request",
            ],
            "reason": "Rollback restores the last revision with confirmed passing readiness.",
            "risk_explanation": "Medium. Rolling back discards revision 4 entirely, including any intended change in it.",
            "notes_for_reviewer": "If revision 4 was a deliberate maintenance rollout, reject this and say so — the rejection reason will be recorded against the incident.",
        },
        "human_decision": None,
        "execution": None,
        "verification": None,
        "audit_log": [
            {"step": "correlation", "member_tickets": ["TICKET-101", "TICKET-102", "TICKET-103"], "excluded_tickets": [], "timestamp": "2026-08-30T09:40:01Z"},
            {"step": "BOB", "analysis_source": "ibm-bob", "ok": True, "duration_ms": 12340, "timestamp": "2026-08-30T09:42:01Z"},
            {"step": "plan", "action": "rollback_deployment", "target": "ticket-booking", "timestamp": "2026-08-30T09:42:02Z"},
        ],
    },
    "INC-502": {
        "incident_id": "INC-502",
        "state": "RESOLVED",
        "created_at": "2026-08-29T14:10:00Z",
        "updated_at": "2026-08-29T14:25:00Z",
        "tickets": [
            {
                "ticket_id": "TICKET-098",
                "title": "Intermittent 500 on /book",
                "reported_symptom": "Random 500 errors on booking endpoint, ~5% error rate",
                "named_workload": "ticket-booking",
                "created_at": "2026-08-29T14:08:00Z",
                "severity": "medium",
            }
        ],
        "evidence": {
            "collected_at": "2026-08-29T14:12:00Z",
            "deployment_name": "ticket-booking",
            "namespace": "kubemedic",
            "pod_states": [
                {"name": "ticket-booking-6c3-xyz", "ready": "1/1", "status": "Running", "image": "ticket-booking:1.0", "restarts": 3},
            ],
            "events": [],
            "rollout_history": [{"revision": 3, "image": "ticket-booking:1.0", "created_at": "2026-08-29T14:00:00Z", "change_cause": "Release v1.0"}],
            "application_health": {"status_code": 200, "healthy": True},
        },
        "correlation": {
            "master_incident_id": "INC-502",
            "member_tickets": ["TICKET-098"],
            "excluded_tickets": [],
            "correlation_basis": ["Single ticket referencing ticket-booking within incident window"],
            "rationale": "Single-ticket incident.",
        },
        "analysis": {
            "schema_version": "1.0",
            "analysis_source": "ibm-bob",
            "status": None,
            "root_cause": {
                "statement": "Pod restart loop due to memory exhaustion — OOMKill observed 3 times.",
                "confidence": "medium",
                "confidence_reason": "Restart pattern consistent with OOM; no explicit OOMKill event captured but restart count and symptom timing match.",
                "is_inference": True,
            },
            "hypotheses": [
                {
                    "rank": 1,
                    "statement": "Memory exhaustion causing OOMKill and pod restarts.",
                    "confidence": "medium",
                    "confidence_reason": "Restart count and symptom pattern match OOM; no direct OOMKill event in captured window.",
                    "supporting_evidence": ["Pod restart count: 3", "Symptom onset matches restart timestamps"],
                    "contradicting_evidence": ["No explicit OOMKill event captured"],
                    "cheapest_next_check": "Check pod memory limits and recent resource usage metrics.",
                }
            ],
            "dual_signal_note": None,
            "timeline": [
                {"t": "14:08:00Z", "event": "TICKET-098 filed", "source": "tickets"},
                {"t": "14:12:00Z", "event": "Evidence collected", "source": "pipeline"},
            ],
            "recommended_action": "restart_deployment",
            "action_target": "ticket-booking",
            "action_parameters": {},
            "reason": "Restart clears in-memory state. If OOM is the cause, fresh pods with the same limits will stabilise until a longer-term fix is deployed.",
            "risk_explanation": "Low. Restart is fully reversible, brief rolling disruption only.",
            "requires_human_approval": True,
            "notes_for_reviewer": None,
            "missing_signals": [],
            "partial_evidence": [],
        },
        "plan": {
            "action": "restart_deployment",
            "target": "ticket-booking",
            "action_parameters": {},
            "blast_radius": "deployment/ticket-booking — brief rolling restart, <30 seconds total disruption.",
            "risk": "low",
            "reversible": True,
            "expected_effect": "Fresh pods start cleanly, error rate drops to zero, /health returns 200.",
            "verification_plan": [
                "All pods in Running/Ready state",
                "Application /health returns 200",
                "No new 500 errors on /book for 60 seconds",
            ],
            "reason": "Restart clears in-memory state causing OOM-related restarts.",
            "risk_explanation": "Low. Fully reversible, brief rolling disruption only.",
            "notes_for_reviewer": None,
        },
        "human_decision": {
            "decision": "approved",
            "approver": "alice",
            "timestamp": "2026-08-29T14:15:00Z",
            "feedback": None,
        },
        "execution": {
            "action": "restart_deployment",
            "target": "ticket-booking",
            "executed_at": "2026-08-29T14:15:05Z",
            "success": True,
            "message": "restart_deployment on ticket-booking succeeded",
        },
        "verification": {
            "outcome": "PASS",
            "signals": [
                {"name": "rollout_healthy", "passed": True, "detail": "ready=true, updated=3, desired=3"},
                {"name": "health_endpoint", "passed": True, "detail": "status_code=200, healthy=true"},
            ],
            "checked_at": "2026-08-29T14:20:00Z",
            "detail": "Both signals green: rollout healthy and application health OK.",
        },
        "audit_log": [
            {"step": "correlation", "member_tickets": ["TICKET-098"], "excluded_tickets": [], "timestamp": "2026-08-29T14:12:01Z"},
            {"step": "BOB", "analysis_source": "ibm-bob", "ok": True, "duration_ms": 9800, "timestamp": "2026-08-29T14:13:00Z"},
            {"step": "plan", "action": "restart_deployment", "target": "ticket-booking", "timestamp": "2026-08-29T14:13:01Z"},
            {"step": "human_decision", "decision": "approved", "approver": "alice", "timestamp": "2026-08-29T14:15:00Z", "feedback": None},
            {"step": "execute", "action": "restart_deployment", "started_at": "2026-08-29T14:15:05Z", "timestamp": "2026-08-29T14:15:05Z"},
            {"step": "verification", "outcome": "PASS", "signals": [{"name": "rollout_healthy", "passed": True}, {"name": "health_endpoint", "passed": True}], "timestamp": "2026-08-29T14:20:00Z"},
        ],
    },
}


class MockAdapter:
    """
    Local development mock. Returns fixture data shaped exactly like the
    agent/models.py Incident JSON. Replace with RealAdapter by setting
    KUBEMEDIC_AGENT_BASE_URL.
    """

    async def list_incidents(self) -> list[dict[str, Any]]:
        return [
            {
                "incident_id": v["incident_id"],
                "state": v["state"],
                "created_at": v["created_at"],
                "updated_at": v["updated_at"],
                "workload": v.get("evidence", {}).get("deployment_name", "unknown"),
                "ticket_count": len(v.get("tickets", [])),
            }
            for v in _MOCK_INCIDENTS.values()
        ]

    async def get_incident(self, incident_id: str) -> dict[str, Any] | None:
        return _MOCK_INCIDENTS.get(incident_id)

    async def record_decision(
        self,
        incident_id: str,
        decision: str,
        approver: str,
        feedback: str | None,
    ) -> dict[str, Any]:
        import copy
        from datetime import datetime, timezone

        inc = _MOCK_INCIDENTS.get(incident_id)
        if inc is None:
            raise ValueError(f"Incident {incident_id} not found")

        inc = copy.deepcopy(inc)

        ts = datetime.now(timezone.utc).isoformat()

        if decision == "rejected":
            if not (feedback or "").strip():
                raise ValueError("feedback is required when decision is 'rejected'")
            inc["human_decision"] = {
                "decision": "rejected",
                "approver": approver,
                "timestamp": ts,
                "feedback": feedback.strip(),
            }
            inc["state"] = "FEEDBACK_RECORDED"
            inc["execution"] = None  # explicitly: no execution
            inc["audit_log"].append({
                "step": "human_decision",
                "decision": "rejected",
                "approver": approver,
                "timestamp": ts,
                "feedback": feedback,
            })
            inc["audit_log"].append({
                "step": "rejection_recorded",
                "reason": feedback,
                "executed": False,
                "timestamp": ts,
            })
        else:
            inc["human_decision"] = {
                "decision": "approved",
                "approver": approver,
                "timestamp": ts,
                "feedback": None,
            }
            inc["state"] = "APPROVED"
            inc["audit_log"].append({
                "step": "human_decision",
                "decision": "approved",
                "approver": approver,
                "timestamp": ts,
                "feedback": None,
            })

        # Persist mutation in the mock store so subsequent GETs reflect it
        _MOCK_INCIDENTS[incident_id] = inc
        return inc
