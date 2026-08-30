"""
KubeMedic agent data contracts.

Field names in BobAnalysis / CorrelationResult are frozen — they mirror
.bob/skills/incident-correlation/references/evidence-schema.md exactly.
Change here and in the schema doc in the same commit.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# Allowlisted actions — the complete, closed set.  Executor rejects anything
# not in this enum.  Bob output that names something else is invalid input.
# ---------------------------------------------------------------------------

class AllowedAction(str, Enum):
    rollback_deployment = "rollback_deployment"
    restart_deployment  = "restart_deployment"
    scale_workload      = "scale_workload"


# ---------------------------------------------------------------------------
# Ticket reference
# ---------------------------------------------------------------------------

class TicketReference(BaseModel):
    ticket_id: str
    title: str | None = None
    reported_symptom: str | None = None
    named_workload: str | None = None
    created_at: datetime | None = None
    severity: str | None = None


# ---------------------------------------------------------------------------
# Evidence snapshot — what the MCP server collected
# ---------------------------------------------------------------------------

class EvidenceSnapshot(BaseModel):
    collected_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    deployment_name: str
    namespace: str = "default"
    pod_states: list[dict[str, Any]] = Field(default_factory=list)
    events: list[dict[str, Any]] = Field(default_factory=list)
    rollout_history: list[dict[str, Any]] = Field(default_factory=list)
    application_health: dict[str, Any] | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Correlation result — many tickets → one incident
# ---------------------------------------------------------------------------

class CorrelationResult(BaseModel):
    """Output of the correlation step.  Maps N open tickets → 1 master incident."""
    master_incident_id: str
    member_tickets: list[str]          # ticket IDs that belong to this incident
    excluded_tickets: list[str] = Field(default_factory=list)
    correlation_basis: list[str] = Field(default_factory=list)
    rationale: str = ""


# ---------------------------------------------------------------------------
# Bob analysis — exactly mirrors evidence-schema.md success shape
# ---------------------------------------------------------------------------

class Hypothesis(BaseModel):
    rank: int
    statement: str
    confidence: Literal["high", "medium", "low"]
    confidence_reason: str
    supporting_evidence: list[str] = Field(default_factory=list)
    contradicting_evidence: list[str] = Field(default_factory=list)
    cheapest_next_check: str = ""


class RootCause(BaseModel):
    statement: str
    confidence: Literal["high", "medium", "low"]
    is_inference: bool = True


class TimelineEvent(BaseModel):
    t: str
    event: str
    source: str


class BobAnalysis(BaseModel):
    """Parsed, validated output of one IBM Bob reasoning call."""
    schema_version: str = "1.0"
    # Provider id, or "unavailable". Widened from a Bob-only literal when
    # the reasoning layer became pluggable -- see agent/providers/. The
    # matching change is in
    # .bob/skills/incident-correlation/references/evidence-schema.md.
    analysis_source: Literal[
        "ibm-bob", "watsonx", "anthropic", "gemini",
        # Reasoning done by the agentic IDE hosting the workspace. Stamped
        # honestly: the Bob IDE reports ibm-bob because it genuinely is Bob.
        "claude-code", "antigravity", "host",
        # Scripted fixture reasoning used by scripts/dry_run.py when no engine
        # is reachable. Deliberately its own value: a record reading "fixture"
        # cannot be mistaken for a model having reasoned, and a judge reading
        # one knows exactly what they are looking at.
        "fixture",
        "unavailable",
    ] = "ibm-bob"
    status: str | None = None                  # "evidence_unavailable" or absent

    # Correlation block (present on success)
    correlation: CorrelationResult | None = None
    timeline: list[TimelineEvent] = Field(default_factory=list)
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    root_cause: RootCause | None = None
    dual_signal_note: str | None = None

    # Recommendation
    recommended_action: AllowedAction | None = None
    action_target: str | None = None
    action_parameters: dict[str, Any] = Field(default_factory=dict)
    reason: str = ""
    risk_explanation: str = ""
    requires_human_approval: bool = True
    notes_for_reviewer: str | None = None

    # Evidence-unavailable shape extras
    missing_signals: list[str] = Field(default_factory=list)
    partial_evidence: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_action_target(self) -> "BobAnalysis":
        if self.recommended_action is not None and not self.action_target:
            raise ValueError(
                "action_target is required when recommended_action is set"
            )
        return self

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> "BobAnalysis":
        """
        Parse a raw dict from Bob.  Raises ValueError on malformed input.
        Rejects any recommended_action not in AllowedAction.
        """
        # Normalise recommended_action early so the enum validator fires
        action = raw.get("recommended_action")
        if action is not None:
            valid = {a.value for a in AllowedAction}
            # A model may return an object here rather than a string -- a live
            # Gemini call did exactly that, and `action not in valid` raised
            # TypeError: unhashable type instead of a refusal. Anything that is
            # not a plain string is simply not in the allowlist.
            if not isinstance(action, str):
                raise ValueError(
                    f"recommended_action must be one of {sorted(valid)}, "
                    f"got {type(action).__name__}: {action!r}"
                )
            if action not in valid:
                raise ValueError(
                    f"recommended_action '{action}' is not in the allowlist "
                    f"{sorted(valid)}"
                )
        return cls.model_validate(raw)

    @property
    def is_unavailable(self) -> bool:
        return (
            self.analysis_source == "unavailable"
            or self.status in ("evidence_unavailable", "bob_unavailable")
        )


# ---------------------------------------------------------------------------
# Remediation plan — structured, never a shell string
# ---------------------------------------------------------------------------

class RemediationPlan(BaseModel):
    action: AllowedAction
    target: str
    action_parameters: dict[str, Any] = Field(default_factory=dict)
    blast_radius: str = ""
    risk: Literal["low", "medium", "high"] = "medium"
    reversible: bool = True
    expected_effect: str = ""
    verification_plan: list[str] = Field(default_factory=list)
    reason: str = ""
    risk_explanation: str = ""
    notes_for_reviewer: str | None = None

    @classmethod
    def from_analysis(cls, analysis: BobAnalysis) -> "RemediationPlan":
        """Build a plan from a validated BobAnalysis.  Raises if no action."""
        if analysis.recommended_action is None:
            raise ValueError(
                "Cannot build RemediationPlan: recommended_action is null"
            )
        if not analysis.action_target:
            raise ValueError(
                "Cannot build RemediationPlan: action_target is empty"
            )
        return cls(
            action=analysis.recommended_action,
            target=analysis.action_target,
            action_parameters=analysis.action_parameters,
            reason=analysis.reason,
            risk_explanation=analysis.risk_explanation,
            notes_for_reviewer=analysis.notes_for_reviewer,
        )


# ---------------------------------------------------------------------------
# Human decision
# ---------------------------------------------------------------------------

class HumanDecision(BaseModel):
    decision: Literal["approved", "rejected"]
    approver: str
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    feedback: str | None = None

    @model_validator(mode="after")
    def _require_feedback_on_rejection(self) -> "HumanDecision":
        if self.decision == "rejected" and not (self.feedback or "").strip():
            raise ValueError(
                "feedback is required when decision is 'rejected'"
            )
        return self


# ---------------------------------------------------------------------------
# Execution result
# ---------------------------------------------------------------------------

class ExecutionResult(BaseModel):
    action: AllowedAction
    target: str
    executed_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    success: bool
    message: str = ""
    raw_response: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Verification result
# ---------------------------------------------------------------------------

class VerificationSignal(BaseModel):
    name: str                          # e.g. "rollout_healthy", "health_endpoint"
    passed: bool
    detail: str = ""


class VerificationResult(BaseModel):
    outcome: Literal["PASS", "FAIL", "INCONCLUSIVE"]
    signals: list[VerificationSignal] = Field(default_factory=list)
    checked_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    detail: str = ""

    @classmethod
    def inconclusive(cls, reason: str) -> "VerificationResult":
        return cls(outcome="INCONCLUSIVE", detail=reason)


# ---------------------------------------------------------------------------
# Incident — top-level container that flows through the pipeline
# ---------------------------------------------------------------------------

class IncidentState(str, Enum):
    OPEN                    = "OPEN"
    EVIDENCE_COLLECTED      = "EVIDENCE_COLLECTED"
    EVIDENCE_FAILED         = "EVIDENCE_FAILED"
    ANALYSED                = "ANALYSED"
    BOB_UNAVAILABLE         = "BOB_UNAVAILABLE"
    PENDING_APPROVAL        = "PENDING_APPROVAL"
    APPROVED                = "APPROVED"
    REJECTED                = "REJECTED"
    FEEDBACK_RECORDED       = "FEEDBACK_RECORDED"
    EXECUTING               = "EXECUTING"
    EXECUTED                = "EXECUTED"
    VERIFIED                = "VERIFIED"
    RESOLVED                = "RESOLVED"
    VERIFICATION_FAILED     = "VERIFICATION_FAILED"


# A rejected plan may be revised this many times before the incident is handed
# to a human outright. Without a ceiling, reject -> revise -> reject is an
# unbounded loop that burns Bob calls and never terminates.
MAX_REVISIONS = 3


# Transitions that are explicitly illegal (executor raises on these)
_ILLEGAL_TRANSITIONS: set[tuple[IncidentState, IncidentState]] = {
    (IncidentState.REJECTED, IncidentState.EXECUTING),
    (IncidentState.FEEDBACK_RECORDED, IncidentState.EXECUTING),
}


class Incident(BaseModel):
    incident_id: str
    state: IncidentState = IncidentState.OPEN
    tickets: list[TicketReference] = Field(default_factory=list)
    evidence: EvidenceSnapshot | None = None
    correlation: CorrelationResult | None = None   # set by correlate()
    analysis: BobAnalysis | None = None
    plan: RemediationPlan | None = None
    human_decision: HumanDecision | None = None
    execution: ExecutionResult | None = None
    verification: VerificationResult | None = None
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    audit_log: list[dict[str, Any]] = Field(default_factory=list)

    # Every rejection reason this incident has collected, oldest first. Read
    # back into Bob's prompt on re-analysis so a revised plan knows what the
    # reviewer objected to. Storing it without feeding it back was the gap.
    feedback_history: list[str] = Field(default_factory=list)
    # How many times Bob has been asked to revise. Capped by MAX_REVISIONS so
    # a reject/revise cycle cannot spin indefinitely.
    revision_count: int = 0

    def transition(self, new_state: IncidentState) -> None:
        """Advance state, refusing illegal transitions."""
        if (self.state, new_state) in _ILLEGAL_TRANSITIONS:
            raise ValueError(
                f"Illegal state transition: {self.state} → {new_state}"
            )
        self.state = new_state
        self.updated_at = datetime.now(timezone.utc)

    def require_approval(self) -> None:
        """Raise if the incident is not in APPROVED state."""
        if self.state != IncidentState.APPROVED:
            raise ValueError(
                f"Execution requires APPROVED state; current state is {self.state}"
            )


# ---------------------------------------------------------------------------
# Incident record — the immutable audit artifact written to records/
# ---------------------------------------------------------------------------

class IncidentRecord(BaseModel):
    incident_id: str
    final_state: IncidentState
    tickets: list[str]                      # ticket IDs
    correlation: CorrelationResult | None = None
    analysis_source: str
    bob_analysis: dict[str, Any] | None = None  # full analysis snapshot for audit
    root_cause: dict[str, Any] | None = None
    recommended_action: str | None
    human_decision: str | None              # "approved" / "rejected" / None
    rejection_feedback: str | None = None
    feedback_history: list[str] = Field(default_factory=list)
    revision_count: int = 0
    executed: bool = False
    verification_outcome: str | None = None
    created_at: datetime
    resolved_at: datetime | None = None
    audit_log: list[dict[str, Any]] = Field(default_factory=list)

    @classmethod
    def from_incident(cls, inc: Incident) -> "IncidentRecord":
        # Snapshot the full analysis for the audit record
        bob_analysis_snapshot: dict[str, Any] | None = None
        root_cause_snapshot: dict[str, Any] | None = None
        if inc.analysis and not inc.analysis.is_unavailable:
            bob_analysis_snapshot = inc.analysis.model_dump(mode="json")
            if inc.analysis.root_cause:
                root_cause_snapshot = inc.analysis.root_cause.model_dump(mode="json")

        terminal_states = {
            IncidentState.RESOLVED,
            IncidentState.REJECTED,
            IncidentState.FEEDBACK_RECORDED,
            IncidentState.VERIFICATION_FAILED,
        }

        return cls(
            incident_id=inc.incident_id,
            final_state=inc.state,
            tickets=[t.ticket_id for t in inc.tickets],
            correlation=inc.correlation,
            analysis_source=(
                inc.analysis.analysis_source if inc.analysis else "none"
            ),
            bob_analysis=bob_analysis_snapshot,
            root_cause=root_cause_snapshot,
            recommended_action=(
                inc.analysis.recommended_action.value
                if inc.analysis and inc.analysis.recommended_action
                else None
            ),
            human_decision=(
                inc.human_decision.decision if inc.human_decision else None
            ),
            rejection_feedback=(
                inc.human_decision.feedback
                if inc.human_decision and inc.human_decision.decision == "rejected"
                else None
            ),
            feedback_history=list(inc.feedback_history),
            revision_count=inc.revision_count,
            executed=inc.execution is not None and inc.execution.success,
            verification_outcome=(
                inc.verification.outcome if inc.verification else None
            ),
            created_at=inc.created_at,
            resolved_at=(
                inc.updated_at if inc.state in terminal_states else None
            ),
            audit_log=inc.audit_log,
        )
