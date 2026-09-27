"""
HTTP surface over the incident lifecycle.

WHY THIS EXISTS
---------------
run_full_pipeline() takes the human decision as an argument, so it cannot
pause at the approval gate — by the time it runs, the decision has already
been made. That is fine for a test and useless for a review. A real human
review needs the incident to sit in PENDING_APPROVAL across requests while a
person reads it.

So this module calls the stages individually and holds the Incident between
calls. Every safety property still lives in agent/ — this layer adds no
authority. It cannot execute an unapproved plan because execute() checks
require_approval(); it cannot record a rejection without a reason because
HumanDecision refuses to construct; it cannot verify a claim it did not check
because verify() re-reads the cluster itself.

STATE
-----
Incidents live in an in-process dict, so a restart loses them. Audit records
on disk are the durable artifact. For a proof of concept this is the right
trade — but it is a stated limitation, not an oversight.
"""
from __future__ import annotations

import logging
import os
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from agent.adapters import collect_agent_evidence, tickets_to_references
from agent import auth
from agent.auth import Principal, require_presenter_tools, require_role
from agent.audit import record_decision, write_record
from agent.correlation import correlate
from agent.executor import execute
from agent.models import (
    MAX_REVISIONS,
    HumanDecision,
    Incident,
    IncidentRecord,
    IncidentState,
)
from agent.pipeline import plan_remediation, request_revision
from agent.reasoning import run_analysis
from agent.store import get_store
from agent.verification import verify, wait_for_recovery

log = logging.getLogger("kubemedic.api")

DEFAULT_NAMESPACE = os.getenv("KUBEMEDIC_NAMESPACE", "opspilot")
DEFAULT_DEPLOYMENT = os.getenv("KUBEMEDIC_DEPLOYMENT", "ticket-booking")
DEFAULT_SERVICE = os.getenv("KUBEMEDIC_SERVICE", "ticket-booking")


def allowed_namespaces() -> set[str]:
    """
    Namespaces an incident may be opened against.

    Read at call time so it can be changed without a restart. The default is the
    one watched namespace: a request body must not be able to point evidence
    collection and remediation at any namespace the process's credentials
    happen to reach.
    """
    raw = os.getenv("KUBEMEDIC_ALLOWED_NAMESPACES") or DEFAULT_NAMESPACE
    return {n.strip() for n in raw.split(",") if n.strip()}

app = FastAPI(
    title="KubeMedic Agent API",
    version="1.0.0",
    description=(
        "Evidence, IBM Bob reasoning, human review and verified remediation "
        "for a Kubernetes workload. Nothing mutates the cluster without a "
        "recorded human approval."
    ),
)

# incident_id -> Incident. A cache in front of agent/store.py, which is the
# durable copy: every mutation is written through, and a restart reloads from it.
_INCIDENTS: dict[str, Incident] = {}

# One in-flight execution per incident. Execution is check-then-act on the
# incident's state, so two concurrent requests could otherwise both pass the
# approval check before either had moved the state on.
_EXEC_LOCKS: dict[str, threading.Lock] = {}
_EXEC_LOCKS_GUARD = threading.Lock()


def _exec_lock(incident_id: str) -> threading.Lock:
    with _EXEC_LOCKS_GUARD:
        return _EXEC_LOCKS.setdefault(incident_id, threading.Lock())


def _persist(incident: Incident) -> None:
    """Write through to the durable store. A failure here must not be silent."""
    _INCIDENTS[incident.incident_id] = incident
    try:
        get_store().save(incident)
    except Exception as exc:
        log.error("[API] could not persist %s: %s", incident.incident_id, exc)
        raise HTTPException(
            503,
            detail={"error": "persistence_failed",
                    "message": f"Could not record incident state: {exc}"},
        ) from exc

# Minimal operator console, served from this same process so there is exactly
# one thing to start when checking the system. static/ is plain HTML, CSS and
# JavaScript -- no build step, no framework, and nothing to install.
_STATIC = Path(__file__).resolve().parent.parent / "static"
if _STATIC.is_dir():
    app.mount("/ui", StaticFiles(directory=str(_STATIC), html=True), name="ui")


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse(url="/ui/")


