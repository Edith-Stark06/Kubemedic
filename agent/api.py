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
from typing import Any, Literal

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field

from agent.adapters import collect_agent_evidence, tickets_to_references
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
from agent.verification import verify

log = logging.getLogger("kubemedic.api")

DEFAULT_NAMESPACE = os.getenv("KUBEMEDIC_NAMESPACE", "opspilot")
DEFAULT_DEPLOYMENT = os.getenv("KUBEMEDIC_DEPLOYMENT", "ticket-booking")
DEFAULT_SERVICE = os.getenv("KUBEMEDIC_SERVICE", "ticket-booking")

app = FastAPI(
    title="KubeMedic Agent API",
    version="1.0.0",
    description=(
        "Evidence, IBM Bob reasoning, human review and verified remediation "
        "for a Kubernetes workload. Nothing mutates the cluster without a "
        "recorded human approval."
    ),
)

# incident_id -> Incident
_INCIDENTS: dict[str, Incident] = {}


# ---------------------------------------------------------------------------
# Cluster access, injected so tests never need a live cluster
# ---------------------------------------------------------------------------

def get_cluster():
    """
    The live cluster client. Overridden in tests via dependency_overrides.

    Imported lazily: the API must be importable, and its contract testable,
    on a machine with no kubeconfig.
    """
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
def cluster_status() -> dict[str, Any]:
    """Live cluster state. Never a canned response — if it cannot be read, it says so."""
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


@app.get("/api/tickets")
def list_tickets(status: str | None = None) -> list[dict[str, Any]]:
    """Real tickets from the store. No fabrication."""
    from mcp_server import tickets as ticket_store

    return [t.model_dump(mode="json") for t in ticket_store.list_tickets(status=status)]


# ---------------------------------------------------------------------------
# Incident lifecycle
# ---------------------------------------------------------------------------

@app.post("/api/incidents", response_model=IncidentSummary, status_code=201)
def create_incident(body: CreateIncidentRequest) -> IncidentSummary:
    """
    Collect evidence, correlate the open tickets, ask IBM Bob, build a plan.

    Stops at PENDING_APPROVAL. It does not execute, and it never advances past
    BOB_UNAVAILABLE — an incident with no analysis gets no plan.
    """
    from mcp_server import tickets as ticket_store

    try:
        evidence = collect_agent_evidence(
            body.namespace, body.deployment, body.service
        )
    except Exception as exc:
        raise HTTPException(
            503, detail=f"Evidence collection failed: {exc}"
        ) from exc

    stored = ticket_store.list_tickets(status=body.ticket_status)
    references = tickets_to_references(stored)

    incident, excluded = correlate(references, evidence)
    log.info(
        "[API] %s correlated %d ticket(s), %d excluded",
        incident.incident_id, len(incident.tickets), len(excluded),
    )

    incident, _ = run_analysis(incident)
    if incident.state != IncidentState.BOB_UNAVAILABLE:
        incident = plan_remediation(incident)

    _INCIDENTS[incident.incident_id] = incident
    return _summary(incident)


@app.get("/api/incidents", response_model=list[IncidentSummary])
def list_incidents() -> list[IncidentSummary]:
    return [_summary(i) for i in _INCIDENTS.values()]


@app.get("/api/incidents/{incident_id}")
def get_incident(incident_id: str) -> dict[str, Any]:
    """
    The whole incident: evidence, correlation, Bob's hypotheses and root cause,
    the plan, the decision, execution, verification and the audit log. This is
    what a reviewer reads before deciding.
    """
    return _require(incident_id).model_dump(mode="json")


@app.post("/api/incidents/{incident_id}/review", response_model=IncidentSummary)
def review_incident(incident_id: str, body: ReviewRequest) -> IncidentSummary:
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

    try:
        human = HumanDecision(
            decision=decision, approver=body.approver, feedback=body.feedback
        )
        incident = record_decision(incident, human)
    except ValueError as exc:
        raise HTTPException(409, detail=str(exc)) from exc

    _INCIDENTS[incident.incident_id] = incident
    return _summary(incident)


@app.post("/api/incidents/{incident_id}/revise", response_model=IncidentSummary)
def revise_incident(incident_id: str) -> IncidentSummary:
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

    _INCIDENTS[incident.incident_id] = incident
    return _summary(incident)


@app.post("/api/incidents/{incident_id}/execute")
def execute_incident(
    incident_id: str, cluster=Depends(get_cluster)
) -> dict[str, Any]:
    """
    Perform the approved action, then verify recovery independently.

    Refused unless the incident is APPROVED — the guard is in the executor, not
    here, so no API path can route around it. Verification re-reads the cluster
    on two independent signals and is never inferred from the execution
    response.
    """
    incident = _require(incident_id)

    try:
        incident, result = execute(incident, cluster)
    except ValueError as exc:
        raise HTTPException(409, detail=str(exc)) from exc

    verification = None
    if result.success:
        incident, verification = verify(incident, cluster)

    record_path = write_record(incident)
    _INCIDENTS[incident.incident_id] = incident

    return {
        "incident": _summary(incident).model_dump(),
        "execution": result.model_dump(mode="json"),
        "verification": verification.model_dump(mode="json") if verification else None,
        "record": str(record_path),
    }


@app.get("/api/incidents/{incident_id}/record")
def get_record(incident_id: str) -> dict[str, Any]:
    """The audit artifact for this incident, built from its current state."""
    incident = _require(incident_id)
    return IncidentRecord.from_incident(incident).model_dump(mode="json")


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
def list_incidents_alias() -> list[IncidentSummary]:
    return list_incidents()


@app.get("/incidents/{incident_id}")
def get_incident_alias(incident_id: str) -> dict[str, Any]:
    return get_incident(incident_id)


@app.post("/incidents/{incident_id}/decision", response_model=IncidentSummary)
def review_incident_alias(incident_id: str, body: ReviewRequest) -> IncidentSummary:
    return review_incident(incident_id, body)


@app.post("/incidents/{incident_id}/execute")
def execute_incident_alias(
    incident_id: str, cluster=Depends(get_cluster)
) -> dict[str, Any]:
    return execute_incident(incident_id, cluster)


@app.post("/incidents/{incident_id}/revise", response_model=IncidentSummary)
def revise_incident_alias(incident_id: str) -> IncidentSummary:
    return revise_incident(incident_id)


@app.get("/api/provider")
def provider() -> dict[str, Any]:
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
def limits() -> dict[str, Any]:
    """Bounds a reviewer should know about before they start rejecting plans."""
    from agent.providers import configured_provider_name, provider_names

    return {
        "max_revisions": MAX_REVISIONS,
        "reasoning_provider": configured_provider_name(),
        "available_providers": provider_names(),
        "allowed_actions": [
            "rollback_deployment", "restart_deployment", "scale_workload",
        ],
        "state_is_in_process": True,
        "note": (
            "Incidents live in memory and are lost on restart. Audit records "
            "in records/ are the durable artifact."
        ),
    }


def main() -> None:  # pragma: no cover
    import uvicorn

    uvicorn.run(
        app,
        host=os.getenv("KUBEMEDIC_API_HOST", "127.0.0.1"),
        port=int(os.getenv("KUBEMEDIC_API_PORT", "8100")),
    )


if __name__ == "__main__":  # pragma: no cover
    main()
