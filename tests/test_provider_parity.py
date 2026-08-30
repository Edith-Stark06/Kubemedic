"""
Provider registry, and execution parity across engines.

The parity tests are the point of this file. Four providers now feed the same
pipeline, and the risk of a pluggable reasoning layer is that they diverge
quietly: one returns success on a 401, another forgets to stamp provenance, a
third lets unparseable output through as an empty analysis. Any of those puts a
fabricated diagnosis in front of a human.

So every provider is driven through identical fixtures and asserted to behave
identically. The transport differs; nothing else may.
"""
from __future__ import annotations

import json

import pytest

from agent.models import BobAnalysis
from agent.providers import (
    get_provider,
    provider_names,
    provider_status,
    reset_provider_cache,
)
from agent.providers.anthropic import AnthropicProvider
from agent.providers.ibm_bob import IBMBobProvider
from agent.providers.manual import ManualProvider
from agent.providers.watsonx import WatsonxProvider

VALID_ANALYSIS = {
    "schema_version": "1.0",
    "hypotheses": [{
        "rank": 1,
        "statement": "Revision 31 ships an image that never passes readiness",
        "confidence": "high",
        "confidence_reason": "rollout history and pod readiness agree",
        "supporting_evidence": ["pod 0/1 Ready on ticketbooking:1.1"],
        "contradicting_evidence": ["none found"],
    }],
    "root_cause": {
        "statement": "Image regression in revision 31",
        "confidence": "high",
        "is_inference": True,
    },
    "recommended_action": "rollback_deployment",
    "action_target": "ticket-booking",
    "action_parameters": {"to_revision": 30},
    "reason": "Return to the last revision known to pass readiness",
}

EVIDENCE = {"deployment_name": "ticket-booking", "namespace": "opspilot"}
TICKETS = [{"ticket_id": "TKT-1", "named_workload": "ticket-booking"}]

FENCE = "``" + "`"


@pytest.fixture(autouse=True)
def clean_registry():
    reset_provider_cache()
    yield
    reset_provider_cache()


def _configured(cls, monkeypatch, **env):
    """Build a provider with credentials present, transport not yet stubbed."""
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return cls()


def all_providers(monkeypatch, tmp_path):
    """Every provider, configured, ready to have its transport stubbed."""
    analysis_file = tmp_path / "bob-analysis.json"
    analysis_file.write_text(json.dumps(VALID_ANALYSIS), encoding="utf-8")
    return [
        _configured(IBMBobProvider, monkeypatch,
                    KUBEMEDIC_BOB_API_KEY="k", KUBEMEDIC_BOB_AGENT_ID="a"),
        _configured(WatsonxProvider, monkeypatch,
                    KUBEMEDIC_WATSONX_API_KEY="k",
                    KUBEMEDIC_WATSONX_PROJECT_ID="p"),
        _configured(AnthropicProvider, monkeypatch,
                    KUBEMEDIC_ANTHROPIC_API_KEY="k"),
        ManualProvider(path=str(analysis_file)),
    ]


class TestRegistry:
    def test_every_name_resolves(self):
        for name in provider_names():
            reset_provider_cache()
            assert get_provider(name) is not None

    def test_aliases(self):
        reset_provider_cache()
        assert get_provider("bob").id == "ibm-bob"
        reset_provider_cache()
        assert get_provider("claude").id == "anthropic"

    def test_default_is_ibm_bob(self, monkeypatch):
        """KubeMedic is an IBM Bob project. The default must say so."""
        monkeypatch.delenv("KUBEMEDIC_REASONING_PROVIDER", raising=False)
        assert get_provider().id == "ibm-bob"

    def test_env_selects_the_provider(self, monkeypatch):
        monkeypatch.setenv("KUBEMEDIC_REASONING_PROVIDER", "watsonx")
        assert get_provider().id == "watsonx"

    def test_unknown_provider_is_a_hard_error(self, monkeypatch):
        """
        Never silently fall back. A misspelled name must not leave the system
        looking configured while serving a different engine.
        """
        monkeypatch.setenv("KUBEMEDIC_REASONING_PROVIDER", "gemini")
        with pytest.raises(SystemExit, match="Unknown reasoning provider"):
            get_provider()

    def test_status_lists_every_provider_without_network(self):
        status = provider_status()
        listed = {entry["provider"] for entry in status["providers"]}
        assert {"watsonx", "anthropic"} <= listed
        assert status["default"] == "ibm-bob"
        assert "secrets_backend" in status


class TestParitySuccess:
    def test_all_providers_produce_an_equivalent_analysis(self, monkeypatch, tmp_path):
        results = []
        for provider in all_providers(monkeypatch, tmp_path):
            monkeypatch.setattr(
                type(provider), "_invoke",
                lambda self, prompt: json.dumps(VALID_ANALYSIS),
            )
            results.append((provider.id, provider.analyze(EVIDENCE, TICKETS)))

        for pid, result in results:
            assert result.ok, pid
            analysis = BobAnalysis.from_raw(result.analysis)
            assert analysis.recommended_action.value == "rollback_deployment", pid
            assert analysis.action_target == "ticket-booking", pid
            assert analysis.root_cause.statement == "Image regression in revision 31", pid

    def test_provenance_is_stamped_not_trusted(self, monkeypatch):
        """
        A provider must not be able to claim it is a different engine. The id
        is stamped by the base class after the call, overriding whatever the
        model said.
        """
        lying = dict(VALID_ANALYSIS, analysis_source="ibm-bob")
        provider = _configured(WatsonxProvider, monkeypatch,
                               KUBEMEDIC_WATSONX_API_KEY="k",
                               KUBEMEDIC_WATSONX_PROJECT_ID="p")
        monkeypatch.setattr(
            WatsonxProvider, "_invoke", lambda self, prompt: json.dumps(lying)
        )
        result = provider.analyze(EVIDENCE, TICKETS)
        assert result.analysis["analysis_source"] == "watsonx"

    def test_all_providers_accept_fenced_output(self, monkeypatch, tmp_path):
        fenced = FENCE + "json\n" + json.dumps(VALID_ANALYSIS) + "\n" + FENCE
        for provider in all_providers(monkeypatch, tmp_path):
            monkeypatch.setattr(type(provider), "_invoke", lambda self, p: fenced)
            assert provider.analyze(EVIDENCE, TICKETS).ok, provider.id

    def test_all_providers_accept_prose_wrapped_output(self, monkeypatch, tmp_path):
        wrapped = "Here is the analysis:\n" + json.dumps(VALID_ANALYSIS) + "\nDone."
        for provider in all_providers(monkeypatch, tmp_path):
            monkeypatch.setattr(type(provider), "_invoke", lambda self, p: wrapped)
            assert provider.analyze(EVIDENCE, TICKETS).ok, provider.id