# ---------------------------------------------------------------------------
# Cluster access, injected so tests never need a live cluster
# ---------------------------------------------------------------------------

def get_cluster():
    """
    The live cluster client. Overridden in tests via dependency_overrides.

    Imported lazily: the API must be importable, and its contract testable,
    on a machine with no kubeconfig.
    """
    if _DEMO["active"] and _DEMO["cluster"] is not None:
        return _DEMO["cluster"]

    from agent.k8s_client import LiveCluster

    return LiveCluster()


# ---------------------------------------------------------------------------
# Request and response bodies
# ---------------------------------------------------------------------------

class CreateIncidentRequest(BaseModel):
    namespace: str = DEFAULT_NAMESPACE
    deployment: str = DEFAULT_DEPLOYMENT
    service: str = DEFAULT_SERVICE
    ticket_status: str | None = "open"


class ReviewRequest(BaseModel):
    """
    The human decision.

    `feedback` is optional here on purpose. Rejection without a reason is
    refused explicitly in the handler with 400 feedback_required, so the API
    returns our message rather than a pydantic 422 the UI would have to
    interpret.
    """
    decision: Literal["APPROVED", "REJECTED", "approved", "rejected"]
    approver: str = "web-ui"
    feedback: str | None = None

    @property
    def normalised(self) -> str:
        return self.decision.lower()


class IncidentSummary(BaseModel):
    incident_id: str
    state: str
    ticket_ids: list[str]
    ticket_count: int
    recommended_action: str | None = None
    action_target: str | None = None
    analysis_source: str | None = None
    root_cause: str | None = None
    revision_count: int = 0
    feedback_history: list[str] = Field(default_factory=list)
    created_at: str
    updated_at: str


def _summary(inc: Incident) -> IncidentSummary:
    return IncidentSummary(
        incident_id=inc.incident_id,
        state=inc.state.value,
        ticket_ids=[t.ticket_id for t in inc.tickets],
        ticket_count=len(inc.tickets),
        recommended_action=inc.plan.action.value if inc.plan else None,
        action_target=inc.plan.target if inc.plan else None,
        analysis_source=inc.analysis.analysis_source if inc.analysis else None,
        root_cause=(
            inc.analysis.root_cause.statement
            if inc.analysis and inc.analysis.root_cause
            else None
        ),
        revision_count=inc.revision_count,
        feedback_history=list(inc.feedback_history),
        created_at=inc.created_at.isoformat(),
        updated_at=inc.updated_at.isoformat(),
    )


def _require(incident_id: str) -> Incident:
    incident = _INCIDENTS.get(incident_id)
    if incident is None:
        try:
            incident = get_store().get(incident_id)
        except Exception as exc:
            log.error("[API] could not read %s from the store: %s", incident_id, exc)
            incident = None
        if incident is not None:
            _INCIDENTS[incident_id] = incident
    if incident is None:
        raise HTTPException(404, detail=f"Unknown incident {incident_id}")
    return incident


# ---------------------------------------------------------------------------
# Health and tickets
# ---------------------------------------------------------------------------

@app.get("/api/health")
def health() -> dict[str, Any]:
    """Liveness. Cheap by design -- never calls a model or the cluster."""
    from agent.providers import configured_provider_name

    return {
        "status": "ok",
        "service": "kubemedic-agent-api",
        "reasoning_provider": configured_provider_name(),
    }


