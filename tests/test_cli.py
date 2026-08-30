"""
CLI orchestration.

The CLI must give the same answers the API gives. A second entry point that is
more permissive than the first would be a way around the safety model, so these
tests check the refusals rather than the happy paths: a rejection with no
reason, an execution without approval, an unknown provider.

Exit codes carry meaning -- 0 success, 1 failure, 2 refused by a guard -- so a
script can tell a refusal from a crash.
"""
from __future__ import annotations

import json

import pytest

from agent import cli
from agent.models import (
    AllowedAction,
    EvidenceSnapshot,
    Incident,
    IncidentState,
    RemediationPlan,
    TicketReference,
)


@pytest.fixture(autouse=True)
def clean_store():
    cli._INCIDENTS.clear()
    yield
    cli._INCIDENTS.clear()


def _pending_incident(incident_id="INC-CLI-001"):
    incident = Incident(
        incident_id=incident_id,
        state=IncidentState.EVIDENCE_COLLECTED,
        tickets=[TicketReference(ticket_id="TKT-1", named_workload="ticket-booking")],
        evidence=EvidenceSnapshot(deployment_name="ticket-booking", namespace="opspilot"),
    )
    incident.plan = RemediationPlan(
        action=AllowedAction.rollback_deployment, target="ticket-booking"
    )
    incident.transition(IncidentState.PENDING_APPROVAL)
    cli._INCIDENTS[incident_id] = incident
    return incident_id


def run(argv):
    args = cli.build_parser().parse_args(argv)
    if not hasattr(args, "message"):
        args.message = None
    return args.fn(args, cli.Out(as_json=False))


class TestParser:
    def test_every_command_is_reachable(self):
        for argv in (
            ["status"], ["providers"], ["watch"], ["tickets"],
            ["incident", "new"], ["incident", "list"], ["incident", "show", "INC-1"],
            ["approve", "INC-1"], ["reject", "INC-1"], ["revise", "INC-1"],
            ["execute", "INC-1"],
        ):
            assert cli.build_parser().parse_args(argv).fn is not None

    def test_json_flag_is_global(self):
        assert cli.build_parser().parse_args(["--json", "status"]).json is True


class TestRejectionRequiresAReason:
    def test_reject_without_a_reason_is_refused(self, capsys):
        incident_id = _pending_incident()
        assert run(["reject", incident_id]) == cli.EXIT_REFUSED
        assert "must state why" in capsys.readouterr().err
        # And nothing was recorded on the incident.
        assert cli._INCIDENTS[incident_id].state == IncidentState.PENDING_APPROVAL

    @pytest.mark.parametrize("blank", ["", "   ", "\t"])
    def test_whitespace_is_not_a_reason(self, blank):
        incident_id = _pending_incident()
        assert run(["reject", incident_id, "-m", blank]) == cli.EXIT_REFUSED

    def test_reject_with_a_reason_is_recorded(self):
        incident_id = _pending_incident()
        assert run(["reject", incident_id, "-m", "Roll back instead."]) == cli.EXIT_OK
        incident = cli._INCIDENTS[incident_id]
        assert incident.state == IncidentState.FEEDBACK_RECORDED
        assert incident.feedback_history == ["Roll back instead."]

    def test_approval_needs_no_reason(self):
        incident_id = _pending_incident()
        assert run(["approve", incident_id]) == cli.EXIT_OK
        assert cli._INCIDENTS[incident_id].state == IncidentState.APPROVED


class TestGuardsRefuseRatherThanCrash:
    def test_execute_without_approval(self, capsys, monkeypatch):
        """
        The guard lives in the executor, not the CLI -- so this proves the CLI
        cannot route around it, and reports the refusal as exit 2.
        """
        incident_id = _pending_incident()
        monkeypatch.setattr("agent.k8s_client.LiveCluster", lambda: object())
        assert run(["execute", incident_id]) == cli.EXIT_REFUSED
        assert "requires APPROVED" in capsys.readouterr().err

    def test_execute_after_rejection(self, capsys, monkeypatch):
        incident_id = _pending_incident()
        run(["reject", incident_id, "-m", "not now"])
        monkeypatch.setattr("agent.k8s_client.LiveCluster", lambda: object())
        assert run(["execute", incident_id]) == cli.EXIT_REFUSED

    def test_unknown_incident_is_a_failure_not_a_traceback(self, capsys):
        assert run(["approve", "INC-nope"]) == cli.EXIT_FAIL
        assert "not in this session" in capsys.readouterr().err

    def test_revise_without_a_rejection_is_refused(self, capsys):
        incident_id = _pending_incident()
        assert run(["revise", incident_id]) == cli.EXIT_REFUSED

    def test_unknown_provider_exits_rather_than_defaulting(self, monkeypatch):
        """
        A misspelled engine must not silently fall back to another one.

        The guard is in get_provider(), which `status` goes through. It is
        deliberately NOT in provider_status(): that builds a listing and must
        never raise, or one broken provider would blank the whole health view.
        """
        monkeypatch.setenv("KUBEMEDIC_REASONING_PROVIDER", "gemini")
        from agent.providers import reset_provider_cache
        reset_provider_cache()
        try:
            with pytest.raises(SystemExit, match="Unknown reasoning provider"):
                run(["status"])
        finally:
            reset_provider_cache()

    def test_status_listing_survives_a_broken_provider(self, monkeypatch):
        """The health view must degrade, not disappear."""
        monkeypatch.setenv("KUBEMEDIC_REASONING_PROVIDER", "gemini")
        from agent.providers import provider_status, reset_provider_cache
        reset_provider_cache()
        try:
            assert provider_status()["providers"]        # still lists the known ones
        finally:
            reset_provider_cache()


class TestOutput:
    def test_json_mode_emits_parseable_output(self, capsys, monkeypatch):
        monkeypatch.setattr("agent.providers.provider_status",
                            lambda: {"active": "ibm-bob", "default": "ibm-bob",
                                     "secrets_backend": "env", "providers": []})
        args = cli.build_parser().parse_args(["--json", "providers"])
        args.fn(args, cli.Out(as_json=True))
        assert json.loads(capsys.readouterr().out)["active"] == "ibm-bob"

    def test_text_mode_prints_nothing_machine_readable(self, capsys, monkeypatch):
        monkeypatch.setattr("agent.providers.provider_status",
                            lambda: {"active": "ibm-bob", "default": "ibm-bob",
                                     "secrets_backend": "env", "providers": []})
        args = cli.build_parser().parse_args(["providers"])
        args.fn(args, cli.Out(as_json=False))
        out = capsys.readouterr().out
        assert "reasoning providers" in out
        with pytest.raises(json.JSONDecodeError):
            json.loads(out)
