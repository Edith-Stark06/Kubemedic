"""
Tests for KubeMedic dashboard — all 14 scenarios from the spec.

Run:
    python -m pytest dashboard/tests/test_dashboard.py -v
"""
from __future__ import annotations

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import pytest
from httpx import AsyncClient, ASGITransport

# Import the app — this also registers Jinja2 filters
from dashboard.app import app
from dashboard.api_adapter import _MOCK_INCIDENTS


@pytest.fixture(autouse=True)
def _reset_mock():
    """Reset mock store to known state before each test."""
    import copy
    _original = copy.deepcopy(_MOCK_INCIDENTS)
    yield
    _MOCK_INCIDENTS.clear()
    _MOCK_INCIDENTS.update(_original)


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


# ── TEST 1 — Dashboard starts and renders ─────────────────────────────────

@pytest.mark.asyncio
async def test_01_dashboard_starts(client):
    """Dashboard starts and returns 200."""
    r = await client.get("/")
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"
    print("TEST 1 PASS — dashboard starts")


# ── TEST 2 — Dashboard renders ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_02_dashboard_renders(client):
    """Index page contains KubeMedic branding and incident list."""
    r = await client.get("/")
    assert r.status_code == 200
    assert "KubeMedic" in r.text
    assert "INC-501" in r.text
    assert "INC-502" in r.text
    print("TEST 2 PASS — dashboard renders incident list")


# ── TEST 3 — Incident data renders ───────────────────────────────────────

@pytest.mark.asyncio
async def test_03_incident_data_renders(client):
    """Incident detail page renders IBM Bob analysis, plan, tickets."""
    r = await client.get("/incident/INC-501")
    assert r.status_code == 200
    body = r.text
    assert "INC-501"                    in body, "Incident ID missing"
    assert "IBM Bob Analysis"           in body, "IBM Bob Analysis panel missing"
    assert "TICKET-101"                 in body, "Ticket missing"
    assert "TICKET-102"                 in body, "Ticket missing"
    assert "TICKET-103"                 in body, "Ticket missing"
    assert "rollback_deployment"        in body or "Roll back" in body, "Plan missing"
    assert "ticket-booking"             in body, "Workload missing"
    assert "Root Cause"                 in body or "root_cause" in body, "Root cause missing"
    print("TEST 3 PASS — incident data renders")


# ── TEST 4 — PENDING_APPROVAL shows Human Final Review ──────────────────

@pytest.mark.asyncio
async def test_04_pending_approval_shows_review(client):
    """PENDING_APPROVAL state shows Human Final Review with both buttons."""
    r = await client.get("/incident/INC-501")
    assert r.status_code == 200
    body = r.text
    assert "Human Final Review"         in body, "Human Final Review section missing"
    assert "btn-approve"                in body, "Approve button missing"
    assert "btn-reject"                 in body, "Reject button missing"
    assert "Approve Remediation"        in body, "Approve button text missing"
    assert "Reject Remediation"         in body, "Reject button text missing"
    print("TEST 4 PASS — PENDING_APPROVAL shows Human Final Review with both buttons")


# ── TEST 5 — Reject opens dialog (frontend) ──────────────────────────────

@pytest.mark.asyncio
async def test_05_reject_dialog_present_in_dom(client):
    """Rejection dialog is in the DOM (hidden until Reject is clicked)."""
    r = await client.get("/incident/INC-501")
    assert r.status_code == 200
    body = r.text
    assert "dialog-overlay"             in body, "Dialog overlay missing from DOM"
    assert "rejection-feedback-input"   in body, "Feedback textarea missing"
    assert "Reject &amp; Record Feedback" in body or "Reject & Record Feedback" in body, "Submit button missing"
    assert "dialog__textarea"           in body, "Dialog textarea class missing"
    print("TEST 5 PASS — rejection dialog present in DOM")


# ── TEST 6 — API: empty feedback blocked ────────────────────────────────

@pytest.mark.asyncio
async def test_06_empty_feedback_blocked(client):
    """POST /api/reject with empty feedback returns 422."""
    r = await client.post("/api/reject", json={
        "incident_id": "INC-501",
        "feedback": "",
    })
    assert r.status_code == 422, f"Expected 422 for empty feedback, got {r.status_code}: {r.text}"
    print("TEST 6 PASS — empty feedback blocked with 422")


# ── TEST 7 — API: whitespace-only feedback blocked ───────────────────────

@pytest.mark.asyncio
async def test_07_whitespace_feedback_blocked(client):
    """POST /api/reject with whitespace-only feedback returns 422."""
    r = await client.post("/api/reject", json={
        "incident_id": "INC-501",
        "feedback": "   \t\n  ",
    })
    assert r.status_code == 422, f"Expected 422 for whitespace, got {r.status_code}: {r.text}"
    print("TEST 7 PASS — whitespace-only feedback blocked with 422")


# ── TEST 8 — API: valid feedback accepted ────────────────────────────────

@pytest.mark.asyncio
async def test_08_valid_feedback_accepted(client):
    """POST /api/reject with real feedback returns 200 and FEEDBACK_RECORDED state."""
    feedback_text = (
        "Rollback is high-impact for the production booking service. "
        "Please investigate the deployment health and confirm the affected "
        "revision before retrying."
    )
    r = await client.post("/api/reject", json={
        "incident_id": "INC-501",
        "approver": "verona",
        "feedback": feedback_text,
    })
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    data = r.json()
    assert data["state"] == "FEEDBACK_RECORDED", f"Expected FEEDBACK_RECORDED, got {data['state']}"
    assert data["human_decision"]["decision"] == "rejected"
    assert data["human_decision"]["feedback"] == feedback_text
    assert data["human_decision"]["approver"] == "verona"
    print("TEST 8 PASS — valid feedback accepted, state = FEEDBACK_RECORDED")