@app.get("/api/cluster")
def cluster_status(_: Principal = Depends(require_role("viewer"))) -> dict[str, Any]:
    """Live cluster state. Never a canned response — if it cannot be read, it says so."""
    if _DEMO["active"]:
        cluster = _DEMO["cluster"]
        status = cluster.get_workload_status("ticket-booking", "opspilot")
        return {
            "reachable": True,
            "demo": True,
            "detail": "deterministic fixture cluster (demo mode)",
            "workload": {
                "name": cluster.deployment, "image": cluster.image,
                "revision": str(cluster.current_revision),
                "ready_replicas": status["ready_replicas"],
                "desired_replicas": status["desired_replicas"],
                "rollout_complete": status["rollout_complete"],
            },
            "application_health": cluster.get_application_health(
                "ticket-booking", "opspilot"),
            "pods": [
                {"name": "ticket-booking-7d6b9-new", "ready": cluster.healthy,
                 "image": cluster.image},
                {"name": "ticket-booking-5594-old", "ready": True,
                 "image": "ticketbooking:1.0"},
            ],
        }

    from agent.k8s_client import is_cluster_reachable

    reachable, detail = is_cluster_reachable()
    if not reachable:
        return {"reachable": False, "detail": detail}
    try:
        evidence = collect_agent_evidence(
            DEFAULT_NAMESPACE, DEFAULT_DEPLOYMENT, DEFAULT_SERVICE
        )
        return {
            "reachable": True,
            "detail": detail,
            "workload": evidence.raw.get("workload"),
            "application_health": evidence.application_health,
            "pods": evidence.pod_states,
        }
    except Exception as exc:
        return {"reachable": False, "detail": f"evidence collection failed: {exc}"}


# ---------------------------------------------------------------------------
# Demo mode
#
# The console must be usable without a Kubernetes cluster -- on a judge's
# laptop, in CI, or when the cluster is simply not up. Demo mode swaps the live
# cluster for the deterministic fixture from scripts/dry_run.py.
#
# The fixture is the *cluster*, not the logic: correlation, the approval gate,
# the executor allowlist, the verifier and the audit trail are the real code
# paths, and the reasoning provider is whichever one is configured. Only the
# thing being observed and mutated is simulated, and it behaves rather than
# agrees -- a rollback to a revision that does not exist fails, and a restart
# does not recover the service.
# ---------------------------------------------------------------------------

_DEMO: dict[str, Any] = {"active": False, "cluster": None}


def _fixture_cluster():
    from scripts.dry_run import FixtureCluster

    return FixtureCluster()


@app.get("/api/demo")
def demo_status(_: Principal = Depends(require_role("viewer"))) -> dict[str, Any]:
    from agent.k8s_client import is_cluster_reachable

    reachable, detail = is_cluster_reachable()
    return {
        "demo_active": _DEMO["active"],
        "live_cluster_reachable": reachable,
        "live_cluster_detail": detail,
        "note": (
            "Demo mode uses a deterministic fixture cluster. Correlation, the "
            "approval gate, the executor and the verifier are the real ones."
        ),
    }


@app.post("/api/demo/start")
def demo_start(_: Principal = Depends(require_presenter_tools)) -> dict[str, Any]:
    """
    Reset the fixture to the broken state and file the three tickets a watcher
    would file. Returns nothing that has been reasoned about yet -- creating
    the incident is still POST /api/incidents.
    """
    from scripts.dry_run import seed_tickets

    _DEMO["active"] = True
    _DEMO["cluster"] = _fixture_cluster()
    _INCIDENTS.clear()

    tickets = seed_tickets(datetime.now(timezone.utc))
    _DEMO["tickets"] = tickets
    log.info("[DEMO] fixture reset, %d ticket(s) seeded", len(tickets))
    return {
        "demo_active": True,
        "tickets": [
            {"id": t.ticket_id, "title": t.title, "severity": t.severity,
             "symptom": t.reported_symptom}
            for t in tickets
        ],
        "workload": _DEMO["cluster"].get_workload_status("ticket-booking", "opspilot"),
    }


@app.post("/api/demo/stop")
def demo_stop(_: Principal = Depends(require_presenter_tools)) -> dict[str, Any]:
    _DEMO.update({"active": False, "cluster": None, "tickets": []})
    _INCIDENTS.clear()
    return {"demo_active": False}


# ---------------------------------------------------------------------------
# Live cluster orchestration for the demo
#
# Fault injection is presenter tooling, not an agent capability -- it lives in
# agent/demo_tooling.py so the executor's allowlist stays exactly three
# actions and nothing the model can reach can ship a bad image.
# ---------------------------------------------------------------------------

