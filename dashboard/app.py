import os
import sys
import glob
import json
import time
import uuid
from typing import Optional, Dict, Any, List
from datetime import datetime

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

# Fallback imports in case agent/orchestrator aren't fully wired
try:
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    from agent.bob import BobAgent, Detection
    from agent.record import save_record, RECORDS_DIR
except ImportError:
    BobAgent = None
    RECORDS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'agent', 'records'))


app = FastAPI(title="KubeMedic Dashboard", version="1.0.0")

# In-memory stores
_DETECTIONS: Dict[str, Any] = {}
_WATCHER = {"running": False, "last_check": None}
_TICKETS: Dict[str, Any] = {}
_COUNTER = {"n": 0}

# Many-to-One: Master Incident index.
# Maps master_incident_id -> {"id", "ticket_ids", "correlation_summary",
#                              "services_affected", "severity", "status"}
_MASTER_INCIDENTS: Dict[str, Any] = {}

templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))


class ApproveRejectBody(BaseModel):
    ticket_id: str
    master_incident_id: Optional[str] = None
    approver: Optional[str] = "web-ui"


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html")


@app.get("/api/health")
def api_health():
    return {"status": "ok", "service": "kubemedic-dashboard"}


@app.get("/api/status")
def api_status():
    # Mock live cluster status
    return {
        "workload": {
            "name": "payment-service",
            "image": "us-docker.pkg.dev/proj/apps/payment@sha256:1234",
            "ready_replicas": 2,
            "desired_replicas": 3,
            "rollout_complete": False
        },
        "app_health": {
            "status_code": 503,
            "latency_ms": 1200
        }
    }


@app.post("/api/watcher/start")
def api_watcher_start():
    _WATCHER["running"] = True
    _WATCHER["last_check"] = datetime.now().isoformat()
    return {"status": "started"}


@app.post("/api/watcher/stop")
def api_watcher_stop():
    _WATCHER["running"] = False
    return {"status": "stopped"}


@app.get("/api/watcher/status")
def api_watcher_status():
    return _WATCHER


@app.get("/api/tickets")
def api_tickets():
    """Return tickets grouped by Master Incident when available.

    Each entry in the list is either:
    - A normal ticket dict (no master incident)
    - A *master incident* dict that embeds its correlated sub-tickets
    """
    # Collect all ticket IDs that belong to a master incident
    clustered_ids: set = set()
    result: List[Any] = []

    for mi in _MASTER_INCIDENTS.values():
        clustered_ids.update(mi.get("ticket_ids", []))
        sub_tickets = [_TICKETS[tid] for tid in mi["ticket_ids"] if tid in _TICKETS]
        result.append({
            "type": "master_incident",
            "master_incident_id": mi["id"],
            "correlation_summary": mi["correlation_summary"],
            "services_affected": mi["services_affected"],
            "severity": mi["severity"],
            "status": mi["status"],
            "ticket_ids": mi["ticket_ids"],
            "tickets": sub_tickets,
        })

    # Tickets not belonging to any master incident go in individually
    for t in _TICKETS.values():
        if t["id"] not in clustered_ids:
            result.append({"type": "ticket", **t})

    return result


@app.get("/api/tickets/{ticket_id}")
def api_ticket(ticket_id: str):
    if ticket_id not in _TICKETS:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return _TICKETS[ticket_id]


def _make_ticket(ticket_id: str, severity: str, service_name: str,
                 raw_signal: str, detection_data: Dict[str, Any]) -> Dict[str, Any]:
    """Helper to create a structured ticket dict."""
    return {
        "id": ticket_id,
        "severity": severity,
        "service_name": service_name,
        "status": "open",
        "title": raw_signal,
        "timestamp": datetime.now().isoformat(),
        "raw_signal": raw_signal,
        "detection": detection_data,
    }