class TestParityFailure:
    """
    Every failure mode, on every provider, converges on one outcome: ok=False,
    no analysis, an error a human can read, and an audit entry reading
    "unavailable".
    """

    @pytest.mark.parametrize("boom", [
        TimeoutError("slow"),
        RuntimeError("authentication failed"),
        ConnectionError("refused"),
    ])
    def test_transport_failures(self, monkeypatch, tmp_path, boom):
        for provider in all_providers(monkeypatch, tmp_path):
            def raiser(self, prompt, _b=boom):
                raise _b
            monkeypatch.setattr(type(provider), "_invoke", raiser)
            result = provider.analyze(EVIDENCE, TICKETS)
            assert not result.ok, provider.id
            assert result.analysis is None, provider.id
            assert result.error, provider.id
            assert result.audit_entry()["analysis_source"] == "unavailable", provider.id

    def test_unparseable_output(self, monkeypatch, tmp_path):
        for provider in all_providers(monkeypatch, tmp_path):
            monkeypatch.setattr(
                type(provider), "_invoke", lambda self, p: "I could not tell."
            )
            result = provider.analyze(EVIDENCE, TICKETS)
            assert not result.ok, provider.id
            assert result.audit_entry()["analysis_source"] == "unavailable", provider.id

    def test_missing_credentials(self, monkeypatch):
        for key in (
            "KUBEMEDIC_BOB_API_KEY", "KUBEMEDIC_BOB_AGENT_ID",
            "KUBEMEDIC_WATSONX_API_KEY", "KUBEMEDIC_WATSONX_PROJECT_ID",
            "KUBEMEDIC_ANTHROPIC_API_KEY",
        ):
            monkeypatch.delenv(key, raising=False)
        for cls in (IBMBobProvider, WatsonxProvider, AnthropicProvider):
            result = cls().analyze(EVIDENCE, TICKETS)
            assert not result.ok, cls.__name__
            assert "unset" in (result.error or ""), cls.__name__

    def test_a_non_allowlisted_action_is_refused_downstream(
        self, monkeypatch, tmp_path
    ):
        """
        The provider layer does not validate content -- BobAnalysis does. This
        asserts the boundary holds for every engine, so no provider can smuggle
        an arbitrary action through.
        """
        bad = dict(VALID_ANALYSIS, recommended_action="kubectl delete ns opspilot")
        for provider in all_providers(monkeypatch, tmp_path):
            monkeypatch.setattr(
                type(provider), "_invoke", lambda self, p: json.dumps(bad)
            )
            result = provider.analyze(EVIDENCE, TICKETS)
            assert result.ok, provider.id          # transport succeeded
            with pytest.raises(ValueError, match="allowlist"):
                BobAnalysis.from_raw(result.analysis)


class TestUsageAccounting:
    def test_counters_track_calls_and_failures(self, monkeypatch):
        provider = _configured(AnthropicProvider, monkeypatch,
                               KUBEMEDIC_ANTHROPIC_API_KEY="k")
        monkeypatch.setattr(
            AnthropicProvider, "_invoke", lambda self, p: json.dumps(VALID_ANALYSIS)
        )
        provider.analyze(EVIDENCE, TICKETS)

        def boom(self, prompt):
            raise TimeoutError("slow")

        monkeypatch.setattr(AnthropicProvider, "_invoke", boom)
        provider.analyze(EVIDENCE, TICKETS)

        usage = provider.usage()
        assert usage["calls"] == 2
        assert usage["successes"] == 1
        assert usage["failures"]["timeout"] == 1
        assert usage["last_error"]

    def test_usage_never_leaks_a_credential(self, monkeypatch):
        secret = "sk-ant-supersecretvalue123456"
        provider = _configured(AnthropicProvider, monkeypatch,
                               KUBEMEDIC_ANTHROPIC_API_KEY=secret)
        assert secret not in json.dumps(provider.usage())

    def test_invocation_never_contains_the_prompt_or_a_key(self, monkeypatch):
        provider = _configured(IBMBobProvider, monkeypatch,
                               KUBEMEDIC_BOB_API_KEY="supersecretkey123456",
                               KUBEMEDIC_BOB_AGENT_ID="agent-1")
        monkeypatch.setattr(
            IBMBobProvider, "_invoke", lambda self, p: json.dumps(VALID_ANALYSIS)
        )
        result = provider.analyze(EVIDENCE, TICKETS)
        rendered = json.dumps(result.invocation)
        assert "supersecretkey123456" not in rendered
        assert "ticket-booking" not in rendered   # the prompt carries cluster detail
