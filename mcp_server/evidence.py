"""KubeMedic evidence tools — typed, READ-ONLY Kubernetes inspection.

Safety contract (see AGENTS.md, "The AI boundary"): these tools NEVER mutate
cluster state. Each function validates inputs and returns a typed pydantic
result. Cluster and API errors are captured as structured values — never
silently swallowed, never fabricated. This is the only layer allowed to read
the cluster for evidence.
"""
from __future__ import annotations

import datetime as _dt
from typing import Optional

from pydantic import BaseModel, Field
from kubernetes import client, config
from kubernetes.client.rest import ApiException

DEFAULT_NAMESPACE = "opspilot"
DEFAULT_DEPLOYMENT = "ticket-booking"
DEFAULT_SERVICE = "ticket-booking"

REVISION_ANNOTATION = "deployment.kubernetes.io/revision"
CHANGE_CAUSE_ANNOTATION = "kubernetes.io/change-cause"


def _iso(ts) -> Optional[str]:
    if ts is None:
        return None
    if isinstance(ts, _dt.datetime):
        return ts.astimezone(_dt.timezone.utc).isoformat()
    return str(ts)


# ---- typed result models --------------------------------------------------

class ToolError(BaseModel):
    tool: str
    error: str
    detail: Optional[str] = None


class WorkloadState(BaseModel):
    namespace: str
    name: str
    image: Optional[str] = None
    revision: Optional[str] = None
    desired_replicas: int = 0
    ready_replicas: int = 0
    available_replicas: int = 0
    updated_replicas: int = 0
    unavailable_replicas: int = 0
    observed_generation: Optional[int] = None
    conditions: list[dict] = Field(default_factory=list)
    # True only when the deployment is FULLY rolled out and healthy.
    healthy: bool = False
    rollout_complete: bool = False


class PodState(BaseModel):
    name: str
    phase: Optional[str] = None
    ready: bool = False
    restarts: int = 0
    image: Optional[str] = None
    reason: Optional[str] = None
    message: Optional[str] = None
    # Set once the pod is being deleted (e.g. old ReplicaSet draining after a
    # rollback). A terminating pod receives no Service traffic.
    deletion_timestamp: Optional[str] = None
    terminating: bool = False


class EventItem(BaseModel):
    type: Optional[str] = None
    reason: Optional[str] = None
    message: Optional[str] = None
    count: int = 1
    object: Optional[str] = None
    last_seen: Optional[str] = None


class RevisionInfo(BaseModel):
    revision: Optional[str] = None
    image: Optional[str] = None
    created: Optional[str] = None
    change_cause: Optional[str] = None
    ready_replicas: int = 0
    is_current: bool = False


class HealthResult(BaseModel):
    namespace: str
    service: str
    path: str
    healthy: bool
    status_code: Optional[int] = None
    body: Optional[str] = None
    error: Optional[str] = None


class EvidenceSnapshot(BaseModel):
    """A single, typed, point-in-time snapshot of all read-only evidence.

    This is the internal currency of the evidence pipeline: collected once,
    then passed to correlation → hypothesis → plan, and collected again for
    verification. Everything in it comes from the live cluster.
    """
    namespace: str
    deployment: str
    service: str
    workload: WorkloadState
    pods: list[PodState] = Field(default_factory=list)
    events: list[EventItem] = Field(default_factory=list)
    recent_changes: list[RevisionInfo] = Field(default_factory=list)
    application_health: HealthResult


# ---- client ---------------------------------------------------------------

def _load():
    """Load kubeconfig (rancher-desktop context) and return (AppsV1, CoreV1)."""
    config.load_kube_config()
    return client.AppsV1Api(), client.CoreV1Api()


# ---- read-only tools ------------------------------------------------------

def inspect_workload(namespace: str = DEFAULT_NAMESPACE,
                     name: str = DEFAULT_DEPLOYMENT) -> WorkloadState:
    apps, _ = _load()
    d = apps.read_namespaced_deployment(name=name, namespace=namespace)
    st = d.status
    ann = d.metadata.annotations or {}
    conds = [
        {"type": c.type, "status": c.status, "reason": c.reason, "message": c.message}
        for c in (st.conditions or [])
    ]
    desired = st.replicas or 0
    ready = st.ready_replicas or 0
    updated = st.updated_replicas or 0
    available = st.available_replicas or 0
    rollout_complete = (
        desired > 0 and ready == desired and updated == desired and available == desired
    )
    return WorkloadState(
        namespace=namespace, name=name,
        image=d.spec.template.spec.containers[0].image,
        revision=ann.get(REVISION_ANNOTATION),
        desired_replicas=desired, ready_replicas=ready,
        available_replicas=available, updated_replicas=updated,
        unavailable_replicas=st.unavailable_replicas or 0,
        observed_generation=st.observed_generation, conditions=conds,
        healthy=rollout_complete, rollout_complete=rollout_complete,
    )


def inspect_pods(namespace: str = DEFAULT_NAMESPACE,
                 app: str = DEFAULT_DEPLOYMENT) -> list[PodState]:
    _, core = _load()
    pods = core.list_namespaced_pod(namespace, label_selector=f"app={app}")
    out: list[PodState] = []
    for p in pods.items:
        cs = (p.status.container_statuses or [None])[0]
        reason = message = None
        if cs and cs.state:
            if cs.state.waiting:
                reason, message = cs.state.waiting.reason, cs.state.waiting.message
            elif cs.state.terminated:
                reason, message = cs.state.terminated.reason, cs.state.terminated.message
        del_ts = p.metadata.deletion_timestamp
        out.append(PodState(
            name=p.metadata.name, phase=p.status.phase,
            ready=bool(cs and cs.ready),
            restarts=int(cs.restart_count) if cs else 0,
            image=cs.image if cs else None, reason=reason, message=message,
            deletion_timestamp=_iso(del_ts), terminating=del_ts is not None,
        ))
    return out


