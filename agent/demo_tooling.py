"""
Demo fault injection for the live cluster.

DELIBERATELY NOT PART OF THE AGENT'S ACTION SURFACE
---------------------------------------------------
Breaking a workload on purpose is presenter tooling, not a capability the agent
has. It lives here rather than in agent/k8s_client.py so that the executor's
allowlist stays exactly three actions -- rollback, restart, scale -- and nothing
the model can reach can ship a bad image.

If this were a method on the client the executor uses, "the agent cannot break
your cluster" would stop being true by construction and start being a promise.

The fault is the same one scripts/inject_incident.sh ships: the ticket-booking
deployment moves to ticketbooking:1.1, an image built from the same source with
HEALTHY=false, so /ready returns 500. The new pod never becomes Ready, the old
pods keep serving, and the rollout stalls rather than the service going down.
"""
from __future__ import annotations

import logging
import os
from typing import Any

log = logging.getLogger("kubemedic.demo")

NAMESPACE = os.getenv("KUBEMEDIC_NAMESPACE", "opspilot")
DEPLOYMENT = os.getenv("KUBEMEDIC_DEPLOYMENT", "ticket-booking")
BAD_IMAGE = os.getenv("KUBEMEDIC_BAD_IMAGE", "ticketbooking:1.1")
GOOD_IMAGE = os.getenv("KUBEMEDIC_GOOD_IMAGE", "ticketbooking:1.0")


def _apps_api():
    from kubernetes import client, config

    try:
        config.load_incluster_config()
    except Exception:
        config.load_kube_config()
    return client.AppsV1Api()


def _set_image(image: str, cause: str) -> dict[str, Any]:
    apps = _apps_api()
    deployment = apps.read_namespaced_deployment(DEPLOYMENT, NAMESPACE)
    container = deployment.spec.template.spec.containers[0].name
    patch = {
        "spec": {"template": {"spec": {"containers": [
            {"name": container, "image": image}]}}},
        "metadata": {"annotations": {"kubernetes.io/change-cause": cause}},
    }
    updated = apps.patch_namespaced_deployment(DEPLOYMENT, NAMESPACE, patch)
    revision = (updated.metadata.annotations or {}).get(
        "deployment.kubernetes.io/revision")
    log.info("[DEMO] %s -> %s (revision %s)", DEPLOYMENT, image, revision)
    return {
        "deployment": DEPLOYMENT, "namespace": NAMESPACE,
        "image": image, "revision": revision, "change_cause": cause,
    }


def inject_incident() -> dict[str, Any]:
    """Ship the bad image. Reversible by rollback, which is the point."""
    return _set_image(
        BAD_IMAGE, f"Deploy {BAD_IMAGE} (regression) -- KubeMedic demo injection")


def reset_healthy() -> dict[str, Any]:
    """Restore the good image directly, for cleaning up between runs."""
    return _set_image(
        GOOD_IMAGE, f"Restore {GOOD_IMAGE} (healthy) -- KubeMedic demo reset")


def run_watcher_once() -> dict[str, Any]:
    """
    One watcher pass against the live cluster.

    Returns what it observed as well as what it filed -- a bare "0 filed" and a
    broken watcher look identical, and telling them apart has cost real time.
    """
    from mcp_server.db import init_db
    from mcp_server.watcher import KubeWatcher

    init_db()
    watcher = KubeWatcher(NAMESPACE, DEPLOYMENT, DEPLOYMENT)
    created = watcher.check_once()
    return {"created": created, **(watcher.last_pass or {})}


def close_open_tickets() -> int:
    """Clear the board between demo runs. Resolved, not deleted -- the history stays."""
    from mcp_server import tickets as store
    from mcp_server.db import init_db

    init_db()
    closed = 0
    for ticket in store.list_tickets():
        if ticket.status.value in ("open", "investigating"):
            store.update_ticket(ticket.id, status="resolved")
            closed += 1
    return closed
