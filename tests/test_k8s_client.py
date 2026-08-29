"""
Live Kubernetes client tests.

The Kubernetes API is mocked. These assert the guards, the shapes and the
refusals — the things that must hold before this client is allowed anywhere
near a cluster. A live smoke test lives in scripts/validate.sh.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from agent.k8s_client import MAX_REPLICAS, LiveEvidenceReader, LiveKubernetesClient


class FakeAppsApi:
    """Records patches instead of applying them."""

    def __init__(self, replicas=2, container="app", generation=7):
        self.patches: list[tuple] = []
        self.scale_patches: list[tuple] = []
        self._replicas = replicas
        self._container = container
        self._generation = generation

    def read_namespaced_deployment(self, name, namespace):
        return SimpleNamespace(
            metadata=SimpleNamespace(
                annotations={"deployment.kubernetes.io/revision": "3"}
            ),
            spec=SimpleNamespace(
                replicas=self._replicas,
                template=SimpleNamespace(
                    spec=SimpleNamespace(
                        containers=[SimpleNamespace(name=self._container)]
                    )
                ),
            ),
            status=SimpleNamespace(observed_generation=self._generation),
        )

    def patch_namespaced_deployment(self, name, namespace, patch):
        self.patches.append((name, namespace, patch))
        return SimpleNamespace(
            metadata=SimpleNamespace(
                annotations={"deployment.kubernetes.io/revision": "4"}
            ),
            status=SimpleNamespace(observed_generation=self._generation + 1),
        )

    def patch_namespaced_deployment_scale(self, name, namespace, patch):
        self.scale_patches.append((name, namespace, patch))
        return SimpleNamespace(
            status=SimpleNamespace(observed_generation=self._generation + 1)
        )


def _revisions(monkeypatch, revs):
    monkeypatch.setattr("agent.k8s_client.recent_changes", lambda **kw: revs)


def _rev(revision, image, is_current=False):
    return SimpleNamespace(revision=revision, image=image, is_current=is_current)


@pytest.fixture
def api():
    return FakeAppsApi()


@pytest.fixture
def k8s(api):
    return LiveKubernetesClient(apps_api=api)


class TestNameValidation:
    """A malformed target must be refused before it reaches the API."""

    @pytest.mark.parametrize(
        "bad", ["", "UPPER", "has space", "trailing-", "-leading", "a" * 254, None]
    )
    def test_bad_deployment_name_refused(self, k8s, bad):
        with pytest.raises(ValueError):
            k8s.restart_deployment(bad, "opspilot")

    def test_bad_namespace_refused(self, k8s):
        with pytest.raises(ValueError):
            k8s.restart_deployment("ticket-booking", "Bad NS")

    def test_valid_name_accepted(self, k8s):
        result = k8s.restart_deployment("ticket-booking", "opspilot")
        assert result["action"] == "restart_deployment"


class TestRollback:
    def test_rolls_back_to_previous_revision_by_default(self, k8s, api, monkeypatch):
        _revisions(monkeypatch, [
            _rev("3", "ticketbooking:1.1", is_current=True),
            _rev("2", "ticketbooking:1.0"),
        ])
        result = k8s.rollback_deployment("ticket-booking", "opspilot")
        assert result["from_revision"] == "3"
        assert result["to_revision"] == "2"
        assert result["image"] == "ticketbooking:1.0"
        _, _, patch = api.patches[0]
        containers = patch["spec"]["template"]["spec"]["containers"]
        assert containers[0]["image"] == "ticketbooking:1.0"

    def test_explicit_revision_is_honoured(self, k8s, monkeypatch):
        _revisions(monkeypatch, [
            _rev("3", "ticketbooking:1.1", is_current=True),
            _rev("2", "ticketbooking:1.0"),
            _rev("1", "ticketbooking:0.9"),
        ])
        result = k8s.rollback_deployment("ticket-booking", "opspilot", to_revision=1)
        assert result["to_revision"] == "1"
        assert result["image"] == "ticketbooking:0.9"

    def test_writes_a_change_cause(self, k8s, api, monkeypatch):
        _revisions(monkeypatch, [
            _rev("3", "ticketbooking:1.1", is_current=True),
            _rev("2", "ticketbooking:1.0"),
        ])
        k8s.rollback_deployment("ticket-booking", "opspilot")
        _, _, patch = api.patches[0]
        cause = patch["metadata"]["annotations"]["kubernetes.io/change-cause"]
        assert "KubeMedic rollback" in cause
        assert "human approval" in cause

    def test_unknown_revision_refused(self, k8s, monkeypatch):
        _revisions(monkeypatch, [_rev("3", "x:1", is_current=True), _rev("2", "x:0")])
        with pytest.raises(ValueError, match="not found"):
            k8s.rollback_deployment("ticket-booking", "opspilot", to_revision=99)

    def test_rollback_to_current_revision_refused(self, k8s, monkeypatch):
        """A no-op that reports success is worse than an error."""
        _revisions(monkeypatch, [_rev("3", "x:1", is_current=True), _rev("2", "x:0")])
        with pytest.raises(ValueError, match="already current"):
            k8s.rollback_deployment("ticket-booking", "opspilot", to_revision=3)

    def test_single_revision_refused(self, k8s, monkeypatch):
        _revisions(monkeypatch, [_rev("1", "x:1", is_current=True)])
        with pytest.raises(ValueError, match="nothing to roll back"):
            k8s.rollback_deployment("ticket-booking", "opspilot")

    def test_no_history_refused(self, k8s, monkeypatch):
        _revisions(monkeypatch, [])
        with pytest.raises(ValueError, match="No revision history"):
            k8s.rollback_deployment("ticket-booking", "opspilot")

    def test_revision_without_image_refused(self, k8s, monkeypatch):
        _revisions(monkeypatch, [
            _rev("3", "x:1", is_current=True),
            _rev("2", None),
        ])
        with pytest.raises(ValueError, match="no recorded image"):
            k8s.rollback_deployment("ticket-booking", "opspilot")


class TestRestart:
    def test_stamps_restarted_at(self, k8s, api):
        k8s.restart_deployment("ticket-booking", "opspilot")
        _, _, patch = api.patches[0]
        ann = patch["spec"]["template"]["metadata"]["annotations"]
        assert "kubectl.kubernetes.io/restartedAt" in ann
        assert ann["kubemedic.io/restarted-by"] == "kubemedic-executor"


class TestScale:
    def test_scales_and_reports_both_ends(self, k8s, api):
        result = k8s.scale_workload("ticket-booking", "opspilot", replicas=4)
        assert result["from_replicas"] == 2
        assert result["to_replicas"] == 4
        assert api.scale_patches[0][2] == {"spec": {"replicas": 4}}

    def test_zero_is_allowed(self, k8s):
        assert k8s.scale_workload("ticket-booking", "opspilot", 0)["to_replicas"] == 0

    def test_negative_refused(self, k8s):
        with pytest.raises(ValueError, match=">= 0"):
            k8s.scale_workload("ticket-booking", "opspilot", -1)

    def test_above_ceiling_refused(self, k8s):
        """An unbounded replica count from model output is a cluster DoS."""
        with pytest.raises(ValueError, match="ceiling"):
            k8s.scale_workload("ticket-booking", "opspilot", MAX_REPLICAS + 1)

    def test_non_integer_refused(self, k8s):
        with pytest.raises(ValueError, match="integer"):
            k8s.scale_workload("ticket-booking", "opspilot", "lots")

    def test_numeric_string_accepted(self, k8s):
        assert k8s.scale_workload("ticket-booking", "opspilot", "3")["to_replicas"] == 3


class TestEvidenceReaderShape:
    """The verifier depends on these exact keys."""

    def test_workload_status_keys(self, monkeypatch):
        monkeypatch.setattr(
            "agent.k8s_client.inspect_workload",
            lambda **kw: SimpleNamespace(
                rollout_complete=True, desired_replicas=2, ready_replicas=2,
                updated_replicas=2, available_replicas=2, unavailable_replicas=0,
                image="ticketbooking:1.0", revision="4",
            ),
        )
        out = LiveEvidenceReader().get_workload_status("ticket-booking", "opspilot")
        for key in ("ready", "updated_replicas", "desired_replicas", "available_replicas"):
            assert key in out
        assert out["ready"] is True

    def test_ready_follows_rollout_complete_not_healthy(self, monkeypatch):
        """
        `ready` is the narrow claim -- desired == ready == updated ==
        available -- not the broader word `healthy`.
        """
        monkeypatch.setattr(
            "agent.k8s_client.inspect_workload",
            lambda **kw: SimpleNamespace(
                rollout_complete=False, desired_replicas=2, ready_replicas=0,
                updated_replicas=2, available_replicas=0, unavailable_replicas=2,
                image="ticketbooking:1.1", revision="5",
            ),
        )
        out = LiveEvidenceReader().get_workload_status("ticket-booking", "opspilot")
        assert out["ready"] is False

    def test_application_health_keys(self, monkeypatch):
        monkeypatch.setattr(
            "agent.k8s_client.check_application_health",
            lambda **kw: SimpleNamespace(
                status_code=503, healthy=False, body="unhealthy", error="HTTP 503"
            ),
        )
        out = LiveEvidenceReader().get_application_health("ticket-booking", "opspilot")
        assert out["status_code"] == 503
        assert out["healthy"] is False


class TestProtocolConformance:
    def test_satisfies_the_executor_protocol(self, k8s):
        for method in ("rollback_deployment", "restart_deployment", "scale_workload"):
            assert callable(getattr(k8s, method))

    def test_reader_cannot_mutate(self):
        """
        The verifier must not hold anything that can change what it verifies.
        """
        reader = LiveEvidenceReader()
        for method in ("rollback_deployment", "restart_deployment", "scale_workload"):
            assert not hasattr(reader, method)
