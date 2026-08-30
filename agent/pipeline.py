"""
Pipeline — end-to-end incident lifecycle runner.

This module wires together all agent stages into one callable flow.
It is the entry point for the backend; the dashboard calls each stage
individually through the API layer (not yet implemented) or calls
run_full_pipeline() for a synchronous end-to-end run.

Stage sequence:
  1. correlate()         tickets + evidence → Incident
  2. run_analysis()      Incident → BobAnalysis (or BOB_UNAVAILABLE)
  3. plan_remediation()  BobAnalysis → RemediationPlan (or None)
  4. record_decision()   HumanDecision → APPROVED / FEEDBACK_RECORDED
  5. execute()           APPROVED → EXECUTED
  6. verify()            EXECUTED → RESOLVED / VERIFICATION_FAILED
  7. write_record()      any terminal state → records/
"""
from __future__ import annotations

import logging
from typing import Any

from agent.audit import record_decision, write_record
from agent.correlation import correlate
from agent.executor import KubernetesClient, execute
from agent.models import (
    MAX_REVISIONS,
    BobAnalysis,
    EvidenceSnapshot,
    HumanDecision,
    Incident,
    IncidentState,
    RemediationPlan,
    TicketReference,
)
from agent.reasoning import run_analysis
from agent.verification import EvidenceReader, verify

log = logging.getLogger("kubemedic.pipeline")


# ---------------------------------------------------------------------------
# Stage 3 helper — plan is derived from analysis, no extra module needed
# ---------------------------------------------------------------------------

def plan_remediation(incident: Incident) -> Incident:
    """
    Build a RemediationPlan from the validated BobAnalysis.
    If the analysis has no action (null recommendation or unavailable),
    the incident stays in its current state with plan=None.
    """
    analysis = incident.analysis
    if analysis is None or analysis.is_unavailable:
        log.info(
            "[PIPELINE] %s: no plan (analysis unavailable or null action)",
            incident.incident_id,
        )
        return incident

    if analysis.recommended_action is None:
        log.info(
            "[PIPELINE] %s: null recommendation — no plan built",
            incident.incident_id,
        )
        return incident

    try:
        plan = RemediationPlan.from_analysis(analysis)
    except ValueError as exc:
        log.error("[PIPELINE] Cannot build plan: %s", exc)
        return incident

    incident.plan = plan
    incident.transition(IncidentState.PENDING_APPROVAL)
    incident.audit_log.append(
        {
            "step": "plan",
            "action": plan.action.value,
            "target": plan.target,
        }
    )
    return incident


# ---------------------------------------------------------------------------
# Revision — the loop back from a rejection
# ---------------------------------------------------------------------------

def request_revision(incident: Incident) -> Incident:
    """
    Ask Bob for a revised plan after a human rejected the previous one.

    The reviewer's reasons are already on incident.feedback_history (put there
    by record_decision); run_analysis reads them back into the prompt. This is
    the step that turns a stored rejection reason into a different plan.

    Preconditions:
      - incident.state is REJECTED or FEEDBACK_RECORDED
      - at least one feedback entry exists
      - revision_count < MAX_REVISIONS

    The incident lands back at PENDING_APPROVAL for a second human review, or
    at BOB_UNAVAILABLE if Bob could not be reached. It never lands anywhere
    that can execute: Incident.transition() refuses
    FEEDBACK_RECORDED -> EXECUTING outright, so no revision path can reach the
    cluster without passing a fresh approval.
    """
    revisable = {IncidentState.REJECTED, IncidentState.FEEDBACK_RECORDED}
    if incident.state not in revisable:
        raise ValueError(
            f"Cannot revise: incident is in state {incident.state}. "
            f"Expected one of {[s.value for s in revisable]}."
        )
    if not incident.feedback_history:
        raise ValueError(
            "Cannot revise: no human feedback recorded. A revision exists to "
            "answer an objection; without one there is nothing to answer."
        )
    if incident.revision_count >= MAX_REVISIONS:
        raise ValueError(
            f"Revision limit reached ({MAX_REVISIONS}). This incident needs a "
            "human to act directly rather than another proposal."
        )

    incident.revision_count += 1
    incident.audit_log.append(
        {
            "step": "revision_requested",
            "revision": incident.revision_count,
            "feedback_so_far": list(incident.feedback_history),
        }
    )
    log.info(
        "[PIPELINE] %s: revision %d requested with %d feedback item(s)",
        incident.incident_id, incident.revision_count, len(incident.feedback_history),
    )

    # Clear the previous proposal so a stale plan cannot be approved by
    # mistake if Bob comes back unavailable.
    incident.plan = None
    incident.human_decision = None

    incident, _ = run_analysis(incident)
    if incident.state == IncidentState.BOB_UNAVAILABLE:
        log.warning(
            "[PIPELINE] %s: revision %d stopped - Bob unavailable",
            incident.incident_id, incident.revision_count,
        )
        return incident

    return plan_remediation(incident)


# ---------------------------------------------------------------------------
# Full synchronous pipeline (used for testing and demos)
# ---------------------------------------------------------------------------

def run_full_pipeline(
    tickets: list[TicketReference],
    evidence: EvidenceSnapshot,
    human_decision: HumanDecision,
    kubernetes: KubernetesClient,
    reader: EvidenceReader,
    incident_id: str | None = None,
    persist: bool = True,
) -> Incident:
    """
    Run every stage in sequence.  Returns the incident in its terminal state.

    The human_decision is applied after analysis; if Bob is unavailable or
    the recommendation is null, the pipeline stops before the approval gate.
    """
    # Stage 1 — Correlate
    incident, excluded = correlate(tickets, evidence, incident_id=incident_id)
    log.info(
        "[PIPELINE] %s: correlated %d tickets (%d excluded)",
        incident.incident_id, len(incident.tickets), len(excluded),
    )

    # Stage 2 — Bob analysis
    incident, analysis = run_analysis(incident)
    if incident.state == IncidentState.BOB_UNAVAILABLE:
        log.warning("[PIPELINE] %s: stopping — Bob unavailable", incident.incident_id)
        if persist:
            write_record(incident)
        return incident

    # Stage 3 — Plan
    incident = plan_remediation(incident)
    if incident.plan is None:
        log.info(
            "[PIPELINE] %s: stopping — no remediation plan", incident.incident_id
        )
        if persist:
            write_record(incident)
        return incident

    # Stage 4 — Human decision
    incident = record_decision(incident, human_decision)
    if incident.state in (IncidentState.REJECTED, IncidentState.FEEDBACK_RECORDED):
        log.info("[PIPELINE] %s: rejected — stopping", incident.incident_id)
        if persist:
            write_record(incident)
        return incident

    # Stage 5 — Execute
    incident, exec_result = execute(incident, kubernetes)
    if not exec_result.success:
        log.error("[PIPELINE] %s: execution failed", incident.incident_id)
        if persist:
            write_record(incident)
        return incident

    # Stage 6 — Verify
    incident, verification = verify(incident, reader)

    # Stage 7 — Persist
    if persist:
        write_record(incident)

    log.info(
        "[PIPELINE] %s: complete — state=%s verification=%s",
        incident.incident_id, incident.state, verification.outcome,
    )
    return incident
