"""
The reject -> revise -> review loop.

Before this feature, rejection feedback was validated, audited and persisted --
and then read by nothing. PROMPT_TEMPLATE had no slot for it and the pipeline
returned as soon as an incident was rejected. The reviewer's reason was stored
and wasted.

These tests assert the loop closes, and that closing it did not open a path
from a rejection to the cluster.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from agent import bob as bob_module
from agent.audit import record_decision
from agent.bob import BobResult, build_prompt
from agent.models import (
    MAX_REVISIONS,
    AllowedAction,
    EvidenceSnapshot,
    HumanDecision,
    Incident,
    IncidentRecord,
    IncidentState,
    RemediationPlan,
    TicketReference,
)
from agent.pipeline import plan_remediation, request_revision


def _evidence():
    return EvidenceSnapshot(
        deployment_name="ticket-booking",
        namespace="opspilot",
        pod_states=[{"name": "ticket-booking-abc", "ready": False}],
        rollout_history=[
            {"revision": "31", "image": "ticketbooking:1.1", "is_current": True},
            {"revision": "30", "image": "ticketbooking:1.0", "is_current": False},
        ],
        application_health={"status_code": 503, "healthy": False},
    )


def _pending_incident():
    inc = Incident(
        incident_id="INC-REVISE-001",
        state=IncidentState.EVIDENCE_COLLECTED,
        tickets=[
            TicketReference(
                ticket_id="TKT-1",
                named_workload="ticket-booking",
                reported_symptom="pods NotReady after rollout",
                created_at=datetime.now(timezone.utc),
            )
        ],
        evidence=_evidence(),
    )
    inc.plan = RemediationPlan(
        action=AllowedAction.restart_deployment,
        target="ticket-booking",
        reason="Restart to clear the failing pods",
    )
    inc.transition(IncidentState.PENDING_APPROVAL)
    return inc


def _bob_returning(analysis: dict):
    """Stub agent.bob.analyze, capturing the feedback it was handed."""
    captured: dict = {}

    def fake_analyze(evidence, tickets, feedback=None):
        captured["feedback"] = feedback
        captured["calls"] = captured.get("calls", 0) + 1
        return BobResult(
            ok=True, analysis=dict(analysis), raw_stdout="",
            invocation=["stub"], duration_ms=1,
        )

    return fake_analyze, captured


REVISED_ANALYSIS = {
    "schema_version": "1.0",
    "analysis_source": "ibm-bob",
    "hypotheses": [
        {
            "rank": 1,
            "statement": "Revision 31 shipped a bad image",
            "confidence": "high",
            "confidence_reason": "Pods on :1.1 fail readiness; :1.0 pods are healthy",
        }
    ],
    "root_cause": {
        "statement": "Image regression in revision 31",
        "confidence": "high",
    },
    "recommended_action": "rollback_deployment",
    "action_target": "ticket-booking",
    "action_parameters": {"to_revision": 30},
    "reason": "The reviewer asked us to look at the recent deployment first.",
}


class TestFeedbackIsCaptured:
    def test_rejection_appends_to_feedback_history(self):
        inc = _pending_incident()
        inc = record_decision(
            inc,
            HumanDecision(
                decision="rejected",
                approver="shivraj",
                feedback="Check the recent deployment before restarting.",
            ),
        )
        assert inc.feedback_history == [
            "Check the recent deployment before restarting."
        ]

    def test_approval_adds_nothing(self):
        inc = _pending_incident()
        inc = record_decision(inc, HumanDecision(decision="approved", approver="s"))
        assert inc.feedback_history == []

    def test_history_accumulates_across_rejections(self, monkeypatch):
        fake, _ = _bob_returning(REVISED_ANALYSIS)
        monkeypatch.setattr("agent.reasoning.bob_analyze", fake)

        inc = _pending_incident()
        inc = record_decision(
            inc, HumanDecision(decision="rejected", approver="s", feedback="first")
        )
        inc = request_revision(inc)
        inc = record_decision(
            inc, HumanDecision(decision="rejected", approver="s", feedback="second")
        )
        assert inc.feedback_history == ["first", "second"]


class TestFeedbackReachesTheReasoner:
    def test_prompt_contains_the_feedback(self):
        prompt = build_prompt({}, [], ["Do not restart during business hours"])
        assert "<human_feedback>" in prompt
        assert "Do not restart during business hours" in prompt

    def test_prompt_omits_the_block_when_there_is_none(self):
        assert "<human_feedback>" not in build_prompt({}, [], None)
        assert "<human_feedback>" not in build_prompt({}, [], [])

    def test_feedback_is_numbered_oldest_first(self):
        prompt = build_prompt({}, [], ["oldest", "newest"])
        assert "1. oldest" in prompt
        assert "2. newest" in prompt
        assert prompt.index("1. oldest") < prompt.index("2. newest")

    def test_revision_hands_the_feedback_to_bob(self, monkeypatch):
        """The point of the whole feature."""
        fake, captured = _bob_returning(REVISED_ANALYSIS)
        monkeypatch.setattr("agent.reasoning.bob_analyze", fake)

        inc = _pending_incident()
        inc = record_decision(
            inc,
            HumanDecision(
                decision="rejected", approver="s",
                feedback="Check the recent deployment first.",
            ),
        )
        request_revision(inc)
        assert captured["feedback"] == ["Check the recent deployment first."]


class TestRevisionProducesADifferentPlan:
    def test_plan_changes_after_rejection(self, monkeypatch):
        fake, _ = _bob_returning(REVISED_ANALYSIS)
        monkeypatch.setattr("agent.reasoning.bob_analyze", fake)

        inc = _pending_incident()
        original = inc.plan.action
        assert original == AllowedAction.restart_deployment

        inc = record_decision(
            inc,
            HumanDecision(
                decision="rejected", approver="s",
                feedback="Check the recent deployment first.",
            ),
        )
        inc = request_revision(inc)

        assert inc.plan is not None
        assert inc.plan.action == AllowedAction.rollback_deployment
        assert inc.plan.action != original

    def test_revision_returns_to_pending_approval(self, monkeypatch):
        fake, _ = _bob_returning(REVISED_ANALYSIS)
        monkeypatch.setattr("agent.reasoning.bob_analyze", fake)

        inc = _pending_incident()
        inc = record_decision(
            inc, HumanDecision(decision="rejected", approver="s", feedback="why")
        )
        inc = request_revision(inc)
        assert inc.state == IncidentState.PENDING_APPROVAL

    def test_the_revised_plan_can_then_be_approved(self, monkeypatch):
        fake, _ = _bob_returning(REVISED_ANALYSIS)
        monkeypatch.setattr("agent.reasoning.bob_analyze", fake)

        inc = _pending_incident()
        inc = record_decision(
            inc, HumanDecision(decision="rejected", approver="s", feedback="why")
        )
        inc = request_revision(inc)
        inc = record_decision(inc, HumanDecision(decision="approved", approver="s"))
        assert inc.state == IncidentState.APPROVED

    def test_stale_plan_is_cleared_before_re_analysis(self, monkeypatch):
        """
        If Bob is unavailable on the revision, no plan must remain that could
        be approved by mistake.
        """
        def unavailable(evidence, tickets, feedback=None):
            return BobResult(
                ok=False, analysis=None, raw_stdout="",
                invocation=[], duration_ms=1, error="no api key",
            )

        monkeypatch.setattr("agent.reasoning.bob_analyze", unavailable)
        inc = _pending_incident()
        inc = record_decision(
            inc, HumanDecision(decision="rejected", approver="s", feedback="why")
        )
        inc = request_revision(inc)
        assert inc.state == IncidentState.BOB_UNAVAILABLE
        assert inc.plan is None


class TestRevisionGuards:
    def test_cannot_revise_without_feedback(self):
        inc = _pending_incident()
        inc.transition(IncidentState.REJECTED)
        with pytest.raises(ValueError, match="no human feedback"):
            request_revision(inc)

    def test_cannot_revise_from_a_pending_state(self):
        with pytest.raises(ValueError, match="Cannot revise"):
            request_revision(_pending_incident())

    def test_revision_limit_is_enforced(self, monkeypatch):
        fake, _ = _bob_returning(REVISED_ANALYSIS)
        monkeypatch.setattr("agent.reasoning.bob_analyze", fake)

        inc = _pending_incident()
        for i in range(MAX_REVISIONS):
            inc = record_decision(
                inc,
                HumanDecision(decision="rejected", approver="s", feedback=f"no {i}"),
            )
            inc = request_revision(inc)

        inc = record_decision(
            inc, HumanDecision(decision="rejected", approver="s", feedback="still no")
        )
        with pytest.raises(ValueError, match="Revision limit"):
            request_revision(inc)

    def test_revision_count_tracks(self, monkeypatch):
        fake, _ = _bob_returning(REVISED_ANALYSIS)
        monkeypatch.setattr("agent.reasoning.bob_analyze", fake)

        inc = _pending_incident()
        inc = record_decision(
            inc, HumanDecision(decision="rejected", approver="s", feedback="a")
        )
        inc = request_revision(inc)
        assert inc.revision_count == 1


class TestTheLoopCannotReachTheCluster:
    """
    Adding a way out of a rejection must not add a way from a rejection to
    execution.
    """

    def test_feedback_recorded_to_executing_still_illegal(self):
        inc = _pending_incident()
        inc = record_decision(
            inc, HumanDecision(decision="rejected", approver="s", feedback="why")
        )
        assert inc.state == IncidentState.FEEDBACK_RECORDED
        with pytest.raises(ValueError, match="Illegal state transition"):
            inc.transition(IncidentState.EXECUTING)

    def test_revision_requires_a_fresh_approval(self, monkeypatch):
        fake, _ = _bob_returning(REVISED_ANALYSIS)
        monkeypatch.setattr("agent.reasoning.bob_analyze", fake)

        inc = _pending_incident()
        inc = record_decision(
            inc, HumanDecision(decision="rejected", approver="s", feedback="why")
        )
        inc = request_revision(inc)
        # The old decision is gone; nothing is carried over from the rejection.
        assert inc.human_decision is None
        assert inc.state != IncidentState.APPROVED
        with pytest.raises(ValueError, match="requires APPROVED"):
            inc.require_approval()


class TestRecordCarriesTheLoop:
    def test_record_holds_history_and_count(self, monkeypatch):
        fake, _ = _bob_returning(REVISED_ANALYSIS)
        monkeypatch.setattr("agent.reasoning.bob_analyze", fake)

        inc = _pending_incident()
        inc = record_decision(
            inc,
            HumanDecision(
                decision="rejected", approver="s", feedback="Look at the deploy",
            ),
        )
        inc = request_revision(inc)
        record = IncidentRecord.from_incident(inc)
        assert record.feedback_history == ["Look at the deploy"]
        assert record.revision_count == 1

    def test_audit_log_records_the_revision(self, monkeypatch):
        fake, _ = _bob_returning(REVISED_ANALYSIS)
        monkeypatch.setattr("agent.reasoning.bob_analyze", fake)

        inc = _pending_incident()
        inc = record_decision(
            inc, HumanDecision(decision="rejected", approver="s", feedback="why")
        )
        inc = request_revision(inc)
        steps = [e.get("step") for e in inc.audit_log]
        assert "rejection_recorded" in steps
        assert "revision_requested" in steps
