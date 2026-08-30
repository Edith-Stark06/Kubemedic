"""
API tests.

No live cluster and no live Bob: the cluster comes through
dependency_overrides, Bob and the ticket store through monkeypatch. What is
being tested is that the HTTP layer adds no authority of its own -- every
safety property still comes from agent/, and no route can go around one.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from agent import api
from agent.bob import BobResult
from agent.models import MAX_REVISIONS
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
    "root_cause": {"statement": "Image regression in revision 31", "confidence": "high"},
    "recommended_action": "rollback_deployment",
    "action_target": "ticket-booking",
    "action_parameters": {"to_revision": 30},
    "reason": "Roll back to the last healthy revision",
}


class FakeCluster:
    """Implements both protocols. Records what it was asked to do."""

    def __init__(self, healthy_after=True):
        self.calls: list[tuple] = []
        self.healthy_after = healthy_after

    def rollback_deployment(self, name, namespace, to_revision=None):
        self.calls.append(("rollback", name, namespace, to_revision))
        return {"action": "rollback_deployment", "to_revision": to_revision}

    def restart_deployment(self, name, namespace):
        self.calls.append(("restart", name, namespace))
        return {"action": "restart_deployment"}

    def scale_workload(self, name, namespace, replicas):
        self.calls.append(("scale", name, namespace, replicas))
        return {"action": "scale_workload"}

    def get_workload_status(self, name, namespace):
        return {
            "ready": self.healthy_after,
            "desired_replicas": 2,
            "updated_replicas": 2 if self.healthy_after else 0,
            "available_replicas": 2 if self.healthy_after else 0,
        }

    def get_application_health(self, name, namespace):
        return {
            "status_code": 200 if self.healthy_after else 503,
            "healthy": self.healthy_after,
        }


def _ticket(tid="TKT-1", title="Rollout not complete on ticket-booking"):
    now = datetime.now(timezone.utc).isoformat()
    return Ticket(
        id=tid, title=title, status=TicketStatus.open, severity=TicketSeverity.high,
        namespace="opspilot", deployment="ticket-booking", service="ticket-booking",
        created_at=now, updated_at=now,
        signals=["ready 0/2", "readiness probe 503"], related_ticket_ids=[],
    )


@pytest.fixture
def cluster():
    return FakeCluster()


@pytest.fixture
def client(monkeypatch, cluster, tmp_path):
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
                namespace=namespace, name=deployment, image="ticketbooking:1.1",
                revision="31", desired_replicas=2, ready_replicas=0,
                updated_replicas=2, available_replicas=0, unavailable_replicas=2,
                healthy=False, rollout_complete=False,
            ),
            pods=[PodState(name="ticket-booking-abc", ready=False,
                           image="ticketbooking:1.1")],
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
    monkeypatch.setattr(
        "mcp_server.tickets.list_tickets", lambda status=None, limit=50: [_ticket()]
    )
    monkeypatch.setattr(
        "agent.reasoning.bob_analyze",
        lambda evidence, tickets, feedback=None: BobResult(
            ok=True, analysis=dict(ANALYSIS), raw_stdout="",
            invocation=["stub"], duration_ms=1,
        ),
    )
    monkeypatch.setattr("agent.audit.RECORDS_DIR", tmp_path / "records")
    monkeypatch.setattr(
        "agent.api.write_record",
        lambda inc: __import__("agent.audit", fromlist=["write_record"]).write_record(
            inc, tmp_path / "records"
        ),
    )

    api.app.dependency_overrides[api.get_cluster] = lambda: cluster
    yield TestClient(api.app)
    api.app.dependency_overrides.clear()
    api._INCIDENTS.clear()


def _create(client) -> str:
    resp = client.post("/api/incidents", json={})
    assert resp.status_code == 201, resp.text
    return resp.json()["incident_id"]


class TestBasics:
    def test_health(self, client):
        assert client.get("/api/health").json()["status"] == "ok"

    def test_limits_states_the_revision_cap(self, client):
        assert client.get("/api/limits").json()["max_revisions"] == MAX_REVISIONS

    def test_unknown_incident_is_404(self, client):
        assert client.get("/api/incidents/INC-nope").status_code == 404


class TestCreateIncident:
    def test_creates_and_reaches_pending_approval(self, client):
        body = client.post("/api/incidents", json={}).json()
        assert body["state"] == "PENDING_APPROVAL"
        assert body["recommended_action"] == "rollback_deployment"
        assert body["analysis_source"] == "ibm-bob"
        assert body["root_cause"] == "Image regression in revision 31"

    def test_correlates_the_stored_ticket(self, client):
        assert client.post("/api/incidents", json={}).json()["ticket_ids"] == ["TKT-1"]

    def test_full_incident_carries_evidence_and_analysis(self, client):
        incident_id = _create(client)
        full = client.get(f"/api/incidents/{incident_id}").json()
        assert full["evidence"]["deployment_name"] == "ticket-booking"
        assert full["analysis"]["hypotheses"][0]["confidence"] == "high"
        assert full["correlation"]["member_tickets"] == ["TKT-1"]

    def test_bob_unavailable_yields_no_plan(self, client, monkeypatch):
        monkeypatch.setattr(
            "agent.reasoning.bob_analyze",
            lambda e, t, feedback=None: BobResult(
                ok=False, analysis=None, raw_stdout="", invocation=[],
                duration_ms=1, error="no api key",
            ),
        )
        body = client.post("/api/incidents", json={}).json()
        assert body["state"] == "BOB_UNAVAILABLE"
        assert body["recommended_action"] is None

    def test_evidence_failure_is_503_not_a_fabricated_incident(
        self, client, monkeypatch
    ):
        def boom(*a, **kw):
            raise RuntimeError("cluster unreachable")

        monkeypatch.setattr(api, "collect_agent_evidence", boom)
        resp = client.post("/api/incidents", json={})
        assert resp.status_code == 503
        assert "Evidence collection failed" in resp.json()["detail"]


class TestReviewGate:
    def test_approval_needs_no_feedback(self, client):
        incident_id = _create(client)
        resp = client.post(
            f"/api/incidents/{incident_id}/review",
            json={"decision": "APPROVED", "approver": "shivraj"},
        )
        assert resp.status_code == 200
        assert resp.json()["state"] == "APPROVED"

    def test_rejection_without_feedback_is_400_feedback_required(self, client):
        incident_id = _create(client)
        resp = client.post(
            f"/api/incidents/{incident_id}/review",
            json={"decision": "REJECTED", "approver": "shivraj"},
        )
        assert resp.status_code == 400
        assert resp.json()["detail"]["error"] == "feedback_required"

    @pytest.mark.parametrize("blank", ["", "   ", "\n\t"])
    def test_whitespace_feedback_is_also_refused(self, client, blank):
        incident_id = _create(client)
        resp = client.post(
            f"/api/incidents/{incident_id}/review",
            json={"decision": "REJECTED", "approver": "s", "feedback": blank},
        )
        assert resp.status_code == 400

    def test_rejection_with_feedback_is_recorded(self, client):
        incident_id = _create(client)
        resp = client.post(
            f"/api/incidents/{incident_id}/review",
            json={
                "decision": "REJECTED", "approver": "shivraj",
                "feedback": "Check the recent deployment before restarting.",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["state"] == "FEEDBACK_RECORDED"
        assert body["feedback_history"] == [
            "Check the recent deployment before restarting."
        ]

    def test_lowercase_decision_accepted(self, client):
        incident_id = _create(client)
        resp = client.post(
            f"/api/incidents/{incident_id}/review",
            json={"decision": "approved", "approver": "s"},
        )
        assert resp.status_code == 200

    def test_invalid_decision_rejected_by_the_schema(self, client):
        incident_id = _create(client)
        resp = client.post(
            f"/api/incidents/{incident_id}/review",
            json={"decision": "MAYBE", "approver": "s"},
        )
        assert resp.status_code == 422

    def test_double_review_is_409_not_a_silent_overwrite(self, client):
        incident_id = _create(client)
        client.post(
            f"/api/incidents/{incident_id}/review", json={"decision": "APPROVED"}
        )
        resp = client.post(
            f"/api/incidents/{incident_id}/review", json={"decision": "APPROVED"}
        )
        assert resp.status_code == 409


class TestExecutionGate:
    def test_execute_without_approval_is_refused(self, client, cluster):
        incident_id = _create(client)
        resp = client.post(f"/api/incidents/{incident_id}/execute")
        assert resp.status_code == 409
        assert "APPROVED" in resp.json()["detail"]
        assert cluster.calls == [], "the cluster was touched without approval"

    def test_execute_after_rejection_is_refused(self, client, cluster):
        incident_id = _create(client)
        client.post(
            f"/api/incidents/{incident_id}/review",
            json={"decision": "REJECTED", "feedback": "not now"},
        )
        resp = client.post(f"/api/incidents/{incident_id}/execute")
        assert resp.status_code == 409
        assert cluster.calls == [], "a rejected plan reached the cluster"

    def test_approved_execution_runs_and_verifies(self, client, cluster):
        incident_id = _create(client)
        client.post(
            f"/api/incidents/{incident_id}/review", json={"decision": "APPROVED"}
        )
        body = client.post(f"/api/incidents/{incident_id}/execute").json()

        assert body["execution"]["success"] is True
        assert body["verification"]["outcome"] == "PASS"
        assert body["incident"]["state"] == "RESOLVED"
        assert cluster.calls[0][0] == "rollback"

    def test_verification_failure_does_not_resolve(self, client, monkeypatch):
        api.app.dependency_overrides[api.get_cluster] = lambda: FakeCluster(
            healthy_after=False
        )
        incident_id = _create(client)
        client.post(
            f"/api/incidents/{incident_id}/review", json={"decision": "APPROVED"}
        )
        body = client.post(f"/api/incidents/{incident_id}/execute").json()
        assert body["verification"]["outcome"] == "FAIL"
        assert body["incident"]["state"] == "VERIFICATION_FAILED"


class TestRevisionLoop:
    def test_revise_after_rejection_returns_to_pending_approval(self, client):
        incident_id = _create(client)
        client.post(
            f"/api/incidents/{incident_id}/review",
            json={"decision": "REJECTED", "feedback": "look at the deploy"},
        )
        body = client.post(f"/api/incidents/{incident_id}/revise").json()
        assert body["state"] == "PENDING_APPROVAL"
        assert body["revision_count"] == 1

    def test_revised_plan_can_be_approved_and_executed(self, client, cluster):
        incident_id = _create(client)
        client.post(
            f"/api/incidents/{incident_id}/review",
            json={"decision": "REJECTED", "feedback": "look at the deploy"},
        )
        client.post(f"/api/incidents/{incident_id}/revise")
        client.post(
            f"/api/incidents/{incident_id}/review", json={"decision": "APPROVED"}
        )
        body = client.post(f"/api/incidents/{incident_id}/execute").json()
        assert body["incident"]["state"] == "RESOLVED"

    def test_revise_without_a_rejection_is_409(self, client):
        incident_id = _create(client)
        assert client.post(f"/api/incidents/{incident_id}/revise").status_code == 409

    def test_revision_cap_is_enforced_over_http(self, client):
        incident_id = _create(client)
        for i in range(MAX_REVISIONS):
            client.post(
                f"/api/incidents/{incident_id}/review",
                json={"decision": "REJECTED", "feedback": f"no {i}"},
            )
            client.post(f"/api/incidents/{incident_id}/revise")
        client.post(
            f"/api/incidents/{incident_id}/review",
            json={"decision": "REJECTED", "feedback": "still no"},
        )
        resp = client.post(f"/api/incidents/{incident_id}/revise")
        assert resp.status_code == 409
        assert "Revision limit" in resp.json()["detail"]


class TestRecord:
    def test_record_reflects_the_rejection(self, client):
        incident_id = _create(client)
        client.post(
            f"/api/incidents/{incident_id}/review",
            json={"decision": "REJECTED", "feedback": "wrong action"},
        )
        record = client.get(f"/api/incidents/{incident_id}/record").json()
        assert record["human_decision"] == "rejected"
        assert record["rejection_feedback"] == "wrong action"
        assert record["executed"] is False

    def test_record_reflects_a_verified_resolution(self, client):
        incident_id = _create(client)
        client.post(
            f"/api/incidents/{incident_id}/review", json={"decision": "APPROVED"}
        )
        client.post(f"/api/incidents/{incident_id}/execute")
        record = client.get(f"/api/incidents/{incident_id}/record").json()
        assert record["executed"] is True
        assert record["verification_outcome"] == "PASS"
        assert record["analysis_source"] == "ibm-bob"


class TestTickets:
    def test_tickets_come_from_the_store(self, client):
        body = client.get("/api/tickets").json()
        assert body[0]["id"] == "TKT-1"