# ── TEST 9 — Rejection result displays in UI ─────────────────────────────

@pytest.mark.asyncio
async def test_09_rejection_result_displays(client):
    """After rejection, incident detail shows REJECTED and the reason."""
    feedback_text = "Deliberate maintenance deploy — do not roll back."
    # Submit rejection
    r = await client.post("/api/reject", json={
        "incident_id": "INC-501",
        "approver": "verona",
        "feedback": feedback_text,
    })
    assert r.status_code == 200

    # Reload incident page
    r2 = await client.get("/incident/INC-501")
    assert r2.status_code == 200
    body = r2.text
    assert "REJECTED"                   in body, "REJECTED badge missing"
    assert feedback_text                in body, "Rejection reason not displayed verbatim"
    print("TEST 9 PASS — rejection result displays correctly")


# ── TEST 10 — Rejection feedback verbatim ────────────────────────────────

@pytest.mark.asyncio
async def test_10_rejection_feedback_verbatim(client):
    """Rejection reason is stored and displayed verbatim without truncation."""
    feedback_text = (
        "This deployment is an approved maintenance activity, do not roll back. "
        "The team is aware of the readiness probe failures and is monitoring."
    )
    await client.post("/api/reject", json={
        "incident_id": "INC-501",
        "approver": "verona",
        "feedback": feedback_text,
    })
    r = await client.get("/incident/INC-501")
    assert r.status_code == 200
    assert feedback_text in r.text, "Feedback not displayed verbatim"
    print("TEST 10 PASS — rejection feedback displayed verbatim")


# ── TEST 11 — No execution after rejection ────────────────────────────────

@pytest.mark.asyncio
async def test_11_no_execution_after_rejection(client):
    """After rejection, execution must be null and 'NOT executed' must appear."""
    await client.post("/api/reject", json={
        "incident_id": "INC-501",
        "approver": "verona",
        "feedback": "High risk — reject.",
    })
    # Check API
    r_api = await client.get("/api/incidents/INC-501")
    data = r_api.json()
    assert data["execution"] is None, "execution must be null after rejection"

    # Check UI
    r_ui = await client.get("/incident/INC-501")
    body = r_ui.text
    assert "NOT executed" in body or "was NOT executed" in body, "'NOT executed' not shown in UI"
    print("TEST 11 PASS — no execution after rejection, 'NOT executed' displayed")


# ── TEST 12 — Approval path still works ──────────────────────────────────

@pytest.mark.asyncio
async def test_12_approval_path_works(client):
    """Approval returns 200, state transitions to APPROVED, execution not blocked."""
    r = await client.post("/api/approve", json={
        "incident_id": "INC-501",
        "approver": "alice",
    })
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    data = r.json()
    assert data["state"] == "APPROVED", f"Expected APPROVED, got {data['state']}"
    assert data["human_decision"]["decision"] == "approved"
    assert data["human_decision"]["feedback"] is None, "Approved feedback should be null"
    assert data["execution"] is None or isinstance(data["execution"], dict), "Unexpected execution state"
    print("TEST 12 PASS — approval path works, state = APPROVED")


# ── TEST 13 — Timeline renders ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_13_timeline_renders(client):
    """Timeline panel is present and contains at least one entry."""
    r = await client.get("/incident/INC-501")
    assert r.status_code == 200
    body = r.text
    assert "panel-timeline"             in body, "Timeline panel missing"
    assert "timeline-item"              in body, "No timeline items"
    # INC-501 has timeline events from analysis
    assert "Rollout of revision 4"      in body or "rollout" in body.lower(), "Timeline content missing"
    print("TEST 13 PASS — timeline renders")


# ── TEST 14 — Missing data does not crash ─────────────────────────────────

@pytest.mark.asyncio
async def test_14_missing_data_no_crash(client):
    """Unknown incident returns 404 gracefully, not a 500."""
    r = await client.get("/incident/INC-DOES-NOT-EXIST")
    # Should return 404 via index page redirect, not 500
    assert r.status_code in (200, 404), f"Got unexpected {r.status_code}"
    assert "500" not in r.text or "Internal Server Error" not in r.text
    print("TEST 14 PASS — missing incident handled gracefully")


# ── BONUS — Audit record contains rejection_feedback ─────────────────────

@pytest.mark.asyncio
async def test_bonus_audit_contains_feedback(client):
    """After rejection, audit_log contains the rejection step with feedback."""
    feedback = "Do not roll back — approved maintenance window."
    r = await client.post("/api/reject", json={
        "incident_id": "INC-501",
        "approver": "verona",
        "feedback": feedback,
    })
    assert r.status_code == 200
    data = r.json()

    # Check audit_log
    steps = [e["step"] for e in data.get("audit_log", [])]
    assert "human_decision"    in steps, "human_decision not in audit_log"
    assert "rejection_recorded" in steps, "rejection_recorded not in audit_log"

    rejection_entry = next(e for e in data["audit_log"] if e["step"] == "rejection_recorded")
    assert rejection_entry["executed"] is False, "executed must be False"
    assert rejection_entry["reason"] == feedback, "Feedback not stored in audit_log"

    # IncidentRecord-style field: rejection_feedback
    # (available on IncidentRecord.from_incident in agent/models.py)
    assert data["human_decision"]["feedback"] == feedback

    print("BONUS TEST PASS — audit record contains rejection feedback, executed=False")
