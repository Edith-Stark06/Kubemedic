"""
The live Kubernetes client — the only place in KubeMedic that changes a cluster.

Until this module existed, `agent/executor.py` and `agent/verification.py`
declared `KubernetesClient` and `EvidenceReader` as Protocols with no concrete
implementation anywhere in the repository. Every test injected a fake, so the
executor had never mutated a cluster and the verifier had never read one.

SAFETY
------
Three operations, matching AllowedAction exactly. Each is a typed call against
the Kubernetes API. There is no shell here, no kubectl subprocess, and no
string interpolation into a command — a model-composed action cannot become an
arbitrary operation, because the only thing that crosses this boundary is an
`AllowedAction` enum member plus a validated target name.

`LiveKubernetesClient` implements the mutating protocol.
`LiveEvidenceReader` implements the read-only verification protocol.

They are separate classes on purpose: verification must be able to read the
cluster without holding anything that can write to it. `LiveCluster` combines
them for callers that legitimately need both.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from kubernetes import client, config
from kubernetes.client.rest import ApiException

from mcp_server.evidence import (
    REVISION_ANNOTATION,
    check_application_health,
    inspect_workload,
    recent_changes,
)

log = logging.getLogger("kubemedic.k8s")

# RFC 1123 label — the shape Kubernetes itself requires of a resource name.
# Validating here means a malformed target is refused before it reaches the
# API, with a message that names the problem.
_DNS_1123 = re.compile(r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$")

MAX_REPLICAS = 10


def _validate_name(kind: str, value: str) -> str:
    if not value or not isinstance(value, str):
        raise ValueError(f"{kind} must be a non-empty string, got {value!r}")
    if len(value) > 253 or not _DNS_1123.match(value):
        raise ValueError(
            f"{kind} {value!r} is not a valid Kubernetes name "
            "(RFC 1123: lower-case alphanumerics and '-')"
        )
    return value


def _load_apps_api():
    """Load kubeconfig, in-cluster first, then the user's kubeconfig."""
    try:
        config.load_incluster_config()
    except Exception:
        config.load_kube_config()
    return client.AppsV1Api()


