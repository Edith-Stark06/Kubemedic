"""
The model chooses `action_target`; the evidence decides whether it is allowed.

A plan against any workload other than the one the incident is about must be
refused before a human is asked to approve it, and refused again by the
executor if one is somehow constructed by hand.
"""
from __future__ import annotations

import pytest

from agent.audit import record_decision
from agent.executor import execute
from agent.models import (
    AllowedAction,
    HumanDecision,
    IncidentState,
    RemediationPlan,
)
from agent.pipeline import plan_remediation
from tests.test_api import client, cluster  # noqa: F401  (fixtures)
from tests.test_lifecycle import (
    _analysed_incident,
    _approved_incident,
    _fake_k8s,
    _valid_analysis,
)


class TestPlanning:
    def test_matching_target_is_planned(self):
        inc = plan_remediation(_analysed_incident())
        assert inc.state == IncidentState.PENDING_APPROVAL
        assert inc.plan is not None
        assert inc.plan.target == "ticket-booking"

    def test_other_workload_is_refused_at_planning(self):
        inc = _analysed_incident()
        inc.analysis = _valid_analysis(target="payments-db")
        inc = plan_remediation(inc)

        assert inc.plan is None
        assert inc.state == IncidentState.ANALYSED
        refusal = [e for e in inc.audit_log if e.get("step") == "plan_refused"]
        assert len(refusal) == 1
        assert refusal[0]["proposed_target"] == "payments-db"
        assert refusal[0]["incident_workload"] == "ticket-booking"

    def test_refused_incident_cannot_be_approved(self):
        inc = _analysed_incident()
        inc.analysis = _valid_analysis(target="payments-db")
        inc = plan_remediation(inc)

        with pytest.raises(ValueError, match="no remediation plan"):
            record_decision(inc, HumanDecision(decision="approved", approver="alice"))

    def test_refused_incident_cannot_be_rejected_into_a_revision_either(self):
        inc = _analysed_incident()
        inc.analysis = _valid_analysis(target="payments-db")
        inc = plan_remediation(inc)

        with pytest.raises(ValueError, match="no remediation plan"):
            record_decision(
                inc,
                HumanDecision(decision="rejected", approver="alice", feedback="no"),
            )


class TestExecutor:
    def test_hand_built_plan_with_wrong_target_is_refused(self):
        inc = _approved_incident()
        inc.plan = RemediationPlan(
            action=AllowedAction.restart_deployment, target="payments-db"
        )
        k8s = _fake_k8s()

        with pytest.raises(ValueError, match="not the workload"):
            execute(inc, k8s)

        k8s.restart_deployment.assert_not_called()
        k8s.rollback_deployment.assert_not_called()
        k8s.scale_workload.assert_not_called()
        assert inc.state == IncidentState.APPROVED
        assert inc.execution is None

    def test_matching_target_still_executes(self):
        inc = _approved_incident()
        k8s = _fake_k8s()
        inc, result = execute(inc, k8s)
        assert result.success
        k8s.rollback_deployment.assert_called_once()

    def test_incident_without_evidence_is_refused(self):
        inc = _approved_incident()
        inc.evidence = None
        k8s = _fake_k8s()
        with pytest.raises(ValueError, match="not the workload"):
            execute(inc, k8s)
        k8s.rollback_deployment.assert_not_called()


class TestNamespaceAllowlist:
    def test_disallowed_namespace_is_400(self, client, monkeypatch):  # noqa: F811
        monkeypatch.setenv("KUBEMEDIC_ALLOWED_NAMESPACES", "opspilot")
        r = client.post("/api/incidents", json={"namespace": "kube-system"})
        assert r.status_code == 400
        assert r.json()["detail"]["error"] == "namespace_not_allowed"

    def test_allowed_namespace_works(self, client, monkeypatch):  # noqa: F811
        monkeypatch.setenv("KUBEMEDIC_ALLOWED_NAMESPACES", "opspilot,staging")
        r = client.post("/api/incidents", json={"namespace": "staging"})
        assert r.status_code == 201

    def test_default_is_the_watched_namespace_only(self, client, monkeypatch):  # noqa: F811
        monkeypatch.delenv("KUBEMEDIC_ALLOWED_NAMESPACES", raising=False)
        assert client.post("/api/incidents", json={}).status_code == 201
        r = client.post("/api/incidents", json={"namespace": "somewhere-else"})
        assert r.status_code == 400


