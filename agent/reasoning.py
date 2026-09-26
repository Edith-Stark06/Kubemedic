"""
Reasoning bridge — calls IBM Bob and validates the structured response.

This is the ONLY module that calls agent/bob.py.  Everything it returns
is a typed model; no raw dicts escape this module.
"""
from __future__ import annotations

import logging
from typing import Any

from agent.providers import (
    ProviderResult as BobResult,
    analyze_with_fallback,
    get_provider,
    unavailable_analysis,
)


def bob_analyze(evidence, tickets, feedback=None):
    """
    Call the active reasoning provider.

    Kept under this name because it is the seam the whole test suite
    patches by string -- with a real evidence/tickets/feedback signature,
    since a mocked Bob has no reason to also accept a runbook. The provider
    behind it is selected by KUBEMEDIC_REASONING_PROVIDER; nothing else in
    the pipeline knows or cares which engine answered.

    Loads the configured runbook itself (see agent/runbook.py) rather than
    taking it as a parameter here, so this seam's signature -- and every
    existing test double for it -- is unaffected by whether the "document
    understanding" feature is in play.
    """
    return analyze_with_fallback(evidence, tickets, feedback, load_runbook())
from agent.models import (
    BobAnalysis,
    EvidenceSnapshot,
    Incident,
    IncidentState,
    TicketReference,
)
from agent.runbook import load_runbook

log = logging.getLogger("kubemedic.reasoning")


def run_analysis(
    incident: Incident,
) -> tuple[Incident, BobAnalysis]:
    """
    Send the incident's evidence + tickets to IBM Bob.
    Validates the response into BobAnalysis.
    Advances incident state.
    Never converts a Bob failure into a successful analysis.

    Returns (updated_incident, analysis).
    """
    if incident.evidence is None:
        raise ValueError("Cannot analyse: incident has no evidence snapshot")

    tickets: list[dict[str, Any]] = [
        t.model_dump(mode="json") for t in incident.tickets
    ]
    evidence_dict: dict[str, Any] = incident.evidence.model_dump(mode="json")

    # Prior rejection reasons travel with the incident. On a first pass this is
    # empty; on a revision it carries every objection the reviewer has raised,
    # so Bob answers them instead of re-proposing what was already refused.
    feedback = list(incident.feedback_history) or None

    result: BobResult = bob_analyze(evidence_dict, tickets, feedback=feedback)

    incident.audit_log.append(result.audit_entry())

    if not result.ok or result.analysis is None:
        # Bob unavailable — do not fabricate
        ua = unavailable_analysis(result.error or "Bob returned no analysis")
        analysis = BobAnalysis.model_validate(ua)
        incident.transition(IncidentState.BOB_UNAVAILABLE)
        incident.analysis = analysis
        log.warning("[REASONING] Bob unavailable: %s", result.error)
        return incident, analysis

    try:
        analysis = BobAnalysis.from_raw(result.analysis)
    except (ValueError, Exception) as exc:
        # Malformed output — treat as unavailable, never as success
        ua = unavailable_analysis(f"Bob output failed validation: {exc}")
        analysis = BobAnalysis.model_validate(ua)
        incident.transition(IncidentState.BOB_UNAVAILABLE)
        incident.analysis = analysis
        log.error("[REASONING] Bob output invalid: %s", exc)
        return incident, analysis

    invented = _invented_ticket_ids(analysis, incident)
    if invented:
        # A model that cites tickets it was never given is inventing evidence.
        # Its conclusions cannot be trusted, so none of them are used.
        ua = unavailable_analysis(
            "analysis cites ticket ids that were not in the evidence: "
            + ", ".join(invented)
        )
        analysis = BobAnalysis.model_validate(ua)
        incident.transition(IncidentState.BOB_UNAVAILABLE)
        incident.analysis = analysis
        incident.audit_log.append(
            {"step": "analysis_rejected", "reason": "fabricated_ticket_ids",
             "ticket_ids": invented}
        )
        log.error("[REASONING] analysis rejected, invented tickets: %s", invented)
        return incident, analysis

    if analysis.is_unavailable:
        incident.transition(IncidentState.BOB_UNAVAILABLE)
    else:
        incident.transition(IncidentState.ANALYSED)

    incident.analysis = analysis
    log.info(
        "[REASONING] analysis ok, action=%s confidence=%s",
        analysis.recommended_action,
        analysis.hypotheses[0].confidence if analysis.hypotheses else "n/a",
    )
    return incident, analysis


def _invented_ticket_ids(analysis: BobAnalysis, incident: Incident) -> list[str]:
    """Ticket ids the analysis names that the incident was never given."""
    if analysis.correlation is None:
        return []
    known = {ticket.ticket_id for ticket in incident.tickets}
    cited = [
        *analysis.correlation.member_tickets,
        *analysis.correlation.excluded_tickets,
    ]
    return sorted({ticket_id for ticket_id in cited if ticket_id not in known})
