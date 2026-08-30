"""
Verification — independently confirms service recovery after execution.

Rules:
  - Re-reads the cluster through the same evidence interface.
  - Requires TWO independent signals: Kubernetes rollout health AND
    application /health endpoint.
  - Never trusts the execution API response as proof of recovery.
  - FAIL and INCONCLUSIVE are never softened to PASS.
"""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Protocol

from agent.models import (
    Incident,
    IncidentState,
    VerificationResult,
    VerificationSignal,
)

log = logging.getLogger("kubemedic.verification")

# Verification timeout — same as BOB_TIMEOUT default
VERIFY_TIMEOUT_S = 60


class EvidenceReader(Protocol):
    """Minimal read-only interface to the cluster.  Tests inject a fake."""
    def get_workload_status(self, name: str, namespace: str) -> dict[str, Any]: ...
    def get_application_health(self, name: str, namespace: str) -> dict[str, Any]: ...


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def verify(
    incident: Incident,
    reader: EvidenceReader,
) -> tuple[Incident, VerificationResult]:
    """
    Re-read cluster state and confirm two independent signals.

    Signal 1 — Kubernetes rollout healthy:
        workload_status["ready"] is True and
        workload_status.get("updated_replicas") == workload_status.get("desired_replicas")

    Signal 2 — Application health:
        health["status_code"] == 200 (or health["healthy"] is True)

    Outcome:
      PASS         — both signals green
      FAIL         — either signal red
      INCONCLUSIVE — a verification tool itself errored

    Never returns PASS unless both signals are explicitly confirmed.
    """
    if incident.state != IncidentState.EXECUTED:
        raise ValueError(
            f"Cannot verify: incident is in state {incident.state}, expected EXECUTED"
        )
    if incident.plan is None:
        raise ValueError("Cannot verify: incident has no remediation plan")

    namespace = (incident.evidence.namespace if incident.evidence else "default")
    target = incident.plan.target
    signals: list[VerificationSignal] = []
    inconclusive_reason: str | None = None

    # Signal 1: rollout health
    try:
        ws = reader.get_workload_status(target, namespace)
        rollout_ok = bool(ws.get("ready", False)) and (
            ws.get("updated_replicas") == ws.get("desired_replicas")
            or ws.get("available_replicas", 0) >= ws.get("desired_replicas", 1)
        )
        signals.append(VerificationSignal(
            name="rollout_healthy",
            passed=rollout_ok,
            detail=f"ready={ws.get('ready')}, updated={ws.get('updated_replicas')}, desired={ws.get('desired_replicas')}",
        ))
    except Exception as exc:
        log.error("[VERIFY] get_workload_status failed: %s", exc)
        inconclusive_reason = f"get_workload_status errored: {exc}"
        signals.append(VerificationSignal(
            name="rollout_healthy",
            passed=False,
            detail=str(exc),
        ))

    # Signal 2: application health
    try:
        health = reader.get_application_health(target, namespace)
        health_ok = (
            health.get("status_code") == 200
            or health.get("healthy") is True
        )
        signals.append(VerificationSignal(
            name="health_endpoint",
            passed=health_ok,
            detail=f"status_code={health.get('status_code')}, healthy={health.get('healthy')}",
        ))
    except Exception as exc:
        log.error("[VERIFY] get_application_health failed: %s", exc)
        if inconclusive_reason is None:
            inconclusive_reason = f"get_application_health errored: {exc}"
        signals.append(VerificationSignal(
            name="health_endpoint",
            passed=False,
            detail=str(exc),
        ))

    # Derive outcome
    if inconclusive_reason:
        outcome = "INCONCLUSIVE"
        detail = inconclusive_reason
    elif all(s.passed for s in signals):
        outcome = "PASS"
        detail = "Both signals green: rollout healthy and application health OK."
    else:
        outcome = "FAIL"
        failed = [s.name for s in signals if not s.passed]
        detail = f"Signals failed: {', '.join(failed)}"

    result = VerificationResult(outcome=outcome, signals=signals, detail=detail)
    incident.verification = result
    incident.audit_log.append(
        {
            "step": "verification",
            "outcome": outcome,
            "signals": [s.model_dump() for s in signals],
            "detail": detail,
            "checked_at": result.checked_at.isoformat(),
        }
    )

    new_state = (
        IncidentState.RESOLVED
        if outcome == "PASS"
        else IncidentState.VERIFICATION_FAILED
    )
    incident.transition(new_state)
    log.info("[VERIFY] outcome=%s signals=%s", outcome, [s.name for s in signals])
    return incident, result


# ---------------------------------------------------------------------------
# Settling before verification
# ---------------------------------------------------------------------------

DEFAULT_SETTLE_TIMEOUT_S = 90
DEFAULT_SETTLE_INTERVAL_S = 5


def _settle_window() -> tuple[int, int]:
    """
    Read at call time, not import time, so a test (or an operator) can shorten
    the window without reloading the module. A suite that inherits a 90s wait
    stops being a suite.
    """
    return (
        int(os.getenv("KUBEMEDIC_SETTLE_TIMEOUT_SECONDS", DEFAULT_SETTLE_TIMEOUT_S)),
        int(os.getenv("KUBEMEDIC_SETTLE_INTERVAL_SECONDS", DEFAULT_SETTLE_INTERVAL_S)),
    )


def wait_for_recovery(
    reader: EvidenceReader,
    target: str,
    namespace: str,
    timeout_s: int | None = None,
    interval_s: int | None = None,
) -> tuple[bool, str]:
    """
    Give the cluster a bounded window to converge before verifying.

    A rollback returns the moment the API server accepts the patch, but the
    controller then takes tens of seconds to replace pods. Verifying
    immediately reports FAIL on a remediation that is working -- which is worse
    than useless, because it teaches a reviewer to distrust a signal that is
    usually right.

    This does NOT soften the outcome. It waits for the rollout to report
    healthy, and if the window expires it returns anyway and lets verify()
    report exactly what it finds. A remediation that has not converged in the
    window has genuinely not converged.

    Returns (settled, detail) for the audit trail, so a record shows whether
    the verdict came from a settled cluster or an expired wait.
    """
    env_timeout, env_interval = _settle_window()
    timeout_s = env_timeout if timeout_s is None else timeout_s
    interval_s = env_interval if interval_s is None else interval_s

    deadline = time.monotonic() + max(0, timeout_s)
    last = "no reading taken"
    attempts = 0

    while True:
        attempts += 1
        try:
            status = reader.get_workload_status(target, namespace)
            last = (
                f"ready={status.get('ready')} "
                f"updated={status.get('updated_replicas')} "
                f"desired={status.get('desired_replicas')}"
            )
            if status.get("ready"):
                elapsed = int(timeout_s - max(0, deadline - time.monotonic()))
                return True, f"settled after ~{elapsed}s ({attempts} checks): {last}"
        except Exception as exc:
            # A read failure during settling is not a verdict. verify() will
            # make the call, and an error there becomes INCONCLUSIVE.
            last = f"read failed: {exc}"

        if time.monotonic() >= deadline:
            return False, (
                f"did not settle within {timeout_s}s ({attempts} checks); "
                f"last reading: {last}"
            )
        time.sleep(min(interval_s, max(0, deadline - time.monotonic())))