@app.post("/api/detect")
def api_detect():
    """Create a cascading-failure storm of multiple related tickets and group
    them under a single Master Incident — simulating a real enterprise incident
    where one root cause triggers alerts across multiple services.

    Tickets created:
      TKT-N   (critical) ticket-booking  — CrashLoopBackOff (root cause)
      TKT-N+1 (high)     payment-service — upstream timeout
      TKT-N+2 (medium)   frontend-gateway — 502 Bad Gateway
    """
    # ---- TKT-1: ticket-booking CrashLoopBackOff (root cause) ----------------
    _COUNTER["n"] += 1
    tkt1_id = f"TKT-{_COUNTER['n']}"

    tkt1_detection = {
        "evidence": {
            "workload": {
                "name": "ticket-booking",
                "image": "ticketbooking:1.1",
                "revision": "3",
                "ready_replicas": 0,
                "desired_replicas": 2,
                "rollout_complete": False,
                "namespace": "opspilot"
            },
            "application_health": {"status_code": 503},
            "pods": [
                {"name": "ticket-booking-7d6b9-xk1", "ready": False,
                 "image": "ticketbooking:1.1", "restarts": 5,
                 "reason": "CrashLoopBackOff"},
                {"name": "ticket-booking-7d6b9-xk2", "ready": False,
                 "image": "ticketbooking:1.1", "restarts": 4,
                 "reason": "CrashLoopBackOff"},
            ]
        },
        "correlation": {
            "is_incident": True,
            "summary": "ticket-booking deployment revision 3 (ticketbooking:1.1) is CrashLoopBackOff. "
                       "Both pods fail readiness. Rollback to revision 2 (ticketbooking:1.0) recommended.",
            "confidence": "high",
            "signals": [
                "Rollout not complete: ready 0/2, updated 2, unavailable 2.",
                "Pod ticket-booking-7d6b9-xk1 on image ticketbooking:1.1 is NotReady "
                "(phase=Running, restarts=5).",
                "Pod ticket-booking-7d6b9-xk2 on image ticketbooking:1.1 is NotReady "
                "(phase=Running, restarts=4).",
                "Readiness probe failing with HTTP 503 (x9) on Pod/ticket-booking-7d6b9-xk1.",
                "Most recent change: revision 3 deployed image ticketbooking:1.1.",
                "Image changed from ticketbooking:1.0 (revision 2) to ticketbooking:1.1 — prime suspect.",
            ]
        },
        "hypotheses": {
            "source": "gemini",
            "root_cause_summary": "Bad image ticketbooking:1.1 introduced in revision 3. "
                                  "HEALTHY env-var set to 'false', causing the health endpoint "
                                  "to always return 503. Both replicas fail readiness probes and "
                                  "enter CrashLoopBackOff.",
            "hypotheses": [
                {
                    "title": "Regressed deployment: ticketbooking:1.1 fails readiness probe",
                    "likelihood": "high",
                    "explanation": "The container starts but the /health endpoint always returns "
                                   "503 because HEALTHY=false is baked into the image. "
                                   "K8s kubelet never marks the pod Ready.",
                    "supporting_evidence": [
                        "5 restarts on both pods", "readiness probe 503 events",
                        "image changed 1.0→1.1 at this revision"
                    ],
                    "recommended_action": "rollback_deployment"
                }
            ],
            "uncertainty": ""
        },
        "plan": {
            "chosen_action": {
                "tool": "rollback_deployment",
                "namespace": "opspilot",
                "deployment": "ticket-booking",
                "parameters": {"to_revision": "2"},
                "description": "Roll back deployment 'ticket-booking' to revision 2 "
                               "(image ticketbooking:1.0), reverting the regressed "
                               "revision 3 (image ticketbooking:1.1)."
            },
            "impact": {
                "risk_level": "low",
                "reversible": True,
                "scope": "Namespace-scoped, single workload: deployment/ticket-booking in opspilot.",
                "blast_radius": "1 Deployment (ticket-booking); up to 2 pod(s) recreated onto "
                                "image ticketbooking:1.0. Other namespaces/workloads unaffected.",
                "user_facing_risk": "Low. Previous revision pods (ticketbooking:1.0) are already "
                                    "serving traffic. Rollback restores full capacity.",
                "expected_effect": "New pods on ticketbooking:1.0 become Ready; rollout completes "
                                   "at 2/2. Cascading failures in payment-service and frontend "
                                   "gateway resolve automatically once upstream is healthy.",
                "reversibility_note": "Fully reversible: revision 3 remains in history."
            },
            "rationale": "Correlation (confidence=high) attributes the degraded rollout to the "
                         "image change ticketbooking:1.0 → ticketbooking:1.1 at revision 3. "
                         "Rolling back to revision 2 restores the last revision that was serving "
                         "successfully. This also unblocks payment-service and the frontend gateway.",
            "requires_approval": True,
            "approval_reason": "Mutating action on a live workload. Human must approve before execution.",
            "verification": {
                "checks": [
                    "Kubernetes rollout completes (rollout status within timeout).",
                    "workload.rollout_complete is True and ready == desired (2/2).",
                    "No pod remains on the suspect image ticketbooking:1.1.",
                    "Application health endpoint returns HTTP 200 (independent signal).",
                ],
                "success_criteria": "DUAL-SIGNAL: K8s rollout healthy AND /health returns 200."
            }
        }
    }

    # ---- TKT-2: payment-service upstream timeout (cascading) ----------------
    _COUNTER["n"] += 1
    tkt2_id = f"TKT-{_COUNTER['n']}"

    tkt2_detection = {
        "evidence": {
            "workload": {
                "name": "payment-service",
                "image": "payment-service:2.4.1",
                "revision": "7",
                "ready_replicas": 2,
                "desired_replicas": 2,
                "rollout_complete": True,
                "namespace": "opspilot"
            },
            "application_health": {"status_code": 504},
            "pods": [
                {"name": "payment-svc-6f8c-ab1", "ready": True,
                 "image": "payment-service:2.4.1", "restarts": 0},
                {"name": "payment-svc-6f8c-ab2", "ready": True,
                 "image": "payment-service:2.4.1", "restarts": 0},
            ]
        },
        "correlation": {
            "is_incident": True,
            "summary": "payment-service returning 504 Gateway Timeout. Its own pods are healthy; "
                       "the upstream dependency ticket-booking is unavailable.",
            "confidence": "high",
            "signals": [
                "Application /health returns 504 — upstream call to ticket-booking timed out.",
                "payment-service pods themselves are Ready and stable (0 restarts).",
                "Correlated with ticket-booking CrashLoopBackOff which started at the same time.",
            ]
        },
        "hypotheses": {
            "source": "gemini",
            "root_cause_summary": "payment-service is healthy; its timeout is a DOWNSTREAM effect "
                                  "of ticket-booking being unavailable. Fixing ticket-booking "
                                  "will resolve this automatically.",
            "hypotheses": [
                {
                    "title": "Upstream dependency unavailable (ticket-booking CrashLoopBackOff)",
                    "likelihood": "high",
                    "explanation": "payment-service calls ticket-booking for booking confirmation. "
                                   "With ticket-booking down (CrashLoopBackOff), every call times "
                                   "out, causing 504s on payment-service's own health probe.",
                    "supporting_evidence": [
                        "ticket-booking started failing at same timestamp",
                        "payment-service pods are healthy with 0 restarts",
                        "504 pattern matches dependency timeout, not local failure"
                    ],
                    "recommended_action": "investigate_further"
                }
            ],
            "uncertainty": "Will auto-resolve when ticket-booking is restored."
        },
        "plan": {
            "chosen_action": {
                "tool": "investigate_further",
                "namespace": "opspilot",
                "deployment": "payment-service",
                "parameters": {},
                "description": "No direct action on payment-service. This is a cascading effect. "
                               "Root fix is rollback of ticket-booking."
            },
            "impact": {
                "risk_level": "low",
                "reversible": True,
                "scope": "No mutation — cascading effect from ticket-booking.",
                "blast_radius": "None — this ticket resolves automatically when root cause is fixed.",
                "user_facing_risk": "payment-service will recover automatically after ticket-booking rollback.",
                "expected_effect": "Once ticket-booking:1.0 is restored, payment-service /health returns 200.",
                "reversibility_note": "No mutation; nothing to revert."
            },
            "rationale": "payment-service pods are healthy. The 504 is a downstream cascade from "
                         "ticket-booking being unavailable. The master plan (rollback ticket-booking) "
                         "resolves this automatically.",
            "requires_approval": False,
            "approval_reason": "No mutating action proposed for this service.",
            "verification": {
                "checks": [
                    "payment-service /health returns 200 after ticket-booking rollback.",
                ],
                "success_criteria": "payment-service health endpoint returns HTTP 200."
            }
        }
    }

    # ---- TKT-3: frontend-gateway 502 (cascading) ----------------------------
    _COUNTER["n"] += 1
    tkt3_id = f"TKT-{_COUNTER['n']}"

    tkt3_detection = {
        "evidence": {
            "workload": {
                "name": "frontend-gateway",
                "image": "frontend-gateway:1.8.0",
                "revision": "5",
                "ready_replicas": 3,
                "desired_replicas": 3,
                "rollout_complete": True,
                "namespace": "opspilot"
            },
            "application_health": {"status_code": 502},
            "pods": [
                {"name": "frontend-gw-9a2d-c1", "ready": True,
                 "image": "frontend-gateway:1.8.0", "restarts": 0},
                {"name": "frontend-gw-9a2d-c2", "ready": True,
                 "image": "frontend-gateway:1.8.0", "restarts": 0},
                {"name": "frontend-gw-9a2d-c3", "ready": True,
                 "image": "frontend-gateway:1.8.0", "restarts": 0},
            ]
        },
        "correlation": {
            "is_incident": True,
            "summary": "frontend-gateway returning 502 Bad Gateway. Gateway pods are healthy. "
                       "Upstream backend services are unavailable.",
            "confidence": "high",
            "signals": [
                "Application /health returns 502 — upstream backends unreachable.",
                "frontend-gateway pods are all Ready (3/3) with 0 restarts.",
                "Correlated with ticket-booking CrashLoopBackOff and payment-service timeouts.",
            ]
        },
        "hypotheses": {
            "source": "gemini",
            "root_cause_summary": "frontend-gateway is proxying requests to ticket-booking and "
                                  "payment-service, both of which are currently degraded. "
                                  "Gateway itself is healthy — this is a pure cascade effect.",
            "hypotheses": [
                {
                    "title": "All upstream backends unavailable (cascade from ticket-booking)",
                    "likelihood": "high",
                    "explanation": "The gateway proxies all booking-related requests to "
                                   "ticket-booking and payment-service. With ticket-booking in "
                                   "CrashLoopBackOff and payment-service timing out, every "
                                   "proxied request returns a 502.",
                    "supporting_evidence": [
                        "All 3 gateway pods are Ready and healthy",
                        "502 started at same timestamp as ticket-booking failure",
                        "No gateway deployment changes in recent history"
                    ],
                    "recommended_action": "investigate_further"
                }
            ],
            "uncertainty": "Will auto-resolve when ticket-booking is restored."
        },
        "plan": {
            "chosen_action": {
                "tool": "investigate_further",
                "namespace": "opspilot",
                "deployment": "frontend-gateway",
                "parameters": {},
                "description": "No direct action on frontend-gateway. This is a cascading effect. "
                               "Root fix is rollback of ticket-booking."
            },
            "impact": {
                "risk_level": "low",
                "reversible": True,
                "scope": "No mutation — pure cascade effect.",
                "blast_radius": "None — this ticket resolves automatically when root cause is fixed.",
                "user_facing_risk": "End users see 502 errors. Will resolve once ticket-booking is rolled back.",
                "expected_effect": "frontend-gateway returns 200 once ticket-booking:1.0 is restored.",
                "reversibility_note": "No mutation; nothing to revert."
            },
            "rationale": "frontend-gateway pods are all healthy. The 502 is a cascade from "
                         "ticket-booking being unavailable. The master plan resolves this.",
            "requires_approval": False,
            "approval_reason": "No mutating action proposed for this service.",
            "verification": {
                "checks": [
                    "frontend-gateway /health returns 200 after ticket-booking rollback.",
                ],
                "success_criteria": "frontend-gateway health endpoint returns HTTP 200."
            }
        }
    }

    # ---- Store all three tickets --------------------------------------------
    tkt1 = _make_ticket(tkt1_id, "critical", "ticket-booking",
                        "ticket-booking pod CrashLoopBackOff", tkt1_detection)
    tkt2 = _make_ticket(tkt2_id, "high", "payment-service",
                        "payment-service upstream timeout (504)", tkt2_detection)
    tkt3 = _make_ticket(tkt3_id, "medium", "frontend-gateway",
                        "frontend-gateway 502 Bad Gateway errors", tkt3_detection)

    _TICKETS[tkt1_id] = tkt1
    _TICKETS[tkt2_id] = tkt2
    _TICKETS[tkt3_id] = tkt3

    # ---- Create Master Incident ---------------------------------------------
    master_id = f"MI-{_COUNTER['n']}"
    correlation_summary = (
        "🔗 IBM Bob has correlated these 3 tickets into 1 Master Incident.\n\n"
        "Root Cause: CrashLoopBackOff in the ticket-booking deployment (revision 3, "
        "image ticketbooking:1.1). The HEALTHY env-var is baked to 'false' in this image, "
        "causing both pods to fail readiness probes repeatedly.\n\n"
        "Cascade Chain:\n"
        "  1. ticket-booking enters CrashLoopBackOff → service becomes unavailable\n"
        "  2. payment-service calls ticket-booking for booking confirmation → upstream "
        "timeout → payment-service /health returns 504\n"
        "  3. frontend-gateway proxies all booking requests to both degraded services → "
        "every proxied request fails → frontend returns 502 Bad Gateway to end users\n\n"
        "Single Fix: Roll back ticket-booking to revision 2 (ticketbooking:1.0). "
        "Both cascading tickets will auto-resolve once the root cause is remediated."
    )

    _MASTER_INCIDENTS[master_id] = {
        "id": master_id,
        "ticket_ids": [tkt1_id, tkt2_id, tkt3_id],
        "correlation_summary": correlation_summary,
        "services_affected": ["ticket-booking", "payment-service", "frontend-gateway"],
        "severity": "critical",   # highest among the three
        "status": "open",
        "root_cause_ticket_id": tkt1_id,
    }

    return {
        "master_incident_id": master_id,
        "ticket_ids": [tkt1_id, tkt2_id, tkt3_id],
        "tickets": [tkt1, tkt2, tkt3],
        "correlation_summary": correlation_summary,
    }