class LiveKubernetesClient:
    """
    Performs the three allowlisted actions. Satisfies
    agent.executor.KubernetesClient.

    Every method returns a plain dict, which the executor stores verbatim in
    ExecutionResult.raw_response so the audit record carries what the cluster
    actually said.
    """

    def __init__(self, apps_api=None) -> None:
        self._apps = apps_api or _load_apps_api()

    # -- rollback ---------------------------------------------------------

    def rollback_deployment(
        self, name: str, namespace: str, to_revision: int | None = None
    ) -> dict[str, Any]:
        """
        Roll a deployment back to a previous ReplicaSet's pod template.

        The Kubernetes API has no rollback verb — `kubectl rollout undo` is
        client-side logic. We reproduce it honestly: find the target
        ReplicaSet, then patch the deployment's pod template back to it.

        With no `to_revision`, the previous revision is used. Refusing to roll
        back to the current revision is deliberate: it would report success
        while changing nothing.
        """
        _validate_name("deployment", name)
        _validate_name("namespace", namespace)

        revisions = recent_changes(namespace=namespace, deployment=name)
        if not revisions:
            raise ValueError(f"No revision history for {namespace}/{name}")

        current = next((r for r in revisions if r.is_current), None)
        current_rev = current.revision if current else None

        if to_revision is not None:
            target = next(
                (r for r in revisions if str(r.revision) == str(to_revision)), None
            )
            if target is None:
                available = [r.revision for r in revisions]
                raise ValueError(
                    f"Revision {to_revision} not found for {namespace}/{name}. "
                    f"Available: {available}"
                )
        else:
            older = [r for r in revisions if not r.is_current]
            if not older:
                raise ValueError(
                    f"{namespace}/{name} has only one revision; nothing to roll back to"
                )
            target = older[0]

        if str(target.revision) == str(current_rev):
            raise ValueError(
                f"Revision {target.revision} is already current for "
                f"{namespace}/{name}; rollback would be a no-op"
            )
        if not target.image:
            raise ValueError(
                f"Revision {target.revision} has no recorded image; cannot roll back"
            )

        deployment = self._apps.read_namespaced_deployment(name, namespace)
        container = deployment.spec.template.spec.containers[0].name

        patch = {
            "spec": {
                "template": {
                    "spec": {
                        "containers": [{"name": container, "image": target.image}]
                    }
                }
            },
            "metadata": {
                "annotations": {
                    "kubernetes.io/change-cause": (
                        f"KubeMedic rollback to revision {target.revision} "
                        f"({target.image}) after human approval"
                    )
                }
            },
        }

        log.info(
            "[K8S] rollback %s/%s: revision %s -> %s (%s)",
            namespace, name, current_rev, target.revision, target.image,
        )
        updated = self._apps.patch_namespaced_deployment(name, namespace, patch)

        return {
            "action": "rollback_deployment",
            "namespace": namespace,
            "deployment": name,
            "from_revision": current_rev,
            "to_revision": target.revision,
            "image": target.image,
            "observed_generation": updated.status.observed_generation,
            "new_revision": (updated.metadata.annotations or {}).get(
                REVISION_ANNOTATION
            ),
        }

    # -- restart ----------------------------------------------------------

    def restart_deployment(self, name: str, namespace: str) -> dict[str, Any]:
        """
        Trigger a rolling restart, the same way `kubectl rollout restart` does:
        stamp a restartedAt annotation on the pod template so the controller
        rolls new pods.
        """
        _validate_name("deployment", name)
        _validate_name("namespace", namespace)

        from datetime import datetime, timezone

        stamp = datetime.now(timezone.utc).isoformat()
        patch = {
            "spec": {
                "template": {
                    "metadata": {
                        "annotations": {
                            "kubectl.kubernetes.io/restartedAt": stamp,
                            "kubemedic.io/restarted-by": "kubemedic-executor",
                        }
                    }
                }
            }
        }

        log.info("[K8S] restart %s/%s at %s", namespace, name, stamp)
        updated = self._apps.patch_namespaced_deployment(name, namespace, patch)

        return {
            "action": "restart_deployment",
            "namespace": namespace,
            "deployment": name,
            "restarted_at": stamp,
            "observed_generation": updated.status.observed_generation,
        }

    # -- scale ------------------------------------------------------------

    def scale_workload(
        self, name: str, namespace: str, replicas: int
    ) -> dict[str, Any]:
        """
        Change replica count. Bounded deliberately: an unbounded replica count
        taken from model output is a denial-of-service against the cluster.
        """
        _validate_name("deployment", name)
        _validate_name("namespace", namespace)

        try:
            replicas = int(replicas)
        except (TypeError, ValueError):
            raise ValueError(f"replicas must be an integer, got {replicas!r}")
        if replicas < 0:
            raise ValueError(f"replicas must be >= 0, got {replicas}")
        if replicas > MAX_REPLICAS:
            raise ValueError(
                f"replicas {replicas} exceeds the KubeMedic ceiling of "
                f"{MAX_REPLICAS}. Raise MAX_REPLICAS deliberately if a real "
                "workload needs more."
            )

        before = self._apps.read_namespaced_deployment(name, namespace)
        previous = before.spec.replicas

        log.info("[K8S] scale %s/%s: %s -> %s", namespace, name, previous, replicas)
        updated = self._apps.patch_namespaced_deployment_scale(
            name, namespace, {"spec": {"replicas": replicas}}
        )

        return {
            "action": "scale_workload",
            "namespace": namespace,
            "deployment": name,
            "from_replicas": previous,
            "to_replicas": replicas,
            "observed_generation": updated.status.observed_generation
            if updated.status
            else None,
        }


class LiveEvidenceReader:
    """
    Read-only cluster reader. Satisfies agent.verification.EvidenceReader.

    Holds nothing that can write. Verification re-reading the cluster through
    an object incapable of changing it is the point: the verifier must not be
    able to influence what it is verifying.

    The two signals come from different sources on purpose — the control
    plane's view of the rollout, and the application answering HTTP through the
    Service proxy.
    """

    def get_workload_status(self, name: str, namespace: str) -> dict[str, Any]:
        state = inspect_workload(namespace=namespace, name=name)
        return {
            # `ready` maps to rollout_complete, not healthy. rollout_complete
            # is the narrow, checkable claim: desired == ready == updated ==
            # available. `healthy` is a broader word and verification should
            # assert the narrow thing.
            "ready": state.rollout_complete,
            "desired_replicas": state.desired_replicas,
            "ready_replicas": state.ready_replicas,
            "updated_replicas": state.updated_replicas,
            "available_replicas": state.available_replicas,
            "unavailable_replicas": state.unavailable_replicas,
            "image": state.image,
            "revision": state.revision,
            "rollout_complete": state.rollout_complete,
        }

    def get_application_health(self, name: str, namespace: str) -> dict[str, Any]:
        # The Service and the Deployment share a name in this project; if that
        # stops being true, this is the line to change.
        health = check_application_health(namespace=namespace, service=name)
        return {
            "status_code": health.status_code,
            "healthy": health.healthy,
            "body": health.body,
            "error": health.error,
        }


class LiveCluster(LiveKubernetesClient, LiveEvidenceReader):
    """Both protocols, for callers that genuinely need to act and to read."""


def is_cluster_reachable() -> tuple[bool, str]:
    """
    Cheap preflight so a demo fails at the start with a clear message rather
    than midway through an incident.
    """
    try:
        _load_apps_api().get_api_resources()
        return True, "cluster reachable"
    except ApiException as exc:
        return False, f"Kubernetes API error {exc.status}: {exc.reason}"
    except Exception as exc:
        return False, f"cluster unreachable: {exc}"