@app.post("/api/live/inject")
def live_inject(_: Principal = Depends(require_presenter_tools)) -> dict[str, Any]:
    """Ship the bad image at the live cluster. Reversible by rollback."""
    from agent import demo_tooling

    _DEMO["active"] = False          # injecting means we are on the real thing
    try:
        closed = demo_tooling.close_open_tickets()
        result = demo_tooling.inject_incident()
    except Exception as exc:
        raise HTTPException(503, detail=f"Injection failed: {exc}") from exc
    return {"injected": True, "tickets_closed": closed, **result}


@app.post("/api/live/watch")
def live_watch(_: Principal = Depends(require_presenter_tools)) -> dict[str, Any]:
    """
    One watcher pass. Reports what it observed as well as what it filed --
    "0 filed" and a broken watcher look identical otherwise.
    """
    from agent import demo_tooling

    try:
        return demo_tooling.run_watcher_once()
    except Exception as exc:
        raise HTTPException(503, detail=f"Watcher failed: {exc}") from exc


@app.post("/api/live/reset")
def live_reset(_: Principal = Depends(require_presenter_tools)) -> dict[str, Any]:
    """Restore the healthy image and resolve open tickets."""
    from agent import demo_tooling

    try:
        closed = demo_tooling.close_open_tickets()
        result = demo_tooling.reset_healthy()
    except Exception as exc:
        raise HTTPException(503, detail=f"Reset failed: {exc}") from exc
    _INCIDENTS.clear()
    return {"reset": True, "tickets_closed": closed, **result}


@app.get("/api/tickets")
def list_tickets(
    status: str | None = None, _: Principal = Depends(require_role("viewer"))
) -> list[dict[str, Any]]:
    """Real tickets from the store. No fabrication."""
    if _DEMO["active"]:
        return [
            {"id": t.ticket_id, "title": t.title, "status": "open",
             "severity": t.severity or "high", "deployment": t.named_workload,
             "signals": [t.reported_symptom or ""],
             "created_at": t.created_at.isoformat() if t.created_at else None}
            for t in _DEMO.get("tickets", [])
        ]

    from mcp_server import tickets as ticket_store
    from mcp_server.db import init_db

    init_db()                    # idempotent; a fresh volume has no table yet
    return [t.model_dump(mode="json") for t in ticket_store.list_tickets(status=status)]


# ---------------------------------------------------------------------------
# Incident lifecycle
# ---------------------------------------------------------------------------

@app.post("/api/incidents", response_model=IncidentSummary, status_code=201)
def create_incident(
    body: CreateIncidentRequest, principal: Principal = Depends(require_role("approver"))
) -> IncidentSummary:
    """
    Collect evidence, correlate the open tickets, ask IBM Bob, build a plan.

    Stops at PENDING_APPROVAL. It does not execute, and it never advances past
    BOB_UNAVAILABLE — an incident with no analysis gets no plan.
    """
    if _DEMO["active"]:
        from scripts.dry_run import collect_evidence

        evidence = collect_evidence(_DEMO["cluster"])
        references = list(_DEMO.get("tickets", []))
    else:
        if body.namespace not in allowed_namespaces():
            raise HTTPException(
                400,
                detail={
                    "error": "namespace_not_allowed",
                    "message": (
                        f"Namespace {body.namespace!r} is not in "
                        "KUBEMEDIC_ALLOWED_NAMESPACES."
                    ),
                },
            )
        from mcp_server import tickets as ticket_store
        from mcp_server.db import init_db

        init_db()
        try:
            evidence = collect_agent_evidence(
                body.namespace, body.deployment, body.service
            )
        except Exception as exc:
            raise HTTPException(
                503, detail=f"Evidence collection failed: {exc}"
            ) from exc

        references = tickets_to_references(
            ticket_store.list_tickets(status=body.ticket_status)
        )

    incident, excluded = correlate(references, evidence)
    log.info(
        "[API] %s correlated %d ticket(s), %d excluded",
        incident.incident_id, len(incident.tickets), len(excluded),
    )

    incident, _ = run_analysis(incident)
    if incident.state != IncidentState.BOB_UNAVAILABLE:
        incident = plan_remediation(incident)

    incident.audit_log.append(
        {"step": "incident_opened", "by": principal.identity}
    )
    _persist(incident)
    return _summary(incident)


