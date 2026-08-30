"""
Reasoning bridge — calls IBM Bob and validates the structured response.

This is the ONLY module that calls agent/bob.py.  Everything it returns
is a typed model; no raw dicts escape this module.
"""
from __future__ import annotations

import logging
from typing import Any

from agent.bob import BobResult, analyze as bob_analyze, unavailable_analysis
from agent.models import (
    BobAnalysis,
    EvidenceSnapshot,
    Incident,
    IncidentState,
    TicketReference,
)

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

    result: BobResult = bob_analyze(evidence_dict, tickets)

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
