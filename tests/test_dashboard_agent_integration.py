"""
The dashboard-to-agent seam, exercised for real.

dashboard/tests cover the MockAdapter. RealAdapter -- the path that runs the
moment KUBEMEDIC_AGENT_BASE_URL is set -- had never been executed by anything,
which is how three missing `await`s survived: every httpx call returned a
coroutine and `raise_for_status()` would have failed on it.

These tests point RealAdapter at the actual agent API through an ASGI
transport, so the two halves are wired together in-process with no live cluster
and no live Bob.
"""
from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest

from agent import api
from agent.bob import BobResult
from dashboard.api_adapter import FeedbackRequired, RealAdapter
from mcp_server.models import Ticket, TicketSeverity, TicketStatus

ANALYSIS = {
    "schema_version": "1.0",
    "analysis_source": "ibm-bob",
    "hypotheses": [{
        "rank": 1,
        "statement": "Revision 31 shipped a bad image",
        "confidence": "high",
        "confidence_reason": "pods on :1.1 fail readiness",
    }],
    "root_cause": {"statement": "Image regression", "confidence": "high"},
    "recommended_action": "rollback_deployment",
    "action_target": "ticket-booking",
    "action_parameters": {"to_revision": 30},
    "reason": "Roll back to the last healthy revision",
}


class FakeCluster:
    def rollback_deployment(self, name, namespace, to_revision=None):
        return {"action": "rollback_deployment", "to_revision": to_revision}

    def restart_deployment(self, name, namespace):
        return {"action": "restart_deployment"}

    def scale_workload(self, name, namespace, replicas):
        return {"action": "scale_workload"}

    def get_workload_status(self, name, namespace):
        return {"ready": True, "desired_replicas": 2,
                "updated_replicas": 2, "available_replicas": 2}

    def get_application_health(self, name, namespace):
        return {"status_code": 200, "healthy": True}


def _ticket():
    now = datetime.now(timezone.utc).isoformat()
    return Ticket(
        id="TKT-1", title="Rollout not complete on ticket-booking",
        status=TicketStatus.open, severity=TicketSeverity.high,
        namespace="opspilot", deployment="ticket-booking",
        service="ticket-booking", created_at=now, updated_at=now,
        signals=["ready 0/2", "readiness probe 503"], related_ticket_ids=[],
    )


@pytest.fixture
def wired(monkeypatch, tmp_path):
    """RealAdapter talking to the real agent app over an ASGI transport."""
    api._INCIDENTS.clear()

    from agent.adapters import cluster_evidence_to_agent
    from mcp_server.evidence import (
        EvidenceSnapshot as ClusterEvidence, HealthResult, PodState,
        RevisionInfo, WorkloadState,
    )

    def fake_evidence(namespace="opspilot", deployment="ticket-booking",
                      service="ticket-booking"):
        return cluster_evidence_to_agent(ClusterEvidence(
            namespace=namespace, deployment=deployment, service=service,
            workload=WorkloadState(
                namespace=namespace, name=deployment,
                image="ticketbooking:1.1", revision="31",
                desired_replicas=2, ready_replicas=0, updated_replicas=2,
                available_replicas=0, unavailable_replicas=2,
                healthy=False, rollout_complete=False,
            ),
            pods=[PodState(name="ticket-booking-abc", ready=False)],
            events=[],
            recent_changes=[
                RevisionInfo(revision="31", image="ticketbooking:1.1", is_current=True),
                RevisionInfo(revision="30", image="ticketbooking:1.0", is_current=False),
            ],
            application_health=HealthResult(
                namespace=namespace, service=service, path="health",
                healthy=False, status_code=503,
            ),
        ))

    monkeypatch.setattr(api, "collect_agent_evidence", fake_evidence)
    monkeypatch.setattr("mcp_server.tickets.list_tickets",
                        lambda status=None, limit=50: [_ticket()])
    monkeypatch.setattr(
        "agent.reasoning.bob_analyze",
        lambda e, t, feedback=None: BobResult(
            ok=True, analysis=dict(ANALYSIS), raw_stdout="",
            invocation=["stub"], duration_ms=1,
        ),
    )
    monkeypatch.setattr("agent.audit.RECORDS_DIR", tmp_path / "records")
    api.app.dependency_overrides[api.get_cluster] = lambda: FakeCluster()

    adapter = RealAdapter("http://agent")
    transport = httpx.ASGITransport(app=api.app)

    original = httpx.AsyncClient

    def patched(*args, **kwargs):
        kwargs.setdefault("transport", transport)
        return original(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", patched)
    yield adapter
    api.app.dependency_overrides.clear()
    api._INCIDENTS.clear()


def _seed() -> str:
    from fastapi.testclient import TestClient

    with TestClient(api.app) as client:
        return client.post("/api/incidents", json={}).json()["incident_id"]


class TestRealAdapterReachesTheAgent:
    async def test_list_incidents(self, wired):
        _seed()
        incidents = await wired.list_incidents()
        assert len(incidents) == 1
        assert incidents[0]["state"] == "PENDING_APPROVAL"

    async def test_get_incident(self, wired):
        incident_id = _seed()
        incident = await wired.get_incident(incident_id)
        assert incident is not None
        assert incident["incident_id"] == incident_id
        assert incident["analysis"]["root_cause"]["statement"] == "Image regression"

    async def test_unknown_incident_is_none_not_an_exception(self, wired):
        assert await wired.get_incident("INC-nope") is None


class TestReviewThroughTheSeam:
    async def test_approval(self, wired):
        incident_id = _seed()
        result = await wired.record_decision(
            incident_id, decision="APPROVED", approver="verona", feedback=None
        )
        assert result["state"] == "APPROVED"

    async def test_rejection_with_a_reason_is_stored(self, wired):
        incident_id = _seed()
        result = await wired.record_decision(
            incident_id, decision="REJECTED", approver="verona",
            feedback="Check the rollout history first.",
        )
        assert result["state"] == "FEEDBACK_RECORDED"
        assert result["feedback_history"] == ["Check the rollout history first."]

    async def test_rejection_without_a_reason_raises_feedback_required(self, wired):
        """
        The agent refuses server-side whatever the UI allows. The adapter must
        surface that as something the reviewer can act on.
        """
        incident_id = _seed()
        with pytest.raises(FeedbackRequired):
            await wired.record_decision(
                incident_id, decision="REJECTED", approver="verona", feedback=None
            )

    async def test_rejection_with_whitespace_reason_also_refused(self, wired):
        incident_id = _seed()
        with pytest.raises(FeedbackRequired):
            await wired.record_decision(
                incident_id, decision="REJECTED", approver="verona", feedback="   "
            )