@app.get("/api/incidents", response_model=list[IncidentSummary])
def list_incidents(
    _: Principal = Depends(require_role("viewer")),
) -> list[IncidentSummary]:
    merged = dict(_INCIDENTS)
    try:
        for stored in get_store().list():
            merged.setdefault(stored.incident_id, stored)
    except Exception as exc:
        log.error("[API] could not list stored incidents: %s", exc)
    return [_summary(i) for i in merged.values()]


@app.get("/api/incidents/{incident_id}")
def get_incident(
    incident_id: str, _: Principal = Depends(require_role("viewer"))
) -> dict[str, Any]:
    """
    The whole incident: evidence, correlation, Bob's hypotheses and root cause,
    the plan, the decision, execution, verification and the audit log. This is
    what a reviewer reads before deciding.
    """
    return _require(incident_id).model_dump(mode="json")


@app.post("/api/incidents/{incident_id}/review", response_model=IncidentSummary)
def review_incident(
    incident_id: str,
    body: ReviewRequest,
    principal: Principal = Depends(require_role("approver")),
) -> IncidentSummary:
    """
    The human approval gate.

    Approval may be direct. **Rejection requires a reason** — it is refused with
    400 feedback_required otherwise. The reason is not a formality: it is added
    to the incident's context and sent to IBM Bob for the revised plan, so a
    rejection without one would leave the agent unable to do anything different.
    """
    incident = _require(incident_id)
    decision = body.normalised

    if decision == "rejected" and not (body.feedback or "").strip():
        raise HTTPException(
            400,
            detail={
                "error": "feedback_required",
                "message": (
                    "A rejection must say why. The reason is added to the "
                    "incident context and sent to IBM Bob for the revised plan."
                ),
            },
        )

    # With auth on, the approver is who the token says they are. The body's
    # `approver` is only honoured in development, where there is no token.
    approver = principal.identity if auth.auth_required() else body.approver
    try:
        human = HumanDecision(
            decision=decision, approver=approver, feedback=body.feedback
        )
        incident = record_decision(incident, human)
    except ValueError as exc:
        raise HTTPException(409, detail=str(exc)) from exc

    _persist(incident)
    return _summary(incident)


@app.post("/api/incidents/{incident_id}/revise", response_model=IncidentSummary)
def revise_incident(
    incident_id: str, principal: Principal = Depends(require_role("approver"))
) -> IncidentSummary:
    """
    Ask Bob for a revised plan that answers the reviewer's objection.

    Returns the incident to PENDING_APPROVAL for a second review. Capped at
    MAX_REVISIONS: an incident refused that many times needs a human to act
    rather than another proposal.
    """
    incident = _require(incident_id)
    try:
        incident = request_revision(incident)
    except ValueError as exc:
        raise HTTPException(409, detail=str(exc)) from exc

    _persist(incident)
    return _summary(incident)


@app.post("/api/incidents/{incident_id}/execute")
def execute_incident(
    incident_id: str,
    cluster=Depends(get_cluster),
    principal: Principal = Depends(require_role("approver")),
) -> dict[str, Any]:
    """
    Perform the approved action, then verify recovery independently.

    Refused unless the incident is APPROVED — the guard is in the executor, not
    here, so no API path can route around it. Verification re-reads the cluster
    on two independent signals and is never inferred from the execution
    response.
    """
    incident = _require(incident_id)

    lock = _exec_lock(incident_id)
    if not lock.acquire(blocking=False):
        raise HTTPException(
            409,
            detail={"error": "execution_in_progress",
                    "message": "This incident is already being executed."},
        )
    try:
        return _execute_locked(incident, cluster, principal)
    finally:
        lock.release()


