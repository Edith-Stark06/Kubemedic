"""
Tests: models, correlation, Bob contract, remediation, validation.
Run from repo root:  python -m pytest tests/ -v
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from agent.models import (
    AllowedAction,
    BobAnalysis,
    CorrelationResult,
    EvidenceSnapshot,
    HumanDecision,
    Incident,
    IncidentRecord,
    IncidentState,
    RemediationPlan,
    TicketReference,
    VerificationResult,
    VerificationSignal,
)
from agent.correlation import correlate

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

NOW = datetime.now(timezone.utc)


def _evidence(deployment: str = "ticket-booking") -> EvidenceSnapshot:
    return EvidenceSnapshot(
        deployment_name=deployment,
        namespace="kubemedic",
        collected_at=NOW,
    )


def _ticket(
    tid: str,
    workload: str | None = "ticket-booking",
    symptom: str = "service not responding",
    offset_minutes: int = 30,
) -> TicketReference:
    return TicketReference(
        ticket_id=tid,
        title=f"Issue {tid}",
        reported_symptom=symptom,
        named_workload=workload,
        created_at=NOW - timedelta(minutes=offset_minutes),
    )


def _valid_bob_raw(
    action: str = "rollback_deployment",
    target: str = "ticket-booking",
) -> dict:
    return {
        "schema_version": "1.0",
        "analysis_source": "ibm-bob",
        "correlation": {
            "master_incident_id": "INC-501",
            "member_tickets": ["T-1", "T-2"],
            "excluded_tickets": [],
            "correlation_basis": ["same workload, same window"],
            "rationale": "One regression.",
        },
        "timeline": [
            {"t": "09:37:04Z", "event": "rollout begins", "source": "rollout_history"}
        ],
        "hypotheses": [
            {
                "rank": 1,
                "statement": "New image fails readiness probe.",
                "confidence": "high",
                "confidence_reason": "Three independent sources agree.",
                "supporting_evidence": ["pod 0/1 Ready"],
                "contradicting_evidence": ["none found in available evidence"],
                "cheapest_next_check": "Compare images.",
            }
        ],
        "root_cause": {
            "statement": "Revision 4 regression.",
            "confidence": "high",
            "is_inference": True,
        },
        "recommended_action": action,
        "action_target": target,
        "action_parameters": {"to_revision": 3},
        "reason": "Rollback restores last healthy revision.",
        "risk_explanation": "Medium — discards revision 4.",
        "requires_human_approval": True,
    }


# ──────────────────────────────────────────────────────────────────────────────
# 1. Model creation
# ──────────────────────────────────────────────────────────────────────────────

class TestModelCreation:
    def test_ticket_reference_minimal(self):
        t = TicketReference(ticket_id="T-1")
        assert t.ticket_id == "T-1"

    def test_evidence_snapshot_defaults(self):
        e = _evidence()
        assert e.namespace == "kubemedic"
        assert isinstance(e.collected_at, datetime)

    def test_allowed_action_enum(self):
        assert AllowedAction("rollback_deployment") == AllowedAction.rollback_deployment
        with pytest.raises(ValueError):
            AllowedAction("delete_namespace")

    def test_incident_defaults(self):
        inc = Incident(incident_id="INC-1")
        assert inc.state == IncidentState.OPEN
        assert inc.tickets == []

    def test_human_decision_approved_no_feedback_ok(self):
        d = HumanDecision(decision="approved", approver="alice")
        assert d.feedback is None

    def test_human_decision_rejected_requires_feedback(self):
        with pytest.raises(ValueError, match="feedback is required"):
            HumanDecision(decision="rejected", approver="alice", feedback="")

    def test_human_decision_rejected_with_feedback_ok(self):
        d = HumanDecision(
            decision="rejected", approver="alice", feedback="Wrong revision."
        )
        assert d.feedback == "Wrong revision."

    def test_verification_result_inconclusive(self):
        v = VerificationResult.inconclusive("tool timed out")
        assert v.outcome == "INCONCLUSIVE"
        assert "timed out" in v.detail

    def test_incident_record_from_incident(self):
        inc = Incident(
            incident_id="INC-42",
            tickets=[_ticket("T-1")],
            state=IncidentState.RESOLVED,
        )
        record = IncidentRecord.from_incident(inc)
        assert record.incident_id == "INC-42"
        assert record.final_state == IncidentState.RESOLVED
        assert "T-1" in record.tickets


# ──────────────────────────────────────────────────────────────────────────────
# 2. Many-to-one ticket correlation
# ──────────────────────────────────────────────────────────────────────────────

class TestCorrelation:
    def test_three_tickets_one_incident(self):
        tickets = [
            _ticket("T-1", workload="ticket-booking", symptom="crash loop"),
            _ticket("T-2", workload="ticket-booking", symptom="500 errors"),
            _ticket("T-3", workload="ticket-booking", symptom="timeout"),
        ]
        ev = _evidence("ticket-booking")
        inc, excluded = correlate(tickets, ev, incident_id="INC-99")
        assert inc.incident_id == "INC-99"
        assert len(inc.tickets) == 3
        assert excluded == []

    def test_unrelated_ticket_excluded(self):
        tickets = [
            _ticket("T-1", workload="ticket-booking", symptom="crash loop"),
            # Different workload, recent but no symptom keyword match
            TicketReference(
                ticket_id="T-UNRELATED",
                reported_symptom="minor cosmetic glitch",
                named_workload="other-service",
                created_at=NOW - timedelta(minutes=10),
            ),
        ]
        ev = _evidence("ticket-booking")
        inc, excluded = correlate(tickets, ev)
        member_ids = [t.ticket_id for t in inc.tickets]
        assert "T-1" in member_ids
        assert any(t.ticket_id == "T-UNRELATED" for t in excluded)

    def test_empty_tickets_list(self):
        inc, excluded = correlate([], _evidence())
        assert inc.tickets == []
        assert excluded == []

    def test_correlation_preserves_ticket_refs(self):
        t1 = _ticket("T-11", symptom="pod not ready", offset_minutes=20)
        t2 = _ticket("T-12", symptom="service unavailable", offset_minutes=15)
        inc, _ = correlate([t1, t2], _evidence())
        ids = [t.ticket_id for t in inc.tickets]
        assert "T-11" in ids
        assert "T-12" in ids

    def test_incident_state_evidence_collected(self):
        inc, _ = correlate([_ticket("T-1")], _evidence())
        assert inc.state == IncidentState.EVIDENCE_COLLECTED

    def test_old_ticket_excluded(self):
        """Ticket created 5 hours ago should not correlate on time signal alone."""
        old = TicketReference(
            ticket_id="T-OLD",
            named_workload="ticket-booking",
            reported_symptom="cosmetic issue",   # no symptom keywords → score ≤ 1
            created_at=NOW - timedelta(hours=5),
        )
        inc, excluded = correlate([old], _evidence())
        assert any(t.ticket_id == "T-OLD" for t in excluded)


# ──────────────────────────────────────────────────────────────────────────────
# 3. Valid Bob analysis parsing
# ──────────────────────────────────────────────────────────────────────────────

class TestBobAnalysisValid:
    def test_parse_success_shape(self):
        raw = _valid_bob_raw()
        analysis = BobAnalysis.from_raw(raw)
        assert analysis.analysis_source == "ibm-bob"
        assert analysis.recommended_action == AllowedAction.rollback_deployment
        assert analysis.action_target == "ticket-booking"
        assert len(analysis.hypotheses) == 1
        assert analysis.hypotheses[0].confidence == "high"

    def test_parse_all_three_actions(self):
        for action in ("rollback_deployment", "restart_deployment", "scale_workload"):
            raw = _valid_bob_raw(action=action)
            if action == "scale_workload":
                raw["action_parameters"] = {"replicas": 3}
            a = BobAnalysis.from_raw(raw)
            assert a.recommended_action.value == action

    def test_null_action_is_valid(self):
        raw = _valid_bob_raw()
        raw["recommended_action"] = None
        raw["action_target"] = None
        a = BobAnalysis.from_raw(raw)
        assert a.recommended_action is None

    def test_requires_human_approval_always_true(self):
        raw = _valid_bob_raw()
        a = BobAnalysis.from_raw(raw)
        assert a.requires_human_approval is True

    def test_is_unavailable_false_for_success(self):
        a = BobAnalysis.from_raw(_valid_bob_raw())
        assert not a.is_unavailable


# ──────────────────────────────────────────────────────────────────────────────
# 4. Malformed Bob analysis
# ──────────────────────────────────────────────────────────────────────────────

class TestBobAnalysisMalformed:
    def test_unknown_action_rejected(self):
        raw = _valid_bob_raw(action="delete_namespace")
        with pytest.raises(ValueError, match="not in the allowlist"):
            BobAnalysis.from_raw(raw)

    def test_action_without_target_rejected(self):
        raw = _valid_bob_raw()
        raw["action_target"] = None
        with pytest.raises(ValueError, match="action_target is required"):
            BobAnalysis.from_raw(raw)

    def test_invalid_confidence_rejected(self):
        raw = _valid_bob_raw()
        raw["hypotheses"][0]["confidence"] = "very_sure"
        with pytest.raises(ValueError):
            BobAnalysis.from_raw(raw)

    def test_missing_hypotheses_field_defaults_empty(self):
        """Graceful: missing hypotheses list treated as empty list."""
        raw = _valid_bob_raw()
        del raw["hypotheses"]
        a = BobAnalysis.from_raw(raw)
        assert a.hypotheses == []

    def test_evidence_unavailable_shape(self):
        raw = {
            "schema_version": "1.0",
            "analysis_source": "ibm-bob",
            "status": "evidence_unavailable",
            "missing_signals": ["get_workload_snapshot failed"],
            "partial_evidence": [],
            "hypotheses": [],
            "recommended_action": None,
            "requires_human_approval": True,
            "reason": "Cannot diagnose.",
        }
        a = BobAnalysis.from_raw(raw)
        assert a.is_unavailable

    def test_bob_unavailable_shape(self):
        from agent.bob import unavailable_analysis
        ua = unavailable_analysis("REST timeout")
        a = BobAnalysis.model_validate(ua)
        assert a.is_unavailable
        assert a.analysis_source == "unavailable"


# ──────────────────────────────────────────────────────────────────────────────
# 5. Valid remediation plan
# ──────────────────────────────────────────────────────────────────────────────

class TestRemediationPlan:
    def test_from_analysis(self):
        a = BobAnalysis.from_raw(_valid_bob_raw())
        plan = RemediationPlan.from_analysis(a)
        assert plan.action == AllowedAction.rollback_deployment
        assert plan.target == "ticket-booking"

    def test_direct_construction(self):
        plan = RemediationPlan(
            action=AllowedAction.restart_deployment,
            target="payment-svc",
            reason="Memory leak — restart is the smallest reversible fix.",
            risk="low",
        )
        assert plan.action == AllowedAction.restart_deployment

    def test_from_analysis_null_action_raises(self):
        raw = _valid_bob_raw()
        raw["recommended_action"] = None
        raw["action_target"] = None
        a = BobAnalysis.from_raw(raw)
        with pytest.raises(ValueError, match="recommended_action is null"):
            RemediationPlan.from_analysis(a)


# ──────────────────────────────────────────────────────────────────────────────
# 6. Invalid remediation action
# ──────────────────────────────────────────────────────────────────────────────

class TestInvalidRemediation:
    def test_action_enum_rejects_arbitrary_string(self):
        with pytest.raises(ValueError):
            RemediationPlan(
                action="exec_shell",   # type: ignore[arg-type]
                target="svc",
            )

    def test_action_enum_rejects_kubectl_string(self):
        with pytest.raises(ValueError):
            RemediationPlan(
                action="kubectl delete pod --all",  # type: ignore[arg-type]
                target="svc",
            )


# ──────────────────────────────────────────────────────────────────────────────
# 7. Bob unavailable state
# ──────────────────────────────────────────────────────────────────────────────

class TestBobUnavailableState:
    def test_analyze_no_key_returns_unavailable(self):
        """analyze() with no API key must return ok=False, never fabricate."""
        import os
        os.environ.pop("KUBEMEDIC_BOB_API_KEY", None)
        # Re-import to pick up cleared env (module-level constant is already set,
        # but the function checks the module-level var; patch it directly)
        import agent.bob as bob_mod
        original = bob_mod.BOB_API_KEY
        bob_mod.BOB_API_KEY = ""
        try:
            from agent.bob import analyze
            result = analyze({"deployment": "test"}, [])
            assert not result.ok
            assert result.analysis is None
            assert result.error is not None
        finally:
            bob_mod.BOB_API_KEY = original

    def test_reasoning_on_bob_unavailable_does_not_fabricate(self):
        """run_analysis must transition to BOB_UNAVAILABLE, not ANALYSED."""
        from agent.reasoning import run_analysis
        import agent.bob as bob_mod

        inc = Incident(
            incident_id="INC-BOB-DOWN",
            state=IncidentState.EVIDENCE_COLLECTED,
            tickets=[_ticket("T-1")],
            evidence=_evidence(),
        )

        # Patch bob_analyze to simulate unavailability
        fake_result = MagicMock()
        fake_result.ok = False
        fake_result.analysis = None
        fake_result.error = "Bob REST timed out"
        fake_result.audit_entry.return_value = {"stage": "BOB", "ok": False}

        with patch("agent.reasoning.bob_analyze", return_value=fake_result):
            updated, analysis = run_analysis(inc)

        assert updated.state == IncidentState.BOB_UNAVAILABLE
        assert analysis.is_unavailable
        assert analysis.analysis_source == "unavailable"

    def test_reasoning_on_malformed_output_does_not_fabricate(self):
        """Malformed Bob output must also become BOB_UNAVAILABLE, not ANALYSED."""
        from agent.reasoning import run_analysis

        inc = Incident(
            incident_id="INC-BAD-OUTPUT",
            state=IncidentState.EVIDENCE_COLLECTED,
            tickets=[_ticket("T-1")],
            evidence=_evidence(),
        )

        fake_result = MagicMock()
        fake_result.ok = True
        fake_result.error = None
        fake_result.analysis = {"recommended_action": "blow_up_cluster"}  # invalid
        fake_result.audit_entry.return_value = {"stage": "BOB", "ok": True}

        with patch("agent.reasoning.bob_analyze", return_value=fake_result):
            updated, analysis = run_analysis(inc)

        assert updated.state == IncidentState.BOB_UNAVAILABLE
        assert analysis.is_unavailable

    def test_illegal_transition_rejected_to_executing(self):
        """REJECTED → EXECUTING must raise — this is the safety test."""
        inc = Incident(
            incident_id="INC-REJ",
            state=IncidentState.REJECTED,
        )
        with pytest.raises(ValueError, match="Illegal state transition"):
            inc.transition(IncidentState.EXECUTING)

    def test_require_approval_raises_when_not_approved(self):
        inc = Incident(incident_id="INC-X", state=IncidentState.ANALYSED)
        with pytest.raises(ValueError, match="Execution requires APPROVED"):
            inc.require_approval()

    def test_require_approval_passes_when_approved(self):
        inc = Incident(incident_id="INC-Y", state=IncidentState.APPROVED)
        inc.require_approval()  # must not raise
