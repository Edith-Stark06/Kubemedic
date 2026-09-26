"""
The read-only evidence layer against a fake Kubernetes API.

These cover the behaviours that used to be assumptions: which config is loaded,
how pods are found, what "ready" means for a multi-container pod, and which
events belong to a workload.
"""
from __future__ import annotations

from types import SimpleNamespace as NS

import pytest
from kubernetes.client.rest import ApiException

from mcp_server import evidence


def _container(name="app", ready=True, restarts=0, image="img:1", waiting=None):
    state = NS(waiting=NS(reason=waiting, message="m") if waiting else None,
               terminated=None)
    return NS(name=name, ready=ready, restart_count=restarts, image=image, state=state)


def _pod(name, containers, phase="Running"):
    return NS(
        metadata=NS(name=name, deletion_timestamp=None),
        status=NS(phase=phase, container_statuses=containers),
    )


def _deployment(match_labels):
    return NS(spec=NS(selector=NS(match_labels=match_labels)))


class FakeApps:
    def __init__(self, deployment=None, missing=False):
        self.deployment, self.missing = deployment, missing

    def read_namespaced_deployment(self, name, namespace):
        if self.missing:
            raise ApiException(status=404, reason="not found")
        return self.deployment


class FakeCore:
    def __init__(self, pods=(), events=()):
        self.pods, self.events = list(pods), list(events)
        self.pod_selector = None
        self.event_limit = None

    def list_namespaced_pod(self, namespace, label_selector=None):
        self.pod_selector = label_selector
        return NS(items=self.pods)

    def list_namespaced_event(self, namespace, limit=None):
        self.event_limit = limit
        return NS(items=self.events)


@pytest.fixture
def fake(monkeypatch):
    def install(apps, core):
        monkeypatch.setattr(evidence, "_load", lambda: (apps, core))
    return install


# -- client loading -----------------------------------------------------------

class TestClientLoading:
    def setup_method(self):
        evidence.reset_clients()

    def teardown_method(self):
        evidence.reset_clients()

    def test_in_cluster_config_is_preferred(self, monkeypatch):
        calls = []
        monkeypatch.setattr(evidence.config, "load_incluster_config",
                            lambda: calls.append("incluster"))
        monkeypatch.setattr(evidence.config, "load_kube_config",
                            lambda: calls.append("kubeconfig"))
        evidence._load()
        assert calls == ["incluster"]

    def test_falls_back_to_kubeconfig_outside_a_cluster(self, monkeypatch):
        calls = []

        def not_in_cluster():
            raise evidence.config.ConfigException("not in cluster")

        monkeypatch.setattr(evidence.config, "load_incluster_config", not_in_cluster)
        monkeypatch.setattr(evidence.config, "load_kube_config",
                            lambda: calls.append("kubeconfig"))
        evidence._load()
        assert calls == ["kubeconfig"]

    def test_clients_are_built_once(self, monkeypatch):
        loads = []
        monkeypatch.setattr(evidence.config, "load_incluster_config",
                            lambda: loads.append(1))
        first = evidence._load()
        second = evidence._load()
        assert first is second
        assert len(loads) == 1

    def test_reset_forces_a_reload(self, monkeypatch):
        loads = []
        monkeypatch.setattr(evidence.config, "load_incluster_config",
                            lambda: loads.append(1))
        evidence._load()
        evidence.reset_clients()
        evidence._load()
        assert len(loads) == 2


# -- pods ---------------------------------------------------------------------

class TestPods:
    def test_selector_comes_from_the_deployment_not_a_naming_convention(self, fake):
        core = FakeCore()
        fake(FakeApps(_deployment({"tier": "web", "app.kubernetes.io/name": "shop"})), core)
        evidence.inspect_pods("ns", "checkout")
        assert core.pod_selector == "app.kubernetes.io/name=shop,tier=web"

    def test_falls_back_to_app_label_when_deployment_unreadable(self, fake):
        core = FakeCore()
        fake(FakeApps(missing=True), core)
        evidence.inspect_pods("ns", "checkout")
        assert core.pod_selector == "app=checkout"

    def test_pod_with_a_failing_sidecar_is_not_ready(self, fake):
        pod = _pod("p1", [
            _container("app", ready=True),
            _container("sidecar", ready=False, waiting="CrashLoopBackOff", image="side:2"),
        ])
        fake(FakeApps(_deployment({"app": "x"})), FakeCore([pod]))
        (state,) = evidence.inspect_pods("ns", "x")
        assert state.ready is False
        assert state.reason == "CrashLoopBackOff"
        assert state.image == "side:2"

    def test_restarts_are_summed_across_containers(self, fake):
        pod = _pod("p1", [_container("a", restarts=2), _container("b", restarts=5)])
        fake(FakeApps(_deployment({"app": "x"})), FakeCore([pod]))
        (state,) = evidence.inspect_pods("ns", "x")
        assert state.restarts == 7
        assert state.ready is True

    def test_pod_with_no_container_status_is_not_ready(self, fake):
        fake(FakeApps(_deployment({"app": "x"})), FakeCore([_pod("p1", None, "Pending")]))
        (state,) = evidence.inspect_pods("ns", "x")
        assert state.ready is False
        assert state.restarts == 0


# -- events -------------------------------------------------------------------

def _event(obj_name, reason="Unhealthy"):
    return NS(type="Warning", reason=reason, message="m", count=1,
              involved_object=NS(kind="Pod", name=obj_name),
              last_timestamp=None, event_time=None)


class TestEvents:
    def test_prefix_match_excludes_unrelated_workloads(self, fake):
        core = FakeCore(events=[
            _event("checkout-7d9-abc"),
            _event("checkout"),
            _event("not-checkout-1"),
            _event("checkoutx-1"),
        ])
        fake(FakeApps(), core)
        names = {e.object for e in evidence.inspect_events("ns", "checkout")}
        assert names == {"Pod/checkout-7d9-abc", "Pod/checkout"}

    def test_event_read_is_bounded(self, fake):
        core = FakeCore()
        fake(FakeApps(), core)
        evidence.inspect_events("ns", "checkout")
        assert core.event_limit == evidence.EVENT_SCAN_LIMIT


# -- health -------------------------------------------------------------------

class TestHealthDefaults:
    def test_path_and_port_default_to_configured_values(self):
        import inspect

        params = inspect.signature(evidence.check_application_health).parameters
        assert params["path"].default == evidence.HEALTH_PATH
        assert params["port"].default == evidence.HEALTH_PORT
