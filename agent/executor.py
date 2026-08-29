"""
Executor — performs one allowlisted Kubernetes action after approval is confirmed.

Rules:
  - Raises if incident is not APPROVED.
  - Raises on REJECTED→EXECUTING (enforced by Incident.transition).
  - Never runs a shell string. Action is an AllowedAction enum; target is validated.
  - Idempotent: an already-EXECUTED incident returns its existing ExecutionResult.
  - The real Kubernetes calls are injected via the `kubernetes_client` parameter
    so tests never need a live cluster.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable, Protocol

from agent.models import (
    AllowedAction,
    ExecutionResult,
    Incident,
    IncidentState,
    RemediationPlan,
)

log = logging.getLogger("kubemedic.executor")


# ---------------------------------------------------------------------------
# Kubernetes action protocol — the real implementation lives in mcp_server/
# or a thin wrapper; tests inject a fake.
# ---------------------------------------------------------------------------

class KubernetesClient(Protocol):
    def rollback_deployment(
        self, name: str, namespace: str, to_revision: int | None = None
    ) -> dict[str, Any]: ...

    def restart_deployment(self, name: str, namespace: str) -> dict[str, Any]: ...

    def scale_workload(
        self, name: str, namespace: str, replicas: int
    ) -> dict[str, Any]: ...


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def execute(
    incident: Incident,
    kubernetes: KubernetesClient,
) -> tuple[Incident, ExecutionResult]:
    """
    Execute the remediation plan on the cluster.

    Preconditions (all raise ValueError if not met):
      - incident.state == APPROVED
      - incident.plan is set
      - incident.execution is None (idempotency: returns existing result otherwise)

    Postcondition:
      - incident.state transitions to EXECUTING then EXECUTED (or stays at
        EXECUTED on a repeated call).
    """
    # Idempotency: second execute request returns existing state unchanged.
    if incident.state == IncidentState.EXECUTED and incident.execution is not None:
        log.info(
            "[EXECUTOR] %s already executed — returning existing result",
            incident.incident_id,
        )
        return incident, incident.execution

    # Guard: must be APPROVED
    incident.require_approval()  # raises ValueError if not APPROVED

    plan = incident.plan
    if plan is None:
        raise ValueError(
            f"Incident {incident.incident_id} has no remediation plan"
        )

    incident.transition(IncidentState.EXECUTING)
    incident.audit_log.append(
        {
            "step": "execute",
            "action": plan.action.value,
            "target": plan.target,
            "parameters": plan.action_parameters,
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
    )

    try:
        raw_response = _dispatch(plan, kubernetes, incident.evidence.namespace if incident.evidence else "default")
        success = True
        message = f"{plan.action.value} on {plan.target} succeeded"
    except Exception as exc:
        raw_response = {"error": str(exc)}
        success = False
        message = f"{plan.action.value} on {plan.target} failed: {exc}"
        log.error("[EXECUTOR] %s", message)

    result = ExecutionResult(
        action=plan.action,
        target=plan.target,
        success=success,
        message=message,
        raw_response=raw_response,
    )

    incident.execution = result
    incident.transition(IncidentState.EXECUTED)
    incident.audit_log.append(
        {
            "step": "execute_result",
            "success": success,
            "message": message,
            "completed_at": result.executed_at.isoformat(),
        }
    )
    log.info("[EXECUTOR] %s success=%s", plan.action.value, success)
    return incident, result


def _dispatch(
    plan: RemediationPlan,
    k8s: KubernetesClient,
    namespace: str,
) -> dict[str, Any]:
    """Route to the correct Kubernetes API call. Raises on unknown action."""
    action = plan.action
    target = plan.target
    params = plan.action_parameters

    if action == AllowedAction.rollback_deployment:
        revision = params.get("to_revision")
        return k8s.rollback_deployment(target, namespace, to_revision=revision)

    if action == AllowedAction.restart_deployment:
        return k8s.restart_deployment(target, namespace)

    if action == AllowedAction.scale_workload:
        replicas = int(params["replicas"])
        return k8s.scale_workload(target, namespace, replicas=replicas)

    # This branch is unreachable if AllowedAction is exhaustive, but keeps
    # the function safe against future enum additions.
    raise ValueError(f"Unhandled action: {action}")  # pragma: no cover
