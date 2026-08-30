"""
Incident correlation — many tickets → one incident.

This is deterministic Python logic, not an LLM call.  Bob receives the
correlated evidence; it does not perform the correlation.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from agent.models import (
    CorrelationResult,
    EvidenceSnapshot,
    Incident,
    IncidentState,
    TicketReference,
)


def _normalise_workload(name: str | None) -> str:
    """Lower-case and strip common Kubernetes prefixes for fuzzy matching."""
    if not name:
        return ""
    name = name.lower().strip()
    for prefix in ("deployment/", "deploy/", "svc/", "service/"):
        if name.startswith(prefix):
            name = name[len(prefix):]
    return name


def correlate(
    tickets: list[TicketReference],
    evidence: EvidenceSnapshot,
    incident_id: str | None = None,
) -> tuple[Incident, list[TicketReference]]:
    """
    Group tickets that share at least two of:
      - same workload as evidence.deployment_name
      - created within the incident window (last 2 hours relative to now)
      - symptom keywords that indicate the same failure class

    Returns (Incident, excluded_tickets).

    The incident is in EVIDENCE_COLLECTED state if evidence was supplied,
    otherwise OPEN.
    """
    inc_id = incident_id or _new_id()
    deployment = _normalise_workload(evidence.deployment_name)
    cutoff = evidence.collected_at

    member: list[TicketReference] = []
    excluded: list[TicketReference] = []
    member_ids: list[str] = []
    excluded_ids: list[str] = []
    basis: list[str] = []

    for t in tickets:
        scores = 0
        reasons: list[str] = []

        # Signal 1: workload name match
        if deployment and _normalise_workload(t.named_workload) == deployment:
            scores += 1
            reasons.append(f"{t.ticket_id} references {evidence.deployment_name}")

        # Signal 2: created within 2-hour window before evidence collection
        if t.created_at and (cutoff - t.created_at).total_seconds() <= 7200:
            scores += 1
            reasons.append(
                f"{t.ticket_id} created within incident window"
                f" ({t.created_at.isoformat()})"
            )

        # Signal 3: symptom keywords overlap
        if _symptom_overlap(t.reported_symptom or ""):
            scores += 1
            reasons.append(f"{t.ticket_id} describes known failure symptoms")

        if scores >= 2:
            member.append(t)
            member_ids.append(t.ticket_id)
            basis.extend(reasons)
        else:
            excluded.append(t)
            excluded_ids.append(t.ticket_id)

    correlation = CorrelationResult(
        master_incident_id=inc_id,
        member_tickets=member_ids,
        excluded_tickets=excluded_ids,
        correlation_basis=list(dict.fromkeys(basis)),  # deduplicate, preserve order
        rationale=(
            f"{len(member_ids)} ticket(s) correlated to deployment "
            f"{evidence.deployment_name}."
        ),
    )

    incident = Incident(
        incident_id=inc_id,
        state=(
            IncidentState.EVIDENCE_COLLECTED if evidence else IncidentState.OPEN
        ),
        tickets=member,
        evidence=evidence,
        correlation=correlation,
    )
    incident.audit_log.append(
        {
            "step": "correlation",
            "member_tickets": member_ids,
            "excluded_tickets": excluded_ids,
            "basis": correlation.correlation_basis,
        }
    )

    return incident, excluded


_SYMPTOM_KEYWORDS = re.compile(
    r"crash|restart|timeout|unavailable|5[0-9][0-9]|error|fail|down|"
    r"not.?ready|pending|backoff|oom|evict|probe|unhealthy",
    re.IGNORECASE,
)


def _symptom_overlap(text: str) -> bool:
    return bool(_SYMPTOM_KEYWORDS.search(text))


_counter = 0


def _new_id() -> str:
    global _counter
    _counter += 1
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    return f"INC-{ts}-{_counter:03d}"
