import logging
from typing import Optional

from orchestrator.evidence import (
    inspect_workload,
    inspect_pods,
    inspect_events,
    recent_changes,
    check_application_health,
    collect
)
from mcp_server import tickets

logger = logging.getLogger(__name__)

def get_workload_state(namespace: str = 'opspilot', deployment: str = 'ticket-booking') -> dict:
    try:
        res = inspect_workload(namespace, deployment)
        return res.model_dump()
    except Exception as e:
        return {"error": str(e)}

def get_pods(namespace: str = 'opspilot', deployment: str = 'ticket-booking') -> dict:
    try:
        res = inspect_pods(namespace, deployment)
        return {"pods": [p.model_dump() for p in res]}
    except Exception as e:
        return {"error": str(e)}

def get_events(namespace: str = 'opspilot', deployment: str = 'ticket-booking', limit: int = 15) -> dict:
    try:
        res = inspect_events(namespace, deployment, limit)
        return {"events": [e.model_dump() for e in res]}
    except Exception as e:
        return {"error": str(e)}

def get_recent_changes(namespace: str = 'opspilot', deployment: str = 'ticket-booking') -> dict:
    try:
        res = recent_changes(namespace, deployment)
        return {"revisions": [r.model_dump() for r in res]}
    except Exception as e:
        return {"error": str(e)}

def get_app_health(namespace: str = 'opspilot', service: str = 'ticket-booking') -> dict:
    try:
        res = check_application_health(namespace, service)
        return res.model_dump()
    except Exception as e:
        return {"error": str(e)}

def get_full_snapshot(namespace: str = 'opspilot', deployment: str = 'ticket-booking', service: str = 'ticket-booking') -> dict:
    try:
        res = collect(namespace, deployment, service)
        return res.model_dump()
    except Exception as e:
        return {"error": str(e)}

def list_tickets(status: Optional[str] = None) -> dict:
    res = tickets.list_tickets(status)
    return {"tickets": [t.model_dump() for t in res]}

def get_ticket(ticket_id: str) -> dict:
    res = tickets.get_ticket(ticket_id)
    return res.model_dump() if res else {"error": "Ticket not found"}

def create_ticket(title: str, severity: str, namespace: str, deployment: str, service: str, signals: list) -> dict:
    res = tickets.create_ticket(title, severity, namespace, deployment, service, signals)
    return res.model_dump()

def update_ticket_status(ticket_id: str, status: str, detail: Optional[str] = None) -> dict:
    kwargs = {"status": status}
    if detail:
        kwargs["diagnosis"] = {"detail": detail}
    res = tickets.update_ticket(ticket_id, **kwargs)
    return res.model_dump() if res else {"error": "Ticket not found"}
