"""
Audit — persists incident records and the rejection path.

Two responsibilities:
  1. record_decision()  — apply a human decision to an incident; enforce
                          server-side validation; record rejection feedback.
  2. write_record()     — persist the final IncidentRecord to records/.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from agent.models import (
    HumanDecision,
    Incident,
    IncidentRecord,
    IncidentState,
)

log = logging.getLogger("kubemedic.audit")

RECORDS_DIR = Path("records")


# ---------------------------------------------------------------------------
# Human decision gate
# ---------------------------------------------------------------------------

def record_decision(incident: Incident, decision: HumanDecision) -> Incident:
    """
    Apply a human decision (approved / rejected) to an incident.

    Validation (server-side, not JS):
      - Incident must be in PENDING_APPROVAL or ANALYSED state.
      - decision="rejected" requires non-empty feedback (enforced by
        HumanDecision model, so a bad input raises ValueError before here).
      - REJECTED → EXECUTING is blocked by Incident.transition().

    On rejection:
      - state → REJECTED
      - feedback persisted in human_decision
      - audit log entry written
      - state → FEEDBACK_RECORDED
      - execution does NOT happen

    On approval:
      - state → APPROVED
    """
    allowed_states = {IncidentState.ANALYSED, IncidentState.PENDING_APPROVAL}
    if incident.state not in allowed_states:
        raise ValueError(
            f"Cannot record decision: incident is in state {incident.state}. "
            f"Expected one of {[s.value for s in allowed_states]}."
        )

    # HumanDecision model already validated feedback-on-reject
    incident.human_decision = decision
    incident.audit_log.append(
        {
            "step": "human_decision",
            "decision": decision.decision,
            "approver": decision.approver,
            "timestamp": decision.timestamp.isoformat(),
            "feedback": decision.feedback,
        }
    )

    if decision.decision == "rejected":
        incident.transition(IncidentState.REJECTED)
        # The reason joins the incident's feedback history, which
        # reasoning.run_analysis() reads back into Bob's prompt on the next
        # revision. Storing it only in the audit log -- as this did before --
        # meant the reviewer's knowledge was recorded and never used.
        if decision.feedback:
            incident.feedback_history.append(decision.feedback)
        incident.audit_log.append(
            {
                "step": "rejection_recorded",
                "reason": decision.feedback,
                "executed": False,
                "feedback_count": len(incident.feedback_history),
            }
        )
        incident.transition(IncidentState.FEEDBACK_RECORDED)
        log.info(
            "[AUDIT] Incident %s REJECTED by %s: %s",
            incident.incident_id,
            decision.approver,
            decision.feedback,
        )
    else:
        incident.transition(IncidentState.APPROVED)
        log.info(
            "[AUDIT] Incident %s APPROVED by %s",
            incident.incident_id,
            decision.approver,
        )

    incident.updated_at = datetime.now(timezone.utc)
    return incident


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def write_record(incident: Incident, records_dir: Path = RECORDS_DIR) -> Path:
    """
    Persist an IncidentRecord to records/<incident_id>.json.
    Creates the directory if absent.  Never overwrites — appends a suffix
    if the file exists (for reruns in tests).
    """
    records_dir.mkdir(parents=True, exist_ok=True)
    record = IncidentRecord.from_incident(incident)
    path = records_dir / f"{incident.incident_id}.json"
    if path.exists():
        ts = datetime.now(timezone.utc).strftime("%H%M%S")
        path = records_dir / f"{incident.incident_id}-{ts}.json"
    path.write_text(
        record.model_dump_json(indent=2),
        encoding="utf-8",
    )
    log.info("[AUDIT] Record written to %s", path)
    return path