def _execute_locked(incident: Incident, cluster, principal: Principal) -> dict[str, Any]:
    if incident.state == IncidentState.APPROVED:
        incident.audit_log.append(
            {"step": "execute_requested", "by": principal.identity}
        )
    try:
        incident, result = execute(incident, cluster)
    except ValueError as exc:
        raise HTTPException(409, detail=str(exc)) from exc

    verification = None
    if result.success:
        # Give the cluster a bounded window to converge first. A rollback
        # returns as soon as the API server accepts the patch, but the
        # controller takes tens of seconds to replace pods -- verifying
        # immediately reports FAIL on a remediation that is working, which
        # teaches a reviewer to distrust a signal that is usually right.
        #
        # This does not soften the verdict: if the window expires, verify()
        # still reports exactly what it finds.
        settled, detail = wait_for_recovery(
            cluster, incident.plan.target,
            incident.evidence.namespace if incident.evidence else "default",
        )
        incident.audit_log.append(
            {"step": "settle", "settled": settled, "detail": detail}
        )
        incident, verification = verify(incident, cluster)

    record_path = write_record(incident)
    _persist(incident)

    return {
        "incident": _summary(incident).model_dump(),
        "execution": result.model_dump(mode="json"),
        "verification": verification.model_dump(mode="json") if verification else None,
        "record": str(record_path),
    }


@app.get("/api/incidents/{incident_id}/record")
def get_record(
    incident_id: str, _: Principal = Depends(require_role("viewer"))
) -> dict[str, Any]:
    """The audit artifact for this incident, built from its current state."""
    incident = _require(incident_id)
    return IncidentRecord.from_incident(incident).model_dump(mode="json")


@app.get("/api/incidents/{incident_id}/events")
def incident_events(
    incident_id: str, _: Principal = Depends(require_role("viewer"))
) -> dict[str, Any]:
    """The incident's audit events as chained in the durable store."""
    _require(incident_id)
    return {"incident_id": incident_id, "events": get_store().events(incident_id)}


@app.get("/api/audit/verify")
def audit_verify(_: Principal = Depends(require_role("viewer"))) -> dict[str, Any]:
    """
    Recompute the audit hash chain. `head` is worth recording somewhere the
    database's writer cannot reach: it commits to every event before it.
    """
    store = get_store()
    intact, broken_at = store.verify_chain()
    return {"intact": intact, "broken_at_seq": broken_at, "head": store.chain_head()}


# ---------------------------------------------------------------------------
# Compatibility aliases for the dashboard
#
# dashboard/api_adapter.py was written against an unprefixed surface --
# GET /incidents, GET /incidents/{id}, POST /incidents/{id}/decision -- while
# this module serves /api/... and calls the review route "review".
#
# Aliasing here rather than editing the adapter keeps the seam in one place and
# means either spelling works. They delegate to the same handlers, so there is
# no second implementation of the approval gate to keep in step.
# ---------------------------------------------------------------------------

@app.get("/incidents", response_model=list[IncidentSummary])
def list_incidents_alias(
    principal: Principal = Depends(require_role("viewer")),
) -> list[IncidentSummary]:
    return list_incidents(principal)


@app.get("/incidents/{incident_id}")
def get_incident_alias(
    incident_id: str, principal: Principal = Depends(require_role("viewer"))
) -> dict[str, Any]:
    return get_incident(incident_id, principal)


@app.post("/incidents/{incident_id}/decision", response_model=IncidentSummary)
def review_incident_alias(
    incident_id: str,
    body: ReviewRequest,
    principal: Principal = Depends(require_role("approver")),
) -> IncidentSummary:
    return review_incident(incident_id, body, principal)


@app.post("/incidents/{incident_id}/execute")
def execute_incident_alias(
    incident_id: str,
    cluster=Depends(get_cluster),
    principal: Principal = Depends(require_role("approver")),
) -> dict[str, Any]:
    return execute_incident(incident_id, cluster, principal)


@app.post("/incidents/{incident_id}/revise", response_model=IncidentSummary)
def revise_incident_alias(
    incident_id: str, principal: Principal = Depends(require_role("approver"))
) -> IncidentSummary:
    return revise_incident(incident_id, principal)