def _decide(body: ApproveRejectBody, approved: bool):
    """Approve or reject a ticket or an entire Master Incident.

    When a master_incident_id is provided, ALL correlated tickets are resolved
    (or rejected) in one action — this is the Many-to-One resolution path.
    The root-cause fix (ticket-booking rollback) is recorded as the execution
    entry; cascading tickets are auto-resolved.
    """
    # Determine which tickets to act on
    ticket_ids_to_act: List[str] = []
    master_incident: Optional[Dict[str, Any]] = None

    if body.master_incident_id and body.master_incident_id in _MASTER_INCIDENTS:
        master_incident = _MASTER_INCIDENTS[body.master_incident_id]
        ticket_ids_to_act = master_incident["ticket_ids"]
    elif body.ticket_id:
        ticket_ids_to_act = [body.ticket_id]

    if not ticket_ids_to_act:
        raise HTTPException(status_code=404, detail="Ticket or master incident not found")

    # Validate all tickets exist
    for tid in ticket_ids_to_act:
        if tid not in _TICKETS:
            raise HTTPException(status_code=404, detail=f"Ticket {tid} not found")

    # Mark each ticket resolved/rejected
    final_status = "resolved" if approved else "rejected"
    for tid in ticket_ids_to_act:
        _TICKETS[tid]["status"] = final_status

    # Update master incident status
    if master_incident:
        master_incident["status"] = final_status

    rec_id = f"INC-{int(time.time())}"
    services_affected = (
        master_incident["services_affected"] if master_incident
        else [_TICKETS[ticket_ids_to_act[0]].get("service_name", "unknown")]
    )
    correlation_summary = (
        master_incident["correlation_summary"] if master_incident else ""
    )

    rec = {
        "incident_id": rec_id,
        "ticket_id": ticket_ids_to_act[0],
        "ticket_ids": ticket_ids_to_act,
        "services_affected": services_affected,
        "correlation_summary": correlation_summary,
        "created_at": datetime.now().isoformat(),
        "outcome": "resolved" if approved else "blocked_awaiting_approval",
        "outcome_detail": (
            f"Root cause fixed (ticket-booking rollback). "
            f"All {len(ticket_ids_to_act)} correlated tickets resolved."
            if approved else "Human rejected plan. No cluster changes made."
        ),
        "approval": {"approver": body.approver, "approved": approved},
        "execution": {
            "executed": approved,
            "tool": "rollback_deployment",
            "deployment": "ticket-booking",
            "detail": (
                "Patched deployment 'ticket-booking' to revision 2 (ticketbooking:1.0). "
                "Controller completed rollout. All cascading services recovered."
                if approved else "APPROVAL GATE: execution blocked — plan rejected by human."
            )
        },
        "verification": {
            "passed": approved,
            "dual_signal_ok": approved,
            "checks": [
                {"name": "rollout_complete", "passed": approved,
                 "detail": "ready 2/2, updated 2, unavailable 0" if approved else "not executed"},
                {"name": "all_replicas_ready", "passed": approved,
                 "detail": "2/2 ready" if approved else "not executed"},
                {"name": "no_suspect_image_pods", "passed": approved,
                 "detail": "no active pods on ticketbooking:1.1" if approved else "not executed"},
                {"name": "app_health_200", "passed": approved,
                 "detail": "/health status 200" if approved else "not executed"},
                {"name": "payment_service_recovered", "passed": approved,
                 "detail": "payment-service /health 200 (upstream restored)" if approved else "not executed"},
                {"name": "frontend_gateway_recovered", "passed": approved,
                 "detail": "frontend-gateway /health 200 (cascade resolved)" if approved else "not executed"},
            ]
        }
    }

    # Save audit record
    os.makedirs(RECORDS_DIR, exist_ok=True)
    with open(os.path.join(RECORDS_DIR, f"{rec_id}.json"), "w") as f:
        json.dump(rec, f, indent=2)

    return {
        "record": rec,
        "resolved_ticket_ids": ticket_ids_to_act,
        "master_incident_id": body.master_incident_id,
    }