def inspect_events(namespace: str = DEFAULT_NAMESPACE,
                   name: Optional[str] = None, limit: int = 15) -> list[EventItem]:
    _, core = _load()
    evs = core.list_namespaced_event(namespace)
    items: list[EventItem] = []
    for e in evs.items:
        obj = e.involved_object
        if name and obj and name not in (obj.name or ""):
            continue
        items.append(EventItem(
            type=e.type, reason=e.reason, message=e.message, count=e.count or 1,
            object=(f"{obj.kind}/{obj.name}" if obj else None),
            last_seen=_iso(e.last_timestamp or e.event_time),
        ))
    items.sort(key=lambda x: x.last_seen or "", reverse=True)
    return items[:limit]


def recent_changes(namespace: str = DEFAULT_NAMESPACE,
                   deployment: str = DEFAULT_DEPLOYMENT) -> list[RevisionInfo]:
    apps, _ = _load()
    d = apps.read_namespaced_deployment(deployment, namespace)
    cur_rev = (d.metadata.annotations or {}).get(REVISION_ANNOTATION)
    match = d.spec.selector.match_labels or {}
    selector = ",".join(f"{k}={v}" for k, v in match.items())
    rss = apps.list_namespaced_replica_set(namespace, label_selector=selector)
    revs: list[RevisionInfo] = []
    for rs in rss.items:
        ann = rs.metadata.annotations or {}
        rev = ann.get(REVISION_ANNOTATION)
        tmpl = rs.spec.template if rs.spec else None
        revs.append(RevisionInfo(
            revision=rev,
            image=(tmpl.spec.containers[0].image if tmpl else None),
            created=_iso(rs.metadata.creation_timestamp),
            change_cause=ann.get(CHANGE_CAUSE_ANNOTATION),
            ready_replicas=rs.status.ready_replicas or 0,
            is_current=(rev == cur_rev),
        ))
    revs.sort(key=lambda r: int(r.revision) if (r.revision or "").isdigit() else -1,
              reverse=True)
    return revs


def check_application_health(namespace: str = DEFAULT_NAMESPACE,
                             service: str = DEFAULT_SERVICE,
                             path: str = "health",
                             port: str = "http") -> HealthResult:
    """Independent app-health signal via the API server's service proxy.

    No port-forward needed: the API server proxies to a Ready endpoint of the
    Service. The service-proxy name MUST include the port (``svc:port``) for a
    named port, otherwise the API server returns a misleading "no endpoints
    available" 503. A real 503 (app unhealthy or no ready endpoints) is
    captured, not raised.
    """
    _, core = _load()
    try:
        body = core.connect_get_namespaced_service_proxy_with_path(
            name=f"{service}:{port}", namespace=namespace, path=path,
        )
        return HealthResult(namespace=namespace, service=service, path=path,
                            healthy=True, status_code=200, body=str(body)[:300])
    except ApiException as e:
        return HealthResult(namespace=namespace, service=service, path=path,
                            healthy=False, status_code=e.status,
                            body=(e.body[:300] if isinstance(e.body, str) else None),
                            error=f"HTTP {e.status}")
    except Exception as e:  # cluster unreachable, DNS failure, etc.
        return HealthResult(namespace=namespace, service=service, path=path,
                            healthy=False, error=repr(e))


def gather_evidence(namespace: str = DEFAULT_NAMESPACE,
                    deployment: str = DEFAULT_DEPLOYMENT,
                    service: str = DEFAULT_SERVICE) -> dict:
    """Aggregate every read-only tool into one bundle (best-effort per tool)."""
    tools = {
        "workload": lambda: inspect_workload(namespace, deployment),
        "pods": lambda: inspect_pods(namespace, deployment),
        "events": lambda: inspect_events(namespace, deployment),
        "recent_changes": lambda: recent_changes(namespace, deployment),
        "application_health": lambda: check_application_health(namespace, service),
    }
    bundle: dict = {}
    for key, fn in tools.items():
        try:
            v = fn()
            bundle[key] = [i.model_dump() for i in v] if isinstance(v, list) else v.model_dump()
        except ApiException as e:
            bundle[key] = ToolError(tool=key, error=f"HTTP {e.status}",
                                    detail=(e.reason or "")).model_dump()
        except Exception as e:
            bundle[key] = ToolError(tool=key, error="exception", detail=repr(e)).model_dump()
    return bundle


def collect(namespace: str = DEFAULT_NAMESPACE,
            deployment: str = DEFAULT_DEPLOYMENT,
            service: str = DEFAULT_SERVICE) -> EvidenceSnapshot:
    """Collect one typed evidence snapshot from the live cluster.

    Unlike ``gather_evidence`` (dict, for UI/JSON), this returns typed objects
    for the internal pipeline. Raises on a hard cluster failure for the workload
    read (no workload = nothing to reason about); softer signals degrade to
    empty/`healthy=False` rather than aborting.
    """
    workload = inspect_workload(namespace, deployment)
    try:
        pods = inspect_pods(namespace, deployment)
    except Exception:
        pods = []
    try:
        events = inspect_events(namespace, deployment)
    except Exception:
        events = []
    try:
        changes = recent_changes(namespace, deployment)
    except Exception:
        changes = []
    health = check_application_health(namespace, service)
    return EvidenceSnapshot(
        namespace=namespace, deployment=deployment, service=service,
        workload=workload, pods=pods, events=events,
        recent_changes=changes, application_health=health,
    )


if __name__ == "__main__":
    import json
    import sys

    ns = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_NAMESPACE
    print(json.dumps(gather_evidence(namespace=ns), indent=2, default=str))