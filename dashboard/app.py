"""
KubeMedic Dashboard — Verona's lane.

Architecture
------------
This FastAPI application serves the incident console. It sits in front of
Ramana's agent pipeline via a thin API adapter (api_adapter.py). During local
development the adapter falls back to a mock provider so the UI can be built
and tested without the backend running.

The dashboard never calls IBM Bob directly and never executes cluster actions.
It reads incident state and records human decisions; everything else belongs to
the agent pipeline.

Run
---
    cd dashboard
    pip install -r requirements.txt
    uvicorn app:app --reload --port 8080

Environment variables
---------------------
KUBEMEDIC_AGENT_BASE_URL   Base URL of Ramana's agent HTTP API once it exists.
                            Default: "" (empty → use mock provider).
KUBEMEDIC_REVIEWER_NAME    Name recorded as approver/rejector. Default: "reviewer".
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, field_validator

from dashboard.api_adapter import get_adapter

BASE_DIR = Path(__file__).parent
app = FastAPI(title="KubeMedic Dashboard", docs_url="/docs")

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")

REVIEWER = os.getenv("KUBEMEDIC_REVIEWER_NAME", "reviewer")

# ---------------------------------------------------------------------------
# Jinja2 template filters
# ---------------------------------------------------------------------------

_STATE_LABELS: dict[str, str] = {
    "OPEN": "Detected",
    "EVIDENCE_COLLECTED": "Evidence Collected",
    "EVIDENCE_FAILED": "Evidence Failed",
    "ANALYSED": "Analysed",
    "BOB_UNAVAILABLE": "IBM Bob Unavailable",
    "PENDING_APPROVAL": "Awaiting Review",
    "APPROVED": "Approved",
    "REJECTED": "Rejected",
    "FEEDBACK_RECORDED": "Action Not Executed",
    "EXECUTING": "Executing",
    "EXECUTED": "Executed",
    "VERIFIED": "Verified",
    "RESOLVED": "Resolved",
    "VERIFICATION_FAILED": "Verification Failed",
}

_ACTION_LABELS: dict[str, str] = {
    "rollback_deployment": "Roll back deployment",
    "restart_deployment": "Restart deployment",
    "scale_workload": "Scale workload",
}

_SIGNAL_LABELS: dict[str, str] = {
    "rollout_healthy": "Kubernetes Rollout",
    "health_endpoint": "Application Health",
}


def _state_label(state: str) -> str:
    return _STATE_LABELS.get(state, state)


def _action_label(action: str) -> str:
    return _ACTION_LABELS.get(action, action)


def _signal_label(name: str) -> str:
    return _SIGNAL_LABELS.get(name, name)


def _rel_time(ts: str | None) -> str:
    if not ts:
        return "—"
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        diff = int((now - dt).total_seconds())
        if diff < 60:
            return f"{diff}s ago"
        elif diff < 3600:
            return f"{diff // 60}m ago"
        elif diff < 86400:
            return f"{diff // 3600}h ago"
        else:
            return f"{diff // 86400}d ago"
    except Exception:
        return ts


templates.env.filters["state_label"] = _state_label
templates.env.filters["action_label"] = _action_label
templates.env.filters["signal_label"] = _signal_label
templates.env.filters["rel_time"] = _rel_time


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class ApproveBody(BaseModel):
    incident_id: str
    approver: str | None = None  # falls back to REVIEWER env var


class RejectBody(BaseModel):
    incident_id: str
    approver: str | None = None  # falls back to REVIEWER env var
    feedback: str               # required — matches HumanDecision.feedback

    @field_validator("feedback")
    @classmethod
    def feedback_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("feedback must not be empty or whitespace")
        return v.strip()


# ---------------------------------------------------------------------------
# Page routes
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    """Incident list page."""
    adapter = get_adapter()
    incidents = await adapter.list_incidents()
    return templates.TemplateResponse(
        request,
        "index.html",
        {"incidents": incidents, "reviewer": REVIEWER},
    )


@app.get("/incident/{incident_id}", response_class=HTMLResponse)
async def incident_detail(request: Request, incident_id: str) -> HTMLResponse:
    """Full incident detail page — all panels."""
    adapter = get_adapter()
    incident = await adapter.get_incident(incident_id)
    if incident is None:
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "incidents": [],
                "error": f"Incident {incident_id} not found.",
                "reviewer": REVIEWER,
            },
            status_code=404,
        )
    return templates.TemplateResponse(
        request,
        "incident.html",
        {"incident": incident, "reviewer": REVIEWER},
    )


# ---------------------------------------------------------------------------
# API routes — consumed by app.js via fetch()
# ---------------------------------------------------------------------------

@app.get("/api/incidents")
async def api_list_incidents() -> JSONResponse:
    adapter = get_adapter()
    incidents = await adapter.list_incidents()
    return JSONResponse(incidents)


@app.get("/api/incidents/{incident_id}")
async def api_get_incident(incident_id: str) -> JSONResponse:
    adapter = get_adapter()
    incident = await adapter.get_incident(incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found")
    return JSONResponse(incident)


@app.post("/api/approve")
async def api_approve(body: ApproveBody) -> JSONResponse:
    """
    Record a human approval decision.

    Forwards to agent POST /incidents/{id}/decision with:
        { "decision": "approved", "approver": "...", "feedback": null }

    Expected response: updated Incident JSON.
    """
    adapter = get_adapter()
    approver = (body.approver or REVIEWER).strip() or "reviewer"
    result = await adapter.record_decision(
        incident_id=body.incident_id,
        decision="approved",
        approver=approver,
        feedback=None,
    )
    return JSONResponse(result)


@app.post("/api/reject")
async def api_reject(body: RejectBody) -> JSONResponse:
    """
    Record a human rejection with mandatory feedback.

    Forwards to agent POST /incidents/{id}/decision with:
        { "decision": "rejected", "approver": "...", "feedback": "..." }

    The field name is `feedback` — matches HumanDecision.feedback in
    agent/models.py. The server returns 422 on empty feedback (enforced both
    here and by the agent model validator).

    Expected response: updated Incident JSON.
    Illegal transition REJECTED → EXECUTING is enforced by the agent.
    """
    adapter = get_adapter()
    approver = (body.approver or REVIEWER).strip() or "reviewer"
    result = await adapter.record_decision(
        incident_id=body.incident_id,
        decision="rejected",
        approver=approver,
        feedback=body.feedback,  # already trimmed and validated non-blank
    )
    return JSONResponse(result)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/healthz")
async def healthz() -> JSONResponse:
    return JSONResponse({"status": "ok"})