@app.post("/api/approve")
def api_approve(body: ApproveRejectBody):
    return _decide(body, approved=True)


@app.post("/api/reject")
def api_reject(body: ApproveRejectBody):
    return _decide(body, approved=False)


@app.get("/api/records")
def api_records():
    out = []
    if os.path.isdir(RECORDS_DIR):
        for fp in sorted(glob.glob(os.path.join(RECORDS_DIR, "INC-*.json")), reverse=True):
            try:
                with open(fp, encoding="utf-8") as f:
                    d = json.load(f)
                    out.append({
                        "incident_id": d.get("incident_id", os.path.basename(fp).replace('.json','')), 
                        "created_at": d.get("created_at", ""),
                        "outcome": d.get("outcome", "unknown")
                    })
            except Exception:
                continue
    return out[:50]


@app.get("/api/records/{incident_id}")
def api_record(incident_id: str):
    if not incident_id.startswith("INC-") or "/" in incident_id or "\\" in incident_id:
        raise HTTPException(status_code=400, detail="invalid id")
    fp = os.path.join(RECORDS_DIR, f"{incident_id}.json")
    if not os.path.isfile(fp):
        raise HTTPException(status_code=404, detail="record not found")
    with open(fp, encoding="utf-8") as f:
        return json.load(f)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
