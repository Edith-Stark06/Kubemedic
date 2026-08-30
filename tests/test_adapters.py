"""
Adapter tests.

The correlation hazard is the point of this file. agent/correlation.py needs
2 of 3 signals to admit a ticket into an incident, and two of those signals --
named_workload and created_at -- arrive only through the adapter. If either is
dropped, the ticket is silently excluded from its own incident with no error
raised anywhere. These tests make that failure loud.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from agent.adapters import (
    cluster_evidence_to_agent,
    collect_agent_evidence,
    parse_timestamp,
    previous_revision,
    ticket_to_reference,
    tickets_to_references,
)
from agent.correlation import correlate
from agent.models import EvidenceSnapshot as AgentEvidence
from mcp_server.evidence import (
    EvidenceSnapshot as ClusterEvidence,
    EventItem,
    HealthResult,
    PodState,
    RevisionInfo,
    WorkloadState,
)
from mcp_server.models import Ticket, TicketSeverity, TicketStatus


def _ticket(**over):
    now = datetime.now(timezone.utc).isoformat()
    base = dict(
        id="TKT-20260830-120000-000001",
        title="Rollout not complete on ticket-booking",
        status=TicketStatus.open,
        severity=TicketSeverity.high,
        namespace="opspilot",
        deployment="ticket-booking",
        service="ticket-booking",
        created_at=now,
        updated_at=now,
        signals=["desired: 2, ready: 0", "readiness probe failing 503"],
        related_ticket_ids=[],
    )
    base.update(over)
    return Ticket(**base)


def _cluster_evidence():
    return ClusterEvidence(
        namespace="opspilot",
        deployment="ticket-booking",
        service="ticket-booking",
        workload=WorkloadState(
            namespace="opspilot", name="ticket-booking",
            image="ticketbooking:1.1", revision="31",
            desired_replicas=2, ready_replicas=0, available_replicas=0,
            updated_replicas=2, unavailable_replicas=2,
            healthy=False, rollout_complete=False,
        ),
        pods=[PodState(name="ticket-booking-abc", phase="Running", ready=False,
                       restarts=0, image="ticketbooking:1.1")],
        events=[EventItem(type="Warning", reason="Unhealthy",
                          message="Readiness probe failed: HTTP 503")],
        recent_changes=[
            RevisionInfo(revision="31", image="ticketbooking:1.1", is_current=True),
            RevisionInfo(revision="30", image="ticketbooking:1.0", is_current=False),
            RevisionInfo(revision="1", image="ticketbooking:1.0", is_current=False),
        ],
        application_health=HealthResult(
            namespace="opspilot", service="ticket-booking", path="health",
            healthy=False, status_code=503,
        ),
    )


class TestTimestampParsing:
    def test_iso_string_becomes_aware_utc(self):
        dt = parse_timestamp("2026-08-30T10:00:00+00:00")
        assert dt is not None and dt.tzinfo is not None

    def test_naive_string_is_assumed_utc(self):
        """
        Correlation compares against an aware collected_at. A naive datetime
        would raise TypeError mid-incident.
        """
        dt = parse_timestamp("2026-08-30T10:00:00")
        assert dt is not None and dt.tzinfo == timezone.utc

    def test_zulu_suffix_handled(self):
        assert parse_timestamp("2026-08-30T10:00:00Z") is not None

    def test_datetime_passes_through(self):
        now = datetime.now(timezone.utc)
        assert parse_timestamp(now) == now

    @pytest.mark.parametrize("bad", [None, "", "   ", "not a date"])
    def test_unparseable_returns_none_without_raising(self, bad):
        assert parse_timestamp(bad) is None


class TestTicketToReference:
    def test_named_workload_survives(self):
        """Correlation signal 1. Losing it costs the ticket its incident."""
        assert ticket_to_reference(_ticket()).named_workload == "ticket-booking"

    def test_created_at_survives_as_aware_datetime(self):
        """Correlation signal 2."""
        ref = ticket_to_reference(_ticket())
        assert ref.created_at is not None
        assert ref.created_at.tzinfo is not None

    def test_signals_reach_reported_symptom(self):
        """Correlation signal 3 -- the keyword regex reads this string."""
        symptom = ticket_to_reference(_ticket()).reported_symptom
        assert "readiness probe failing 503" in symptom
        assert "Rollout not complete" in symptom

    def test_id_and_severity_carried(self):
        ref = ticket_to_reference(_ticket())
        assert ref.ticket_id.startswith("TKT-")
        assert ref.severity == "high"

    def test_empty_signals_still_yields_a_symptom_from_the_title(self):
        ref = ticket_to_reference(_ticket(signals=[]))
        assert ref.reported_symptom == "Rollout not complete on ticket-booking"

    def test_batch_conversion(self):
        refs = tickets_to_references([_ticket(), _ticket(id="TKT-2")])
        assert [r.ticket_id for r in refs] == [
            "TKT-20260830-120000-000001", "TKT-2"
        ]


class TestAdaptedTicketsActuallyCorrelate:
    """
    The end-to-end point of the adapter: stored tickets, once adapted, must
    group into one incident.
    """

    def test_three_adapted_tickets_form_one_incident(self):
        now = datetime.now(timezone.utc)
        stored = [
            _ticket(id="TKT-1", title="Rollout not complete",
                    created_at=now.isoformat()),
            _ticket(id="TKT-2", title="Pod NotReady",
                    created_at=(now - timedelta(minutes=5)).isoformat()),
            _ticket(id="TKT-3", title="App health check failed 503",
                    created_at=(now - timedelta(minutes=9)).isoformat()),
        ]
        evidence = cluster_evidence_to_agent(_cluster_evidence())
        incident, excluded = correlate(tickets_to_references(stored), evidence)

        assert len(incident.tickets) == 3, (
            f"adapter lost a correlation signal; excluded={[t.ticket_id for t in excluded]}"
        )
        assert incident.correlation.member_tickets == ["TKT-1", "TKT-2", "TKT-3"]

    def test_a_ticket_for_another_workload_is_excluded(self):
        now = datetime.now(timezone.utc).isoformat()
        stored = [
            _ticket(id="TKT-1", created_at=now),
            _ticket(id="TKT-9", deployment="billing-service",
                    title="disk usage steady", signals=["nothing wrong"],
                    created_at=now),
        ]
        evidence = cluster_evidence_to_agent(_cluster_evidence())
        incident, excluded = correlate(tickets_to_references(stored), evidence)
        assert [t.ticket_id for t in incident.tickets] == ["TKT-1"]
        assert [t.ticket_id for t in excluded] == ["TKT-9"]


class TestClusterEvidenceToAgent:
    def test_field_renames(self):
        agent_ev = cluster_evidence_to_agent(_cluster_evidence())
        assert isinstance(agent_ev, AgentEvidence)
        assert agent_ev.deployment_name == "ticket-booking"
        assert agent_ev.namespace == "opspilot"

    def test_pods_events_and_history_carried(self):
        agent_ev = cluster_evidence_to_agent(_cluster_evidence())
        assert len(agent_ev.pod_states) == 1
        assert len(agent_ev.events) == 1
        assert len(agent_ev.rollout_history) == 3

    def test_application_health_carried(self):
        agent_ev = cluster_evidence_to_agent(_cluster_evidence())
        assert agent_ev.application_health["status_code"] == 503

    def test_raw_holds_the_whole_bundle(self):
        """
        Bob is sent the full dict, so nothing observed is dropped on the way
        to reasoning even when the agent model has no slot for it.
        """
        agent_ev = cluster_evidence_to_agent(_cluster_evidence())
        assert agent_ev.raw["workload"]["image"] == "ticketbooking:1.1"

    def test_is_json_serialisable_for_the_bob_prompt(self):
        import json
        agent_ev = cluster_evidence_to_agent(_cluster_evidence())
        assert json.dumps(agent_ev.model_dump(mode="json"), default=str)


class TestPreviousRevision:
    def test_picks_highest_non_current(self):
        assert previous_revision(cluster_evidence_to_agent(_cluster_evidence())) == 30

    def test_none_when_only_current_exists(self):
        cluster = _cluster_evidence()
        cluster.recent_changes = [
            RevisionInfo(revision="31", image="x:1", is_current=True)
        ]
        assert previous_revision(cluster_evidence_to_agent(cluster)) is None

    def test_none_when_history_empty(self):
        cluster = _cluster_evidence()
        cluster.recent_changes = []
        assert previous_revision(cluster_evidence_to_agent(cluster)) is None


class TestCollectHelper:
    def test_delegates_to_collect_and_adapts(self, monkeypatch):
        monkeypatch.setattr(
            "mcp_server.evidence.collect", lambda *a, **kw: _cluster_evidence()
        )
        evidence = collect_agent_evidence("opspilot", "ticket-booking", "ticket-booking")
        assert isinstance(evidence, AgentEvidence)
        assert evidence.deployment_name == "ticket-booking"