@app.get("/health/ai")
def health_ai(_: Principal = Depends(require_role("viewer"))) -> dict[str, Any]:
    """
    Which engine will answer, and why.

    Never exposes a credential -- only whether one is present. Deliberately
    does not probe the network: a health endpoint that calls a model API turns
    a slow third party into a red dashboard.
    """
    from agent.providers import (
        fallback_enabled,
        fallback_name,
        get_provider,
        primary_name,
    )

    def status_of(name: str) -> tuple[str, str]:
        try:
            configured, detail = get_provider(name).is_configured()
        except SystemExit:
            return "unknown_provider", f"{name} is not a known provider"
        except Exception as exc:
            return "error", str(exc)
        return ("available" if configured else "not_configured"), detail

    primary, secondary = primary_name(), fallback_name()
    primary_status, primary_detail = status_of(primary)
    fallback_status, fallback_detail = status_of(secondary)

    if primary_status == "available":
        active = primary
    elif fallback_enabled() and fallback_status == "available":
        active = secondary
    else:
        active = None


    return {
        "primary_provider": primary,
        "primary_status": primary_status,
        "primary_detail": primary_detail,
        "fallback_provider": secondary,
        "fallback_status": fallback_status,
        "fallback_detail": fallback_detail,
        "fallback_enabled": fallback_enabled(),
        "active_provider": active,
    }


class SelectProviderRequest(BaseModel):
    """Which reasoning engine should answer from now on."""
    provider: str


@app.post("/api/provider/select")
def select_provider(
    body: SelectProviderRequest, _: Principal = Depends(require_presenter_tools)
) -> dict[str, Any]:
    """
    Switch the reasoning engine at runtime.

    This genuinely changes which engine answers -- it does not relabel one as
    another. If watsonx is selected and unreachable, incidents will say so and
    produce no plan; the console will not quietly show IBM branding over a
    different model's output. An audit record always names the engine that
    actually reasoned.

    IBM providers are flagged out of the default order because neither can
    currently answer. Selecting one explicitly is always allowed -- that is the
    point of the switch, and it is how you demonstrate IBM the moment the
    service is active.
    """
    from agent.providers import get_provider, provider_names, reset_provider_cache

    name = body.provider.strip().lower()
    if name not in provider_names() and name not in ("auto", "bob", "claude", "ide"):
        raise HTTPException(
            400,
            detail={
                "error": "unknown_provider",
                "message": f"{name!r} is not a known engine. "
                           f"Valid: {', '.join(provider_names())}, auto.",
            },
        )

    # Persist for this process. Providers read configuration at construction,
    # so the cache is cleared to force a fresh one.
    os.environ["AI_PRIMARY_PROVIDER"] = name
    os.environ["KUBEMEDIC_REASONING_PROVIDER"] = name
    if name in ("ibm-bob", "watsonx", "bob"):
        # Selecting IBM explicitly also lifts the flag, so `auto` would find it
        # too -- otherwise the switch would appear to work and silently not.
        os.environ["KUBEMEDIC_IBM_ENABLED"] = "true"
    reset_provider_cache()

    provider = get_provider(name if name != "auto" else None)
    configured, detail = provider.is_configured()
    log.info("[PROVIDERS] engine switched to %s (configured=%s)", provider.id, configured)
    return {
        "selected": name,
        "active_provider": provider.id,
        "display_name": provider.display_name,
        "configured": configured,
        "detail": detail,
    }


@app.get("/api/provider")
def provider(_: Principal = Depends(require_role("viewer"))) -> dict[str, Any]:
    """
    Which reasoning engine is active, whether each is configured, and how each
    has performed this process.

    Deliberately does NOT probe the network. A health endpoint that calls a
    model API turns a slow third party into a red dashboard and puts it in the
    path of a liveness check. Reachability is discovered by running an
    incident, where a failure is handled rather than merely reported.

    No credential value appears here, only whether one is present.
    """
    from agent.providers import provider_status

    return provider_status()


