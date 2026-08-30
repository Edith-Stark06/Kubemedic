/**
 * KubeMedic Dashboard — app.js
 *
 * Responsibilities:
 *  - submitApproval()       POST /api/approve
 *  - openRejectDialog()     Open rejection dialog (no API call yet)
 *  - closeRejectDialog()    Cancel — zero side effects
 *  - submitRejection()      POST /api/reject with feedback
 *  - toggleAudit()          Expand/collapse audit record
 *
 * Field name contract:
 *  The rejection POST body uses field name "feedback" — matching
 *  HumanDecision.feedback in agent/models.py (not "reason", not a different name).
 *  The server returns 422 on empty or whitespace-only feedback.
 *
 * Safety rules:
 *  - Both Approve and Reject buttons are disabled immediately on click
 *    before any fetch resolves (prevents double-submission).
 *  - Rejection dialog submit stays disabled until textarea.trim().length > 0.
 *  - On any fetch error, buttons are re-enabled and the error is shown inline.
 *  - On dialog cancel: zero state change, zero API call.
 *  - Feedback text is preserved across recoverable errors so the user
 *    does not have to retype it.
 */

"use strict";

// ── State ─────────────────────────────────────────────────────────────────

const _state = {
  incidentId: null,
  reviewer: "reviewer",
  submitting: false,
};

// ── Init ──────────────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", () => {
  const main = document.getElementById("incident-main");
  if (!main) return; // index page — nothing to init

  _state.incidentId = main.dataset.incidentId || null;
  _state.reviewer   = main.dataset.reviewer    || "reviewer";

  // Wire textarea → submit button enable/disable
  const textarea = document.getElementById("rejection-feedback-input");
  if (textarea) {
    textarea.addEventListener("input", _onFeedbackInput);
    // Autofocus is handled by openRejectDialog()
  }

  // ESC closes dialog
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeRejectDialog();
  });

  // Click outside dialog closes it
  const overlay = document.getElementById("dialog-overlay");
  if (overlay) {
    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) closeRejectDialog();
    });
  }
});

// ── Approve ───────────────────────────────────────────────────────────────

async function submitApproval() {
  if (_state.submitting) return;

  const btnApprove = document.getElementById("btn-approve");
  const btnReject  = document.getElementById("btn-reject");

  // Disable both immediately — no double-click
  _disableButtons(btnApprove, btnReject);
  _state.submitting = true;

  const inlineError = _getOrCreateInlineError("review-controls");

  try {
    const res = await fetch("/api/approve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        incident_id: _state.incidentId,
        approver: _state.reviewer,
      }),
    });

    if (!res.ok) {
      const detail = await _extractError(res);
      _showInlineError(inlineError, `Approval failed (HTTP ${res.status}): ${detail}`);
      _enableButtons(btnApprove, btnReject);
      _state.submitting = false;
      return;
    }

    // Success — reload page to reflect new state from server
    window.location.reload();
  } catch (err) {
    _showInlineError(inlineError, `Network error: ${err.message}. Please try again.`);
    _enableButtons(btnApprove, btnReject);
    _state.submitting = false;
  }
}

// ── Reject Dialog — Open ──────────────────────────────────────────────────

function openRejectDialog() {
  if (_state.submitting) return;

  // Disable both review controls while dialog is open
  const btnApprove = document.getElementById("btn-approve");
  const btnReject  = document.getElementById("btn-reject");
  _disableButtons(btnApprove, btnReject);

  // Populate summary inside dialog
  _populateDialogSummary();

  // Reset dialog state
  const textarea  = document.getElementById("rejection-feedback-input");
  const submitBtn = document.getElementById("btn-dialog-submit");
  const errorEl   = document.getElementById("dialog-error");
  const hintEl    = document.getElementById("feedback-hint");

  // Do NOT clear feedback — preserve across cancels if user re-opens
  // (only clear on successful submission)
  if (submitBtn) {
    submitBtn.disabled = true;
    submitBtn.setAttribute("aria-disabled", "true");
  }
  if (errorEl) errorEl.hidden = true;
  if (hintEl)  hintEl.textContent = "";

  // Show dialog
  const overlay = document.getElementById("dialog-overlay");
  overlay.hidden = false;
  overlay.removeAttribute("hidden");

  // Autofocus textarea
  if (textarea) {
    setTimeout(() => textarea.focus(), 50);
  }
}