class TestFabricatedTickets:
    """A model that cites tickets it was never given is inventing evidence."""

    def _run(self, member_tickets):
        from unittest.mock import patch

        from agent.bob import BobResult
        from agent.models import EvidenceSnapshot, Incident
        from agent.reasoning import run_analysis
        from tests.test_lifecycle import _evidence, _ticket

        raw = {
            "schema_version": "1.0",
            "analysis_source": "ibm-bob",
            "correlation": {
                "master_incident_id": "INC-X",
                "member_tickets": member_tickets,
            },
            "hypotheses": [],
            "recommended_action": "rollback_deployment",
            "action_target": "ticket-booking",
            "action_parameters": {"to_revision": 3},
        }
        inc = Incident(
            incident_id="INC-X", state=IncidentState.EVIDENCE_COLLECTED,
            tickets=[_ticket("T-1")], evidence=_evidence(),
        )
        result = BobResult(ok=True, analysis=raw, raw_stdout="", invocation=["x"], duration_ms=1)
        with patch("agent.reasoning.bob_analyze", return_value=result):
            return run_analysis(inc)

    def test_real_ticket_ids_pass(self):
        inc, analysis = self._run(["T-1"])
        assert inc.state == IncidentState.ANALYSED
        assert analysis.recommended_action is not None

    def test_invented_ticket_ids_make_the_analysis_unavailable(self):
        inc, analysis = self._run(["T-1", "TKT-001", "TKT-002"])
        assert inc.state == IncidentState.BOB_UNAVAILABLE
        assert analysis.is_unavailable
        assert analysis.recommended_action is None
        rejected = [e for e in inc.audit_log if e.get("step") == "analysis_rejected"]
        assert rejected and rejected[0]["ticket_ids"] == ["TKT-001", "TKT-002"]

    def test_no_plan_can_follow_a_rejected_analysis(self):
        inc, _ = self._run(["TKT-999"])
        assert plan_remediation(inc).plan is None


class TestSaferDefaults:
    def test_fallback_to_another_vendor_is_opt_in(self, monkeypatch):
        from agent.providers import fallback_enabled

        monkeypatch.delenv("AI_FALLBACK_ENABLED", raising=False)
        assert fallback_enabled() is False
        monkeypatch.setenv("AI_FALLBACK_ENABLED", "true")
        assert fallback_enabled() is True

    def test_read_only_mcp_profile_does_not_start_the_ticket_writer(self, monkeypatch):
        from mcp_server.server import watcher_enabled

        monkeypatch.delenv("KUBEMEDIC_MCP_WATCHER", raising=False)
        assert watcher_enabled("evidence") is False
        assert watcher_enabled(None) is True

    def test_watcher_can_be_enabled_explicitly(self, monkeypatch):
        from mcp_server.server import watcher_enabled

        monkeypatch.setenv("KUBEMEDIC_MCP_WATCHER", "true")
        assert watcher_enabled("evidence") is True

    def test_watcher_follows_the_configured_workload(self, monkeypatch):
        from mcp_server.watcher import KubeWatcher

        monkeypatch.setenv("KUBEMEDIC_NAMESPACE", "shop")
        monkeypatch.setenv("KUBEMEDIC_DEPLOYMENT", "checkout")
        monkeypatch.delenv("KUBEMEDIC_SERVICE", raising=False)
        w = KubeWatcher()
        assert (w.namespace, w.deployment, w.service) == ("shop", "checkout", "checkout")