@app.get("/api/limits")
def limits(_: Principal = Depends(require_role("viewer"))) -> dict[str, Any]:
    """Bounds a reviewer should know about before they start rejecting plans."""
    from agent.providers import configured_provider_name, provider_names

    return {
        "max_revisions": MAX_REVISIONS,
        "reasoning_provider": configured_provider_name(),
        "available_providers": provider_names(),
        "allowed_actions": [
            "rollback_deployment", "restart_deployment", "scale_workload",
        ],
        "state_is_in_process": False,
        "auth": auth.describe(),
        "allowed_namespaces": sorted(allowed_namespaces()),
        "note": (
            "Incidents and their audit trail are persisted to KUBEMEDIC_STATE_DB "
            "and survive a restart. The audit trail is a hash chain; "
            "GET /api/audit/verify checks it."
        ),
    }


def _port_holder(host: str, port: int) -> int | None:
    """
    The pid already listening on this port, if any.

    uvicorn's own message for a taken port is a bare WinError 10048 printed
    *after* "Application startup complete", which reads as though the server
    started and then something unrelated broke. Naming the process turns that
    into an instruction.
    """
    import socket
    import subprocess

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.4)
        if probe.connect_ex((host, port)) != 0:
            return None                      # nothing listening

    try:
        if sys.platform == "win32":
            # Developer-console diagnostic only (naming who holds the port); fixed
            # argv, no shell, no input from a request.
            out = subprocess.run(
                ["netstat", "-ano"],  # noqa: S607
                capture_output=True, text=True, timeout=10
            ).stdout
            for line in out.splitlines():
                if f":{port} " in line and "LISTENING" in line:
                    return int(line.split()[-1])
        else:
            out = subprocess.run(
                ["lsof", "-ti", f"tcp:{port}"],  # noqa: S607
                capture_output=True, text=True, timeout=10,
            ).stdout.strip()
            if out:
                return int(out.splitlines()[0])
    except Exception:
        pass
    return -1                                # busy, holder unknown


_LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")


def insecure_bind(host: str, auth_is_required: bool) -> bool:
    """
    True when this host/auth combination would let anyone on the network
    reach an API that can approve and execute with no credential at all.

    A pure function so the policy is unit-tested without starting a server --
    an earlier version of this check only printed a warning and let the
    process start anyway, found by a security-focused Bob audit session.
    """
    return not auth_is_required and host not in _LOOPBACK_HOSTS


def main() -> None:  # pragma: no cover
    import uvicorn

    host = os.getenv("KUBEMEDIC_API_HOST", "127.0.0.1")
    port = int(os.getenv("KUBEMEDIC_API_PORT", "8100"))

    if auth.auth_required() and not auth.load_tokens():
        print(
            "KUBEMEDIC_REQUIRE_AUTH is set but KUBEMEDIC_API_TOKENS holds no "
            "valid token. Refusing to start.", file=sys.stderr,
        )
        raise SystemExit(1)
    if insecure_bind(host, auth.auth_required()):
        print(
            f"Refusing to bind {host} with authentication OFF. Anyone who can "
            "reach this port would be able to approve and execute. Set "
            "KUBEMEDIC_REQUIRE_AUTH=true, or bind 127.0.0.1 for local use.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    holder = _port_holder(host, port)
    if holder is not None:
        who = f"process {holder}" if holder > 0 else "another process"
        kill = (
            f"Stop-Process -Id {holder} -Force" if sys.platform == "win32"
            else f"kill {holder}"
        )
        other_port = (
            '$env:KUBEMEDIC_API_PORT = "8101"; python -m agent.api'
            if sys.platform == "win32"
            else "KUBEMEDIC_API_PORT=8101 python -m agent.api"
        )
        lines = [
            f"Port {port} is already in use by {who}.",
            "",
            f"  Stop it:         {kill}",
            f"  Or use another:  {other_port}",
            "",
            "If that is an older KubeMedic server, the console it serves is",
            "running the code it was started with, not the code on disk.",
        ]
        print("\n".join(lines), file=sys.stderr)
        raise SystemExit(1)

    print(f"KubeMedic console  ->  http://{host}:{port}/ui/")
    print(f"KubeMedic API      ->  http://{host}:{port}/docs")
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":  # pragma: no cover
    main()
