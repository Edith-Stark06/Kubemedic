"""
Adapters between the MCP evidence layer and the agent's contracts.

Two type systems meet here, and until this module existed nothing joined them:

  mcp_server.evidence.EvidenceSnapshot   namespace, deployment, service,
                                         workload, pods, events,
                                         recent_changes, application_health
  agent.models.EvidenceSnapshot          deployment_name, namespace,
                                         pod_states, events, rollout_history,
                                         application_health, raw

  mcp_server.models.Ticket               id, title, signals[], deployment,
                                         created_at (str), ...
  agent.models.TicketReference           ticket_id, title, reported_symptom,
                                         named_workload, created_at (datetime)

THE CORRELATION HAZARD
----------------------
agent/correlation.py groups tickets on three signals and needs 2 of 3:

  1. named_workload matching the evidence's deployment
  2. created_at inside the two-hour window before evidence collection
  3. symptom keywords in reported_symptom

named_workload and created_at are both Optional on TicketReference and default
to None. A careless adapter that drops either leaves a ticket scoring at most
1 of 3 — and it is silently excluded from its own incident, with no error
anywhere. That is why ticket_to_reference() parses created_at defensively and
why the tests assert both fields survive.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from agent.models import EvidenceSnapshot as AgentEvidence
from agent.models import TicketReference
from mcp_server.evidence import EvidenceSnapshot as ClusterEvidence
from mcp_server.models import Ticket

log = logging.getLogger("kubemedic.adapters")


def parse_timestamp(value: Any) -> datetime | None:
    """
    Parse a stored timestamp into an aware UTC datetime.

    Ticket rows store ISO strings; the cluster returns datetimes. A naive
    datetime is assumed UTC — correlation compares against an aware
    collected_at, and mixing the two raises TypeError mid-incident.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()
        if not text:
            return None
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            log.warning(
                "[ADAPT] unparseable timestamp %r — the ticket will lose its "
                "correlation time signal",
                value,
            )
            return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def ticket_to_reference(ticket: Ticket) -> TicketReference:
    """
    Convert a stored Ticket into the reference the agent correlates on.

    `signals` (a list) collapses into `reported_symptom` (one string) joined by
    '; '. The title is prepended because it usually carries the clearest
    symptom wording, and the keyword regex reads the whole string.
    """
    parts: list[str] = []
    if ticket.title:
        parts.append(ticket.title)
    parts.extend(s for s in (ticket.signals or []) if s)

    return TicketReference(
        ticket_id=ticket.id,
        title=ticket.title,
        reported_symptom="; ".join(parts) or None,
        named_workload=ticket.deployment,          # signal 1 — must survive
        created_at=parse_timestamp(ticket.created_at),  # signal 2 — must survive
        severity=ticket.severity.value
        if hasattr(ticket.severity, "value")
        else ticket.severity,
    )


def tickets_to_references(tickets: list[Ticket]) -> list[TicketReference]:
    return [ticket_to_reference(t) for t in tickets]


def cluster_evidence_to_agent(snapshot: ClusterEvidence) -> AgentEvidence:
    """
    Convert a live cluster snapshot into the agent's evidence contract.

    `raw` carries the untouched cluster bundle. Bob sees the whole dict, so
    nothing observed is silently dropped on the way to reasoning — a field the
    agent's own model has no slot for is still evidence.
    """
    return AgentEvidence(
        collected_at=datetime.now(timezone.utc),
        deployment_name=snapshot.deployment,
        namespace=snapshot.namespace,
        pod_states=[p.model_dump(mode="json") for p in snapshot.pods],
        events=[e.model_dump(mode="json") for e in snapshot.events],
        rollout_history=[r.model_dump(mode="json") for r in snapshot.recent_changes],
        application_health=snapshot.application_health.model_dump(mode="json"),
        raw=snapshot.model_dump(mode="json"),
    )


def collect_agent_evidence(
    namespace: str = "opspilot",
    deployment: str = "ticket-booking",
    service: str = "ticket-booking",
) -> AgentEvidence:
    """Read the live cluster and return evidence in the agent's contract."""
    from mcp_server.evidence import collect

    return cluster_evidence_to_agent(collect(namespace, deployment, service))


def previous_revision(evidence: AgentEvidence) -> int | None:
    """
    The revision to roll back to: the highest-numbered non-current revision in
    the rollout history. Returns None when there is nothing to roll back to.
    """
    candidates: list[int] = []
    for entry in evidence.rollout_history:
        if entry.get("is_current"):
            continue
        revision = entry.get("revision")
        if revision is not None and str(revision).isdigit():
            candidates.append(int(revision))
    return max(candidates) if candidates else None
