"""
Host-session provider and `auto` resolution.

The point of this provider is that a machine with no API keys still has a
working reasoning path: the agentic IDE already sitting in the workspace
answers, through the filesystem.

The honesty risk is the whole design. It must not let a stale answer be
replayed into a later incident, must not claim to be an engine it is not, and
must validate an IDE's answer exactly as strictly as a headless one.
"""
from __future__ import annotations

import json

import pytest

from agent.models import BobAnalysis
from agent.providers import get_provider, resolve_auto, reset_provider_cache
from agent.providers.host import HostSessionProvider, detect_host

ANALYSIS = {
    "schema_version": "1.0",
    "hypotheses": [{
        "rank": 1,
        "statement": "The newest revision fails readiness",
        "confidence": "high",
        "confidence_reason": "rollout history and pod readiness agree",
    }],
    "root_cause": {"statement": "Image regression", "confidence": "high",
                   "is_inference": True},
    "recommended_action": "rollback_deployment",
    "action_target": "ticket-booking",
}

EVIDENCE = {"deployment_name": "ticket-booking"}


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    reset_provider_cache()
    # Every credential, not just the IBM ones. agent/secrets.py loads .env
    # into the process environment, so a developer with a real key would
    # otherwise see these "nothing is configured" tests resolve to whatever
    # they happen to have set.
    for key in ("KUBEMEDIC_BOB_API_KEY", "KUBEMEDIC_BOB_AGENT_ID",
                "KUBEMEDIC_WATSONX_API_KEY", "KUBEMEDIC_WATSONX_PROJECT_ID",
                "KUBEMEDIC_ANTHROPIC_API_KEY",
                "KUBEMEDIC_GEMINI_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    yield
    reset_provider_cache()


def provider(tmp_path, **env):
    return HostSessionProvider(workdir=tmp_path / ".kubemedic")


class TestHostDetection:
    def test_bob_ide_is_stamped_as_ibm_bob(self, monkeypatch):
        """The Bob IDE really is Bob -- the provenance should say so."""
        monkeypatch.setenv("IBM_BOB_SESSION", "1")
        assert detect_host()[0] == "ibm-bob"

    def test_claude_code(self, monkeypatch):
        monkeypatch.delenv("IBM_BOB_SESSION", raising=False)
        monkeypatch.setenv("CLAUDECODE", "1")
        assert detect_host()[0] == "claude-code"

    def test_antigravity(self, monkeypatch):
        monkeypatch.delenv("CLAUDECODE", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_ENTRYPOINT", raising=False)
        monkeypatch.setenv("ANTIGRAVITY", "1")
        assert detect_host()[0] == "antigravity"

    def test_override(self, monkeypatch):
        monkeypatch.setenv("KUBEMEDIC_HOST_KIND", "ibm-bob")
        assert detect_host()[0] == "ibm-bob"

    def test_always_configured(self, tmp_path):
        """It needs no credential -- only somebody to answer."""
        assert provider(tmp_path).is_configured()[0] is True


class TestHandoff:
    def test_first_call_writes_a_request_and_fails_clearly(self, tmp_path):
        p = provider(tmp_path)
        result = p.analyze(EVIDENCE, [])
        assert result.ok is False
        assert p.request_path.is_file()
        assert "write its JSON analysis" in result.error

    def test_the_request_carries_the_real_prompt(self, tmp_path):
        p = provider(tmp_path)
        p.analyze(EVIDENCE, [{"ticket_id": "TKT-1"}], ["roll back instead"])
        text = p.request_path.read_text(encoding="utf-8")
        assert "ticket-booking" in text
        assert "rollback_deployment" in text          # the allowlist
        assert "roll back instead" in text            # human feedback carried

    def test_second_call_consumes_the_answer(self, tmp_path):
        p = provider(tmp_path)
        p.analyze(EVIDENCE, [])                       # writes the request
        p.response_path.write_text(json.dumps(ANALYSIS), encoding="utf-8")

        result = p.analyze(EVIDENCE, [])
        assert result.ok
        assert BobAnalysis.from_raw(result.analysis).action_target == "ticket-booking"

    def test_an_answer_is_consumed_only_once(self, tmp_path):
        """A stale analysis must never be replayed into a later incident."""
        p = provider(tmp_path)
        p.analyze(EVIDENCE, [])
        p.response_path.write_text(json.dumps(ANALYSIS), encoding="utf-8")
        assert p.analyze(EVIDENCE, []).ok
        assert p.response_path.exists() is False
        assert p.analyze(EVIDENCE, []).ok is False

    def test_an_answer_older_than_the_request_is_ignored(self, tmp_path):
        import os, time
        p = provider(tmp_path)
        p.dir.mkdir(parents=True, exist_ok=True)
        p.response_path.write_text(json.dumps(ANALYSIS), encoding="utf-8")
        old = time.time() - 600
        os.utime(p.response_path, (old, old))
        result = p.analyze(EVIDENCE, [])
        assert result.ok is False, "an answer to an older request was consumed"


class TestTheIDEAnswerIsValidatedJustAsStrictly:
    def test_a_non_allowlisted_action_is_refused_downstream(self, tmp_path):
        p = provider(tmp_path)
        p.analyze(EVIDENCE, [])
        p.response_path.write_text(
            json.dumps(dict(ANALYSIS, recommended_action="kubectl delete ns opspilot")),
            encoding="utf-8",
        )
        result = p.analyze(EVIDENCE, [])
        assert result.ok                                   # transport fine
        with pytest.raises(ValueError, match="allowlist"):
            BobAnalysis.from_raw(result.analysis)

    def test_unparseable_answer_is_unavailable_not_success(self, tmp_path):
        p = provider(tmp_path)
        p.analyze(EVIDENCE, [])
        p.response_path.write_text("I think roll it back?", encoding="utf-8")
        result = p.analyze(EVIDENCE, [])
        assert result.ok is False
        assert result.audit_entry()["analysis_source"] == "unavailable"

    def test_provenance_is_the_detected_host_not_the_model_claim(self, tmp_path, monkeypatch):
        monkeypatch.setenv("KUBEMEDIC_HOST_KIND", "claude-code")
        p = provider(tmp_path)
        p.analyze(EVIDENCE, [])
        p.response_path.write_text(
            json.dumps(dict(ANALYSIS, analysis_source="watsonx")), encoding="utf-8"
        )
        assert p.analyze(EVIDENCE, []).analysis["analysis_source"] == "claude-code"


class TestAutoResolution:
    def test_falls_through_to_the_host_when_nothing_is_configured(self, monkeypatch):
        """
        The reason `auto` exists: a fresh clone with no credentials must still
        have a working reasoning path.
        """
        monkeypatch.setenv("KUBEMEDIC_MANUAL_ANALYSIS_FILE", "definitely-not-here.json")
        assert resolve_auto() == "host"

    def test_prefers_ibm_bob_when_it_is_configured(self, monkeypatch):
        """IBM engines come first -- this is an IBM Bob project."""
        monkeypatch.setenv("KUBEMEDIC_BOB_API_KEY", "k")
        monkeypatch.setenv("KUBEMEDIC_BOB_AGENT_ID", "a")
        assert resolve_auto() == "ibm-bob"

    def test_prefers_watsonx_over_anthropic(self, monkeypatch):
        monkeypatch.setenv("KUBEMEDIC_WATSONX_API_KEY", "k")
        monkeypatch.setenv("KUBEMEDIC_WATSONX_PROJECT_ID", "p")
        monkeypatch.setenv("KUBEMEDIC_ANTHROPIC_API_KEY", "k")
        assert resolve_auto() == "watsonx"

    def test_auto_is_the_default(self, monkeypatch):
        monkeypatch.delenv("KUBEMEDIC_REASONING_PROVIDER", raising=False)
        monkeypatch.setenv("KUBEMEDIC_MANUAL_ANALYSIS_FILE", "definitely-not-here.json")
        assert get_provider().id in ("claude-code", "ibm-bob", "antigravity", "host")
