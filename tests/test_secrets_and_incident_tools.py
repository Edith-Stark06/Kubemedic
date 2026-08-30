"""
The secrets seam, and the read-only incident tools on the MCP surface.

Two things are being protected here:

  1. A credential value must never appear in a log line, a health payload, an
     audit record or an MCP response. `describe()` names the source, never the
     contents.
  2. The incident tools must stay read-only, and must not be usable to read
     files outside records/. An MCP tool argument is model-supplied input
     reaching a filesystem path.
"""
from __future__ import annotations

import json

import pytest

from mcp_server import incidents
from agent.secrets import (
    EnvSecrets,
    FileSecrets,
    KubernetesSecrets,
    VaultSecrets,
    get_secrets,
    redact,
    reset_secrets_cache,
)

RECORD = {
    "incident_id": "INC-20260830T120000-001",
    "final_state": "RESOLVED",
    "tickets": ["TKT-1", "TKT-2"],
    "analysis_source": "ibm-bob",
    "recommended_action": "rollback_deployment",
    "human_decision": "approved",
    "rejection_feedback": None,
    "feedback_history": ["Confirm the previous revision was healthy first."],
    "revision_count": 1,
    "executed": True,
    "verification_outcome": "PASS",
    "created_at": "2026-08-30T12:00:00+00:00",
    "resolved_at": "2026-08-30T12:04:00+00:00",
    "audit_log": [{"step": "correlation"}, {"step": "verification"}],
}


@pytest.fixture(autouse=True)
def clean_secrets():
    reset_secrets_cache()
    yield
    reset_secrets_cache()


@pytest.fixture
def records(tmp_path, monkeypatch):
    directory = tmp_path / "records"
    directory.mkdir()
    (directory / f"{RECORD['incident_id']}.json").write_text(
        json.dumps(RECORD), encoding="utf-8"
    )
    monkeypatch.setenv("KUBEMEDIC_RECORDS_DIR", str(directory))
    return directory


class TestSecretBackends:
    def test_env_backend_is_the_default(self, monkeypatch):
        monkeypatch.delenv("KUBEMEDIC_SECRETS_BACKEND", raising=False)
        assert isinstance(get_secrets(), EnvSecrets)

    def test_env_reads_and_strips(self, monkeypatch):
        monkeypatch.setenv("KUBEMEDIC_TEST_SECRET", "  value  ")
        assert EnvSecrets().get("KUBEMEDIC_TEST_SECRET") == "value"

    def test_missing_secret_is_none_not_an_exception(self):
        """A provider must be able to report itself unconfigured, calmly."""
        assert EnvSecrets().get("DEFINITELY_NOT_SET_ANYWHERE") is None

    def test_file_backend_reads_one_file_per_secret(self, tmp_path):
        (tmp_path / "KUBEMEDIC_WATSONX_API_KEY").write_text("filekey\n")
        assert FileSecrets(root=str(tmp_path)).get("KUBEMEDIC_WATSONX_API_KEY") == "filekey"

    def test_file_backend_falls_through_to_env(self, tmp_path, monkeypatch):
        """A partial migration must keep working."""
        monkeypatch.setenv("KUBEMEDIC_ONLY_IN_ENV", "envvalue")
        assert FileSecrets(root=str(tmp_path)).get("KUBEMEDIC_ONLY_IN_ENV") == "envvalue"

    def test_unknown_backend_is_a_hard_error(self):
        with pytest.raises(SystemExit, match="Unknown secrets backend"):
            get_secrets("azure-keyvault")

    def test_vault_backend_fails_loudly_rather_than_silently(self):
        """Selecting an unimplemented backend must not serve nothing quietly."""
        with pytest.raises(NotImplementedError):
            VaultSecrets().get("ANYTHING")

    def test_describe_never_returns_a_value(self, tmp_path, monkeypatch):
        monkeypatch.setenv("KUBEMEDIC_WATSONX_API_KEY", "supersecret1234567890")
        for provider in (
            EnvSecrets(),
            FileSecrets(root=str(tmp_path)),
            KubernetesSecrets(name="s", namespace="n"),
        ):
            assert "supersecret" not in provider.describe()


class TestRedaction:
    def test_unset(self):
        assert redact(None) == "unset"
        assert redact("") == "unset"

    def test_short_values_are_not_partially_revealed(self):
        """
        A four-character prefix of an eight-character secret is a meaningful
        leak, so short values report presence only.
        """
        assert redact("abc12345") == "set (short)"

    def test_long_value_is_masked(self):
        out = redact("sk-ant-abcdefghijklmnop")
        assert "abcdefghij" not in out
        assert out.startswith("set (")


class TestIncidentToolsAreReadOnly:
    def test_list_incidents(self, records):
        result = incidents.list_incidents()
        assert result["count"] == 1
        assert result["incidents"][0]["incident_id"] == RECORD["incident_id"]

    def test_list_summarises_rather_than_dumping_the_audit_log(self, records):
        """A long incident's audit log is large and Bob does not need it here."""
        assert "audit_log" not in result_keys(incidents.list_incidents())

    def test_get_incident_returns_the_full_record(self, records):
        record = incidents.get_incident(RECORD["incident_id"])
        assert record["verification_outcome"] == "PASS"
        assert "audit_log" in record

    def test_rejection_history_surfaces_operator_knowledge(self, records):
        history = incidents.get_rejection_history()
        assert history["count"] == 1
        assert "previous revision was healthy" in history["rejections"][0]["reason"]

    def test_missing_records_directory_is_reported_not_raised(self, monkeypatch, tmp_path):
        monkeypatch.setenv("KUBEMEDIC_RECORDS_DIR", str(tmp_path / "nope"))
        assert incidents.list_incidents()["incidents"] == []

    def test_unknown_incident_is_an_error_not_an_exception(self, records):
        assert "error" in incidents.get_incident("INC-does-not-exist")

    @pytest.mark.parametrize("evil", [
        "../../../etc/passwd",
        "INC-../../secrets",
        "INC-/etc/passwd",
        "INC-..\\..\\windows\\system32",
        "not-an-incident-id",
        "",
    ])
    def test_path_traversal_is_refused(self, records, evil):
        """
        Model-supplied input reaching a filesystem path. Traversal here would
        turn a read-only evidence tool into an arbitrary file read.
        """
        result = incidents.get_incident(evil)
        assert "error" in result
        assert "audit_log" not in result

    def test_unreadable_record_is_reported_not_fabricated(self, records):
        (records / "INC-broken.json").write_text("{ not json", encoding="utf-8")
        entries = incidents.list_incidents()["incidents"]
        broken = [e for e in entries if e.get("file") == "INC-broken.json"]
        assert broken and "error" in broken[0]

    def test_module_exposes_no_mutation(self):
        """There is no create/approve/execute here, and there never will be."""
        for forbidden in ("create_incident", "approve", "execute", "delete"):
            assert not any(
                name.startswith(forbidden) for name in dir(incidents)
            ), forbidden


def result_keys(listing):
    return set().union(*(entry.keys() for entry in listing["incidents"]))