// ── Reject Dialog — Close (Cancel) ────────────────────────────────────────

function closeRejectDialog() {
  const overlay = document.getElementById("dialog-overlay");
  overlay.hidden = true;

  // Re-enable review controls
  const btnApprove = document.getElementById("btn-approve");
  const btnReject  = document.getElementById("btn-reject");
  _enableButtons(btnApprove, btnReject);

  // Hide any error that was showing
  const errorEl = document.getElementById("dialog-error");
  if (errorEl) errorEl.hidden = true;

  // Do NOT clear feedback text — user might re-open the dialog
}

// ── Reject Dialog — Textarea Validation ───────────────────────────────────

function _onFeedbackInput() {
  const textarea  = document.getElementById("rejection-feedback-input");
  const submitBtn = document.getElementById("btn-dialog-submit");
  const hintEl    = document.getElementById("feedback-hint");

  if (!textarea || !submitBtn) return;

  const trimmed = textarea.value.trim();
  const valid   = trimmed.length > 0;

  submitBtn.disabled = !valid;
  submitBtn.setAttribute("aria-disabled", String(!valid));

  if (hintEl) {
    if (textarea.value.length > 0 && !valid) {
      hintEl.textContent = "Feedback cannot be whitespace only.";
    } else {
      hintEl.textContent = "";
    }
  }
}

// ── Reject Dialog — Submit ────────────────────────────────────────────────

async function submitRejection() {
  const textarea  = document.getElementById("rejection-feedback-input");
  const submitBtn = document.getElementById("btn-dialog-submit");
  const cancelBtn = document.getElementById("btn-dialog-cancel");
  const errorEl   = document.getElementById("dialog-error");

  if (!textarea) return;

  const feedback = textarea.value.trim();

  // Final client-side guard (server also validates)
  if (!feedback) {
    if (errorEl) {
      errorEl.textContent = "A rejection reason is required.";
      errorEl.hidden = false;
    }
    textarea.focus();
    return;
  }

  if (_state.submitting) return;
  _state.submitting = true;

  // Disable dialog buttons during request
  if (submitBtn) { submitBtn.disabled = true; submitBtn.setAttribute("aria-disabled", "true"); }
  if (cancelBtn) { cancelBtn.disabled = true; }
  if (errorEl)   { errorEl.hidden = true; }

  try {
    const res = await fetch("/api/reject", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        incident_id: _state.incidentId,
        approver: _state.reviewer,
        feedback: feedback,        // matches HumanDecision.feedback in agent/models.py
      }),
    });

    if (!res.ok) {
      const detail = await _extractError(res);
      if (errorEl) {
        errorEl.textContent = `Rejection failed (HTTP ${res.status}): ${detail}`;
        errorEl.hidden = false;
      }
      // Re-enable so user can fix and retry
      if (submitBtn) { submitBtn.disabled = false; submitBtn.setAttribute("aria-disabled", "false"); }
      if (cancelBtn) { cancelBtn.disabled = false; }
      _state.submitting = false;
      return;
    }

    // Success — feedback was stored; clear it then reload
    textarea.value = "";
    window.location.reload();
  } catch (err) {
    if (errorEl) {
      errorEl.textContent = `Network error: ${err.message}. Your feedback is preserved — please try again.`;
      errorEl.hidden = false;
    }
    if (submitBtn) { submitBtn.disabled = false; submitBtn.setAttribute("aria-disabled", "false"); }
    if (cancelBtn) { cancelBtn.disabled = false; }
    _state.submitting = false;
  }
}

// ── Demo controls (index page only) ──────────────────────────────────────

