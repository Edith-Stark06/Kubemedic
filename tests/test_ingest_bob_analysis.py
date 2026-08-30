"""
Guards on the Bob-analysis ingest path.

scripts/ingest_bob_analysis.py exists so an analysis produced in an interactive
IBM Bob session can drive the real pipeline. That is a legitimate route only
while the input is validated exactly as strictly as the headless REST path --
otherwise it becomes a way to hand-write an analysis and have the audit record
claim Bob made it.

Validation cannot establish provenance; only the operator can. These tests
cover what validation *can* do: refuse malformed input, refuse anything that
does not claim to be Bob's, and refuse an action outside the allowlist.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from ingest_bob_analysis import load_analysis  # noqa: E402

VALID = {
    "schema_version": "1.0",
    "analysis_source": "ibm-bob",
    "hypotheses": [{
        "rank": 1,
        "statement": "The newest revision fails readiness",
        "confidence": "high",
        "confidence_reason": "rollout history and pod readiness agree",
    }],
    "root_cause": {
        "statement": "Regression in the latest revision",
        "confidence": "high",
        "is_inference": True,
    },
    "recommended_action": "rollback_deployment",
    "action_target": "ticket-booking",
}


def _write(tmp_path, payload, name="a.json"):
    p = tmp_path / name
    p.write_text(
        payload if isinstance(payload, str) else json.dumps(payload),
        encoding="utf-8",
    )
    return p


class TestAccepts:
    def test_valid_analysis(self, tmp_path):
        analysis = load_analysis(_write(tmp_path, VALID))
        assert analysis.analysis_source == "ibm-bob"
        assert analysis.recommended_action.value == "rollback_deployment"

    def test_fenced_json_from_a_chat_window(self, tmp_path):
        """Copying out of a chat usually brings the ``` markers along."""
        fenced = "```json\n" + json.dumps(VALID) + "\n```"
        assert load_analysis(_write(tmp_path, fenced)).action_target == "ticket-booking"

    def test_null_recommendation_is_valid(self, tmp_path):
        """Bob is allowed to say no allowlisted action fits."""
        payload = dict(VALID, recommended_action=None, action_target=None)
        assert load_analysis(_write(tmp_path, payload)).recommended_action is None

    def test_source_defaults_to_ibm_bob_when_absent(self, tmp_path):
        payload = {k: v for k, v in VALID.items() if k != "analysis_source"}
        assert load_analysis(_write(tmp_path, payload)).analysis_source == "ibm-bob"


class TestRefuses:
    def test_action_outside_the_allowlist(self, tmp_path):
        payload = dict(VALID, recommended_action="delete_namespace")
        with pytest.raises(SystemExit, match="allowlist"):
            load_analysis(_write(tmp_path, payload))

    def test_a_shell_command_as_an_action(self, tmp_path):
        payload = dict(VALID, recommended_action="kubectl delete pods --all")
        with pytest.raises(SystemExit, match="allowlist"):
            load_analysis(_write(tmp_path, payload))

    def test_action_without_a_target(self, tmp_path):
        payload = dict(VALID, action_target="")
        with pytest.raises(SystemExit, match="failed the contract"):
            load_analysis(_write(tmp_path, payload))

    def test_analysis_not_claiming_to_be_from_bob(self, tmp_path):
        """
        The unavailable shape must never be ingested as a successful analysis.
        """
        payload = dict(VALID, analysis_source="unavailable")
        with pytest.raises(SystemExit, match="not 'ibm-bob'"):
            load_analysis(_write(tmp_path, payload))

    def test_not_json(self, tmp_path):
        with pytest.raises(SystemExit, match="not valid JSON"):
            load_analysis(_write(tmp_path, "Bob says: roll it back"))

    def test_invalid_confidence_value(self, tmp_path):
        payload = dict(VALID)
        payload["hypotheses"] = [dict(VALID["hypotheses"][0], confidence="very high")]
        with pytest.raises(SystemExit, match="failed the contract"):
            load_analysis(_write(tmp_path, payload))
