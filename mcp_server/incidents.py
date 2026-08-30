"""
Read-only incident history for the MCP evidence surface.

Bob reasons better when it can see what has already been decided: which
tickets were previously correlated, what was proposed, what a human rejected
and why. That context lives in the audit records the agent writes.

DELIBERATELY READ-ONLY, AND DELIBERATELY VIA THE FILESYSTEM
-----------------------------------------------------------
The MCP server and the agent API are separate processes, so this reads the
durable artifact (records/*.json) rather than the API's in-memory incident
store. That is a feature, not a workaround: it means the tool surface cannot
reach into live incident state, and there is no path from an MCP call to a
state transition.

There is no create_incident, approve_plan or execute_plan here, and there never
will be. Mutation lives in agent/executor.py behind the human approval gate.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

RECORDS_DIR = Path(os.getenv("KUBEMEDIC_RECORDS_DIR", "records"))

# A summary, not the whole record: the audit log of a long incident is large
# and Bob does not need it to reason about what happened.
SUMMARY_FIELDS = (
    "incident_id", "final_state", "tickets", "analysis_source",
    "recommended_action", "human_decision", "rejection_feedback",
    "revision_count", "executed", "verification_outcome", "feedback_history",
    "created_at", "resolved_at",
)


def _records_dir() -> Path:
    return Path(os.getenv("KUBEMEDIC_RECORDS_DIR", "records"))


def _safe_id(incident_id: str) -> str:
    """
    Reject anything that could escape the records directory.

    An MCP tool argument is model-supplied input reaching a filesystem path.
    Path traversal here would turn a read-only evidence tool into an arbitrary
    file read.
    """
    if not incident_id or not incident_id.startswith("INC-"):
        raise ValueError("incident_id must start with 'INC-'")
    if "/" in incident_id or "\\" in incident_id or ".." in incident_id:
        raise ValueError("incident_id contains a path separator")
    return incident_id


def list_incidents(limit: int = 20) -> dict[str, Any]:
    """Recent incident records, newest first."""
    directory = _records_dir()
    if not directory.is_dir():
        return {"incidents": [], "detail": f"no records directory at {directory}"}

    files = sorted(
        directory.glob("INC-*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )[: max(1, min(limit, 100))]

    incidents = []
    for path in files:
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            # Never fabricate: a record we cannot read is reported as such.
            incidents.append({"file": path.name, "error": str(exc)})
            continue
        incidents.append({k: record.get(k) for k in SUMMARY_FIELDS})
    return {"incidents": incidents, "count": len(incidents)}


def get_incident(incident_id: str) -> dict[str, Any]:
    """One incident record in full, including its audit log."""
    try:
        safe = _safe_id(incident_id)
    except ValueError as exc:
        return {"error": str(exc)}

    path = _records_dir() / f"{safe}.json"
    if not path.is_file():
        return {"error": f"no record for {safe}"}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"error": f"could not read {safe}: {exc}"}


def get_rejection_history(deployment: str | None = None) -> dict[str, Any]:
    """
    Every rejection reason a human has given, newest first.

    This is the most useful thing Bob can read from history: it is operator
    knowledge that the cluster evidence does not contain, and knowing what was
    refused before makes a proposal less likely to be refused again.
    """
    entries = []
    for summary in list_incidents(limit=100).get("incidents", []):
        for reason in summary.get("feedback_history") or []:
            entries.append({
                "incident_id": summary.get("incident_id"),
                "reason": reason,
                "final_state": summary.get("final_state"),
            })
        single = summary.get("rejection_feedback")
        if single and not summary.get("feedback_history"):
            entries.append({
                "incident_id": summary.get("incident_id"),
                "reason": single,
                "final_state": summary.get("final_state"),
            })
    return {"rejections": entries, "count": len(entries)}
