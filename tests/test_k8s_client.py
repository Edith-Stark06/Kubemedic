"""
Live Kubernetes client tests.

The Kubernetes API is mocked. These assert the guards, the shapes and the
refusals — the things that must hold before this client is allowed anywhere
near a cluster. A live smoke test lives in scripts/validate.sh.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from kubernetes import client as k8s_client_lib

from agent.k8s_client import MAX_REPLICAS, LiveEvidenceReader, LiveKubernetesClient


def _template(image, env=None):
    return {
        "metadata": {"labels": {"app": "ticket-booking", "pod-template-hash": "abc123"}},
        "spec": {"containers": [{
            "name": "app", "image": image,
            "env": [{"name": k, "value": v} for k, v in (env or {}).items()],
        }]},
    }


class FakeAppsApi:
    """Records patches instead of applying them."""

    def __init__(self, replicas=2, container="app", generation=7):
        self.patches: list[tuple] = []
        self.scale_patches: list[tuple] = []
        self._replicas = replicas
        self._container = container
        self._generation = generation
        self.selector_used = None
        # A real ApiClient for sanitize_for_serialization -- pure data
        # transformation, no network I/O -- so the fake exposes the same
        # `.api_client` attribute the real AppsV1Api does.
        self.api_client = k8s_client_lib.ApiClient()
        # revision -> pod template (plain dicts, as the API serialises them)
        self.templates = {
            "1": _template("ticketbooking:0.9"),
            "2": _template("ticketbooking:1.0", env={"FEATURE_X": "off"}),
            "3": _template("ticketbooking:1.1", env={"FEATURE_X": "on", "NEW": "1"}),
        }

    def list_namespaced_replica_set(self, namespace, label_selector=None):
        self.selector_used = label_selector
        items = []
        for revision, template in self.templates.items():
            items.append(SimpleNamespace(
                metadata=SimpleNamespace(
                    annotations={"deployment.kubernetes.io/revision": revision}),
                spec=SimpleNamespace(template=template),
            ))
        return SimpleNamespace(items=items)

    def read_namespaced_deployment(self, name, namespace):
        return SimpleNamespace(
            metadata=SimpleNamespace(
                annotations={"deployment.kubernetes.io/revision": "3"}
            ),
            spec=SimpleNamespace(
                selector=SimpleNamespace(match_labels={"app": "ticket-booking"}),
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
        (op,) = patch
        assert op["op"] == "replace" and op["path"] == "/spec/template"
        assert op["value"]["spec"]["containers"][0]["image"] == "ticketbooking:1.0"
        assert result["restored"] == "full pod template"

    def test_restores_the_whole_template_not_just_the_image(self, k8s, api, monkeypatch):
        """An env var added by the bad revision must not survive the rollback."""
        _revisions(monkeypatch, [
            _rev("3", "ticketbooking:1.1", is_current=True),
            _rev("2", "ticketbooking:1.0"),
        ])
        k8s.rollback_deployment("ticket-booking", "opspilot")
        env = api.patches[0][2][0]["value"]["spec"]["containers"][0]["env"]
        assert env == [{"name": "FEATURE_X", "value": "off"}]

    def test_controller_hash_label_is_not_restored(self, k8s, api, monkeypatch):
        _revisions(monkeypatch, [
            _rev("3", "ticketbooking:1.1", is_current=True),
            _rev("2", "ticketbooking:1.0"),
        ])
        k8s.rollback_deployment("ticket-booking", "opspilot")
        labels = api.patches[0][2][0]["value"]["metadata"]["labels"]
        assert "pod-template-hash" not in labels

    def test_replicaset_is_found_by_the_deployments_own_selector(self, k8s, api, monkeypatch):
        _revisions(monkeypatch, [
            _rev("3", "ticketbooking:1.1", is_current=True),
            _rev("2", "ticketbooking:1.0"),
        ])
        k8s.rollback_deployment("ticket-booking", "opspilot")
        assert api.selector_used == "app=ticket-booking"

    def test_missing_replicaset_is_refused_not_guessed(self, k8s, api, monkeypatch):
        _revisions(monkeypatch, [
            _rev("3", "ticketbooking:1.1", is_current=True),
            _rev("2", "ticketbooking:1.0"),
        ])
        del api.templates["2"]
        with pytest.raises(ValueError, match="cannot restore"):
            k8s.rollback_deployment("ticket-booking", "opspilot")
        assert api.patches == []

    def test_reuses_the_loaded_client_rather_than_a_fresh_one(
        self, k8s, api, monkeypatch
    ):
        """
        A bare client.ApiClient() here would re-read kubeconfig a second
        time, separate from the one loaded for self._apps -- flagged by a
        security audit.
        """
        _revisions(monkeypatch, [
            _rev("3", "ticketbooking:1.1", is_current=True),
            _rev("2", "ticketbooking:1.0"),
        ])
        constructed = []
        original = k8s_client_lib.ApiClient
        monkeypatch.setattr(
            k8s_client_lib, "ApiClient",
            lambda *a, **kw: constructed.append(1) or original(*a, **kw),
        )
        k8s.rollback_deployment("ticket-booking", "opspilot")
        assert constructed == []

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
        _, _, patch = api.patches[1]
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

    def test_zero_is_refused_because_it_is_an_outage(self, k8s, api):
        with pytest.raises(ValueError, match="outage decision"):
            k8s.scale_workload("ticket-booking", "opspilot", 0)
        assert api.scale_patches == []

    def test_one_is_the_floor(self, k8s):
        assert k8s.scale_workload("ticket-booking", "opspilot", 1)["to_replicas"] == 1

    def test_negative_refused(self, k8s):
        with pytest.raises(ValueError, match=">= 1"):
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