async function injectIncident() {
  const btn    = document.getElementById("btn-inject");
  const status = document.getElementById("demo-status");
  if (btn) btn.disabled = true;
  if (status) { status.hidden = false; status.textContent = "Injecting incident…"; status.className = "demo-controls-status"; }

  try {
    const res = await fetch("/api/demo/inject", { method: "POST" });
    if (!res.ok) {
      const detail = await _extractError(res);
      if (status) { status.textContent = `Failed: ${detail}`; status.className = "demo-controls-status demo-controls-status--err"; }
    } else {
      if (status) { status.textContent = "Incident injected — refresh the page in a moment."; status.className = "demo-controls-status demo-controls-status--ok"; }
      setTimeout(() => window.location.reload(), 1200);
    }
  } catch (err) {
    if (status) { status.textContent = `Network error: ${err.message}`; status.className = "demo-controls-status demo-controls-status--err"; }
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function resetWorkload() {
  const btn    = document.getElementById("btn-reset");
  const status = document.getElementById("demo-status");
  if (btn) btn.disabled = true;
  if (status) { status.hidden = false; status.textContent = "Resetting workload…"; status.className = "demo-controls-status"; }

  try {
    const res = await fetch("/api/demo/reset", { method: "POST" });
    if (!res.ok) {
      const detail = await _extractError(res);
      if (status) { status.textContent = `Failed: ${detail}`; status.className = "demo-controls-status demo-controls-status--err"; }
    } else {
      if (status) { status.textContent = "Workload reset — cluster is healthy."; status.className = "demo-controls-status demo-controls-status--ok"; }
      setTimeout(() => window.location.reload(), 1500);
    }
  } catch (err) {
    if (status) { status.textContent = `Network error: ${err.message}`; status.className = "demo-controls-status demo-controls-status--err"; }
  } finally {
    if (btn) btn.disabled = false;
  }
}

// ── Audit toggle ──────────────────────────────────────────────────────────

function toggleAudit() {
  const body   = document.getElementById("audit-body");
  const toggle = document.getElementById("audit-toggle");
  if (!body || !toggle) return;

  const isHidden = body.hidden;
  body.hidden = !isHidden;
  toggle.textContent     = isHidden ? "Hide ▴" : "Show ▾";
  toggle.setAttribute("aria-expanded", String(isHidden));
}

// ── Dialog summary population ─────────────────────────────────────────────

function _populateDialogSummary() {
  const container = document.getElementById("dialog-summary");
  if (!container) return;

  // Read from the rendered plan panel if present
  const planPanel = document.getElementById("panel-plan");
  if (!planPanel) {
    container.innerHTML = `<p style="color:var(--text-muted);font-size:14px;">Incident: <strong>${_state.incidentId}</strong></p>`;
    return;
  }

  const rows = [
    { label: "Incident", value: _state.incidentId },
    { label: "Action",   value: _getPlanField(planPanel, "Action") },
    { label: "Target",   value: _getPlanField(planPanel, "Target") },
    { label: "Risk",     value: _getPlanFieldRaw(planPanel, "risk-badge") },
    { label: "Blast",    value: _getPlanField(planPanel, "Blast Radius") },
  ];

  container.innerHTML = rows
    .filter(r => r.value)
    .map(r => `
      <div class="dialog__summary-row">
        <span class="dialog__summary-label">${r.label}</span>
        <span class="dialog__summary-value">${_escHtml(r.value)}</span>
      </div>
    `)
    .join("");
}

function _getPlanField(panel, labelText) {
  const labels = panel.querySelectorAll(".plan-field__label");
  for (const label of labels) {
    if (label.textContent.trim().toLowerCase().includes(labelText.toLowerCase())) {
      const val = label.nextElementSibling;
      return val ? val.textContent.trim() : null;
    }
  }
  return null;
}

function _getPlanFieldRaw(panel, cls) {
  const el = panel.querySelector(`.${cls}`);
  return el ? el.textContent.trim() : null;
}

// ── Utilities ─────────────────────────────────────────────────────────────

function _disableButtons(...buttons) {
  for (const btn of buttons) {
    if (btn) {
      btn.disabled = true;
      btn.setAttribute("aria-disabled", "true");
    }
  }
}

function _enableButtons(...buttons) {
  for (const btn of buttons) {
    if (btn) {
      btn.disabled = false;
      btn.setAttribute("aria-disabled", "false");
    }
  }
}

async function _extractError(res) {
  try {
    const data = await res.json();
    if (data.detail) {
      if (Array.isArray(data.detail)) {
        return data.detail.map(e => e.msg || JSON.stringify(e)).join("; ");
      }
      return String(data.detail);
    }
    return JSON.stringify(data);
  } catch {
    return res.statusText || "Unknown error";
  }
}

function _getOrCreateInlineError(parentId) {
  const parent = document.getElementById(parentId);
  if (!parent) return null;
  let el = parent.querySelector(".inline-error");
  if (!el) {
    el = document.createElement("div");
    el.className = "inline-error";
    el.setAttribute("role", "alert");
    el.hidden = true;
    parent.appendChild(el);
  }
  return el;
}

function _showInlineError(el, msg) {
  if (!el) return;
  el.textContent = msg;
  el.hidden = false;
}

function _escHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
