"""
Tests: rejection path, executor safety, verification, audit, end-to-end pipeline.
Run from repo root:  python -m pytest tests/ -v
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agent.audit import record_decision, write_record
from agent.executor import execute
from agent.models import (
    AllowedAction,
    BobAnalysis,
    EvidenceSnapshot,
    ExecutionResult,
    HumanDecision,
    Incident,
    IncidentRecord,
    IncidentState,
    RemediationPlan,
    TicketReference,
    VerificationResult,
    VerificationSignal,
)
from agent.pipeline import plan_remediation, run_full_pipeline
from agent.verification import verify

# ──────────────────────────────────────────────────────────────────────────────
# Shared fixtures / helpers
# ──────────────────────────────────────────────────────────────────────────────

NOW = datetime.now(timezone.utc)


def _evidence(deployment: str = "ticket-booking") -> EvidenceSnapshot:
    return EvidenceSnapshot(
        deployment_name=deployment,
        namespace="kubemedic",
        collected_at=NOW,
    )


def _ticket(tid: str) -> TicketReference:
    return TicketReference(
        ticket_id=tid,
        reported_symptom="service crash loop",
        named_workload="ticket-booking",
        created_at=NOW - timedelta(minutes=20),
    )


def _valid_analysis(
    action: str = "rollback_deployment",
    target: str = "ticket-booking",
) -> BobAnalysis:
    return BobAnalysis.from_raw(
        {
            "schema_version": "1.0",
            "analysis_source": "ibm-bob",
            "correlation": {
                "master_incident_id": "INC-TEST",
                "member_tickets": ["T-1"],
                "excluded_tickets": [],
                "correlation_basis": ["same workload"],
                "rationale": "test",
            },
            "hypotheses": [
                {
                    "rank": 1,
                    "statement": "Bad image.",
                    "confidence": "high",
                    "confidence_reason": "Three sources.",
                    "supporting_evidence": ["pod 0/1"],
                    "contradicting_evidence": ["none found in available evidence"],
                    "cheapest_next_check": "compare images",
                }
            ],
            "root_cause": {
                "statement": "Revision 4 regression.",
                "confidence": "high",
                "is_inference": True,
            },
            "recommended_action": action,
            "action_target": target,
            "action_parameters": {"to_revision": 3} if action == "rollback_deployment" else {},
            "reason": "Rollback restores last healthy revision.",
            "risk_explanation": "Medium risk.",
            "requires_human_approval": True,
        }
    )


def _analysed_incident(
    inc_id: str = "INC-1",
    action: str = "rollback_deployment",
) -> Incident:
    """Return an incident that has been analysed and is ready for approval."""
    inc = Incident(
        incident_id=inc_id,
        state=IncidentState.EVIDENCE_COLLECTED,
        tickets=[_ticket("T-1")],
        evidence=_evidence(),
    )
    analysis = _valid_analysis(action=action)
    inc.analysis = analysis
    inc.transition(IncidentState.ANALYSED)
    return inc


def _approved_incident(inc_id: str = "INC-2") -> Incident:
    inc = _analysed_incident(inc_id=inc_id)
    inc = plan_remediation(inc)              # → PENDING_APPROVAL
    decision = HumanDecision(decision="approved", approver="alice")
    inc = record_decision(inc, decision)     # → APPROVED
    return inc


def _fake_k8s(success: bool = True) -> MagicMock:
    k8s = MagicMock()
    resp = {"status": "ok"} if success else None
    if not success:
        k8s.rollback_deployment.side_effect = RuntimeError("cluster unreachable")
        k8s.restart_deployment.side_effect = RuntimeError("cluster unreachable")
        k8s.scale_workload.side_effect = RuntimeError("cluster unreachable")
    else:
        k8s.rollback_deployment.return_value = resp
        k8s.restart_deployment.return_value = resp
        k8s.scale_workload.return_value = resp
    return k8s


def _fake_reader(rollout_ok: bool = True, health_ok: bool = True) -> MagicMock:
    reader = MagicMock()
    reader.get_workload_status.return_value = {
        "ready": rollout_ok,
        "updated_replicas": 2,
        "desired_replicas": 2,
        "available_replicas": 2,
    }
    reader.get_application_health.return_value = {
        "status_code": 200 if health_ok else 503,
        "healthy": health_ok,
    }
    return reader


# ──────────────────────────────────────────────────────────────────────────────
# Rejection path
# ──────────────────────────────────────────────────────────────────────────────

class TestRejectionPath:
    def test_empty_feedback_on_reject_raises_422_equivalent(self):
        """Empty feedback on reject → validation error, no state change."""
        inc = _analysed_incident()
        inc = plan_remediation(inc)
        original_state = inc.state
        with pytest.raises(ValueError, match="feedback is required"):
            HumanDecision(decision="rejected", approver="bob", feedback="")
        # State must be unchanged
        assert inc.state == original_state

    def test_valid_feedback_transitions_to_feedback_recorded(self):
        inc = _analysed_incident("INC-REJ-1")
        inc = plan_remediation(inc)
        decision = HumanDecision(
            decision="rejected", approver="bob", feedback="Deliberate maintenance."
        )
        inc = record_decision(inc, decision)
        assert inc.state == IncidentState.FEEDBACK_RECORDED
        assert inc.human_decision.decision == "rejected"
        assert inc.human_decision.feedback == "Deliberate maintenance."

    def test_rejection_sets_executed_false_in_record(self):
        inc = _analysed_incident("INC-REJ-2")
        inc = plan_remediation(inc)
        decision = HumanDecision(
            decision="rejected", approver="bob", feedback="Planned rollout."
        )
        inc = record_decision(inc, decision)
        record = IncidentRecord.from_incident(inc)
        assert record.executed is False
        assert record.human_decision == "rejected"
        assert record.rejection_feedback == "Planned rollout."

    def test_rejection_feedback_persisted_in_audit_log(self):
        inc = _analysed_incident("INC-REJ-3")
        inc = plan_remediation(inc)
        decision = HumanDecision(
            decision="rejected", approver="carol", feedback="Wrong target."
        )
        inc = record_decision(inc, decision)
        rejection_entries = [
            e for e in inc.audit_log if e.get("step") == "rejection_recorded"
        ]
        assert len(rejection_entries) == 1
        assert rejection_entries[0]["reason"] == "Wrong target."
        assert rejection_entries[0]["executed"] is False

    def test_rejected_to_executing_is_unreachable(self):
        inc = _analysed_incident("INC-REJ-4")
        inc = plan_remediation(inc)
        decision = HumanDecision(
            decision="rejected", approver="dave", feedback="Not now."
        )
        inc = record_decision(inc, decision)
        with pytest.raises(ValueError, match="Illegal state transition"):
            inc.transition(IncidentState.EXECUTING)

    def test_decision_on_wrong_state_raises(self):
        inc = Incident(incident_id="INC-BAD", state=IncidentState.OPEN)
        decision = HumanDecision(decision="approved", approver="alice")
        with pytest.raises(ValueError, match="Cannot record decision"):
            record_decision(inc, decision)


# ──────────────────────────────────────────────────────────────────────────────
# Executor safety
# ──────────────────────────────────────────────────────────────────────────────

class TestExecutor:
    def test_execute_approved_succeeds(self):
        inc = _approved_incident("INC-EX-1")
        inc, result = execute(inc, _fake_k8s())
        assert inc.state == IncidentState.EXECUTED
        assert result.success is True

    def test_execute_without_approval_raises(self):
        inc = _analysed_incident("INC-EX-2")
        inc = plan_remediation(inc)
        # Still PENDING_APPROVAL — not approved
        with pytest.raises(ValueError, match="Execution requires APPROVED"):
            execute(inc, _fake_k8s())

    def test_second_execute_returns_existing_state(self):
        """Idempotency: a second execute request returns existing result."""
        inc = _approved_incident("INC-EX-3")
        k8s = _fake_k8s()
        inc, first_result = execute(inc, k8s)
        assert inc.state == IncidentState.EXECUTED

        # Second call — k8s must NOT be called again
        inc, second_result = execute(inc, k8s)
        assert inc.state == IncidentState.EXECUTED
        assert second_result is first_result
        # rollback_deployment called exactly once
        k8s.rollback_deployment.assert_called_once()

    def test_cluster_failure_captured_not_raised(self):
        """K8s error → ExecutionResult.success=False, incident stays at EXECUTED."""
        inc = _approved_incident("INC-EX-4")
        inc, result = execute(inc, _fake_k8s(success=False))
        assert inc.state == IncidentState.EXECUTED
        assert result.success is False
        assert "cluster unreachable" in result.message

    def test_all_three_actions_dispatched(self):
        for action in ("rollback_deployment", "restart_deployment", "scale_workload"):
            inc = _analysed_incident(inc_id=f"INC-{action}", action=action)
            if action == "scale_workload":
                inc.analysis.action_parameters = {"replicas": 2}
            inc = plan_remediation(inc)
            decision = HumanDecision(decision="approved", approver="alice")
            inc = record_decision(inc, decision)
            k8s = _fake_k8s()
            inc, result = execute(inc, k8s)
            assert result.success is True, f"{action} failed"
            assert inc.state == IncidentState.EXECUTED


# ──────────────────────────────────────────────────────────────────────────────
# Verification
# ──────────────────────────────────────────────────────────────────────────────

class TestVerification:
    def _executed_incident(self, inc_id: str = "INC-V-1") -> Incident:
        inc = _approved_incident(inc_id)
        inc, _ = execute(inc, _fake_k8s())
        return inc

    def test_both_signals_pass_resolves(self):
        inc = self._executed_incident("INC-V-PASS")
        inc, result = verify(inc, _fake_reader(rollout_ok=True, health_ok=True))
        assert result.outcome == "PASS"
        assert inc.state == IncidentState.RESOLVED

    def test_rollout_fail_does_not_resolve(self):
        inc = self._executed_incident("INC-V-ROLLOUT-FAIL")
        inc, result = verify(inc, _fake_reader(rollout_ok=False, health_ok=True))
        assert result.outcome == "FAIL"
        assert inc.state == IncidentState.VERIFICATION_FAILED
        assert any(not s.passed and s.name == "rollout_healthy" for s in result.signals)

    def test_health_fail_does_not_resolve(self):
        inc = self._executed_incident("INC-V-HEALTH-FAIL")
        inc, result = verify(inc, _fake_reader(rollout_ok=True, health_ok=False))
        assert result.outcome == "FAIL"
        assert inc.state == IncidentState.VERIFICATION_FAILED
        assert any(not s.passed and s.name == "health_endpoint" for s in result.signals)

    def test_tool_error_inconclusive(self):
        inc = self._executed_incident("INC-V-TOOL-ERR")
        reader = MagicMock()
        reader.get_workload_status.side_effect = RuntimeError("k8s timeout")
        reader.get_application_health.return_value = {"healthy": True, "status_code": 200}
        inc, result = verify(inc, reader)
        assert result.outcome == "INCONCLUSIVE"
        assert inc.state == IncidentState.VERIFICATION_FAILED

    def test_verify_on_wrong_state_raises(self):
        inc = Incident(incident_id="INC-V-BAD", state=IncidentState.APPROVED)
        inc.plan = RemediationPlan(
            action=AllowedAction.restart_deployment, target="svc"
        )
        with pytest.raises(ValueError, match="Cannot verify"):
            verify(inc, _fake_reader())

    def test_verification_written_to_audit_log(self):
        inc = self._executed_incident("INC-V-LOG")
        inc, result = verify(inc, _fake_reader())
        verify_entries = [e for e in inc.audit_log if e.get("step") == "verification"]
        assert len(verify_entries) == 1
        assert verify_entries[0]["outcome"] == result.outcome


# ──────────────────────────────────────────────────────────────────────────────
# Audit / record writing
# ──────────────────────────────────────────────────────────────────────────────

class TestAudit:
    def test_write_record_creates_file(self, tmp_path: Path):
        inc = _approved_incident("INC-AUDIT-1")
        path = write_record(inc, records_dir=tmp_path)
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["incident_id"] == "INC-AUDIT-1"

    def test_record_is_valid_incident_record(self, tmp_path: Path):
        inc = _approved_incident("INC-AUDIT-2")
        path = write_record(inc, records_dir=tmp_path)
        record = IncidentRecord.model_validate_json(path.read_text())
        assert record.incident_id == "INC-AUDIT-2"
        assert record.human_decision == "approved"

    def test_rejected_record_contains_feedback(self, tmp_path: Path):
        inc = _analysed_incident("INC-AUDIT-REJ")
        inc = plan_remediation(inc)
        decision = HumanDecision(
            decision="rejected", approver="eve", feedback="Deliberate."
        )
        inc = record_decision(inc, decision)
        path = write_record(inc, records_dir=tmp_path)
        record = IncidentRecord.model_validate_json(path.read_text())
        assert record.rejection_feedback == "Deliberate."
        assert record.executed is False

    def test_no_overwrite_on_duplicate(self, tmp_path: Path):
        inc = _approved_incident("INC-AUDIT-DUP")
        p1 = write_record(inc, records_dir=tmp_path)
        p2 = write_record(inc, records_dir=tmp_path)
        assert p1 != p2  # second write gets a timestamp suffix


# ──────────────────────────────────────────────────────────────────────────────
# End-to-end pipeline
# ──────────────────────────────────────────────────────────────────────────────

class TestPipeline:
    def _bob_patch(self, raw: dict | None = None, ok: bool = True):
        """Return a mock that replaces agent.reasoning.bob_analyze."""
        from agent.bob import BobResult
        result = MagicMock(spec=BobResult)
        result.ok = ok
        result.analysis = raw
        result.error = None if ok else "Bob unavailable"
        result.audit_entry.return_value = {"stage": "BOB", "ok": ok}
        return result

    def test_happy_path_resolves(self, tmp_path):
        raw = {
            "schema_version": "1.0",
            "analysis_source": "ibm-bob",
            "hypotheses": [
                {
                    "rank": 1, "statement": "bad image", "confidence": "high",
                    "confidence_reason": "3 sources",
                    "supporting_evidence": ["pod 0/1"],
                    "contradicting_evidence": ["none found in available evidence"],
                    "cheapest_next_check": "compare images",
                }
            ],
            "root_cause": {"statement": "Regression", "confidence": "high", "is_inference": True},
            "recommended_action": "rollback_deployment",
            "action_target": "ticket-booking",
            "action_parameters": {"to_revision": 3},
            "reason": "Rollback to last healthy.",
            "risk_explanation": "Medium.",
            "requires_human_approval": True,
        }
        mock_result = self._bob_patch(raw=raw)
        decision = HumanDecision(decision="approved", approver="alice")

        with patch("agent.reasoning.bob_analyze", return_value=mock_result):
            incident = run_full_pipeline(
                tickets=[_ticket("T-1"), _ticket("T-2")],
                evidence=_evidence(),
                human_decision=decision,
                kubernetes=_fake_k8s(),
                reader=_fake_reader(),
                incident_id="INC-E2E-HAPPY",
                persist=False,
            )

        assert incident.state == IncidentState.RESOLVED
        assert incident.verification.outcome == "PASS"
        assert incident.execution.success is True

    def test_rejection_stops_before_execution(self, tmp_path):
        raw = {
            "schema_version": "1.0",
            "analysis_source": "ibm-bob",
            "hypotheses": [
                {
                    "rank": 1, "statement": "bad image", "confidence": "high",
                    "confidence_reason": "ok",
                    "supporting_evidence": [],
                    "contradicting_evidence": [],
                    "cheapest_next_check": "check",
                }
            ],
            "root_cause": {"statement": "x", "confidence": "high", "is_inference": True},
            "recommended_action": "restart_deployment",
            "action_target": "ticket-booking",
            "action_parameters": {},
            "reason": "Restart fixes it.",
            "risk_explanation": "Low.",
            "requires_human_approval": True,
        }
        mock_result = self._bob_patch(raw=raw)
        decision = HumanDecision(
            decision="rejected", approver="bob", feedback="Planned maintenance."
        )
        k8s = _fake_k8s()

        with patch("agent.reasoning.bob_analyze", return_value=mock_result):
            incident = run_full_pipeline(
                tickets=[_ticket("T-1")],
                evidence=_evidence(),
                human_decision=decision,
                kubernetes=k8s,
                reader=_fake_reader(),
                incident_id="INC-E2E-REJECT",
                persist=False,
            )

        assert incident.state == IncidentState.FEEDBACK_RECORDED
        assert incident.execution is None
        # k8s was never called
        k8s.rollback_deployment.assert_not_called()
        k8s.restart_deployment.assert_not_called()

    def test_bob_unavailable_stops_pipeline(self):
        mock_result = self._bob_patch(ok=False)
        decision = HumanDecision(decision="approved", approver="alice")

        with patch("agent.reasoning.bob_analyze", return_value=mock_result):
            incident = run_full_pipeline(
                tickets=[_ticket("T-1")],
                evidence=_evidence(),
                human_decision=decision,
                kubernetes=_fake_k8s(),
                reader=_fake_reader(),
                incident_id="INC-E2E-BOB-DOWN",
                persist=False,
            )

        assert incident.state == IncidentState.BOB_UNAVAILABLE
        assert incident.plan is None
        assert incident.execution is None

    def test_verification_fail_does_not_resolve(self):
        raw = {
            "schema_version": "1.0",
            "analysis_source": "ibm-bob",
            "hypotheses": [
                {
                    "rank": 1, "statement": "bad image", "confidence": "high",
                    "confidence_reason": "ok",
                    "supporting_evidence": [],
                    "contradicting_evidence": [],
                    "cheapest_next_check": "check",
                }
            ],
            "root_cause": {"statement": "x", "confidence": "high", "is_inference": True},
            "recommended_action": "rollback_deployment",
            "action_target": "ticket-booking",
            "action_parameters": {"to_revision": 2},
            "reason": "Rollback.", "risk_explanation": "Low.",
            "requires_human_approval": True,
        }
        mock_result = self._bob_patch(raw=raw)
        decision = HumanDecision(decision="approved", approver="alice")

        with patch("agent.reasoning.bob_analyze", return_value=mock_result):
            incident = run_full_pipeline(
                tickets=[_ticket("T-1")],
                evidence=_evidence(),
                human_decision=decision,
                kubernetes=_fake_k8s(),
                reader=_fake_reader(rollout_ok=False, health_ok=False),
                incident_id="INC-E2E-VERIFY-FAIL",
                persist=False,
            )

        assert incident.state == IncidentState.VERIFICATION_FAILED
        assert incident.verification.outcome == "FAIL"
        assert incident.execution.success is True  # execution worked; verification caught it
