/* KubeMedic operator console.
 *
 * One rule this page follows: it never renders anything the API did not say.
 * No placeholder incidents, no simulated verification, no optimistic state. If
 * a field is absent it renders as absent — the whole point of the system is
 * that it does not claim what it has not checked, and a UI that fills gaps
 * with plausible content would undo that.
 */

const $ = (id) => document.getElementById(id);
let current = null;

// ------------------------------------------------------------------ helpers

async function api(path, options) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  let body = null;
  try { body = await res.json(); } catch { /* empty body is fine */ }
  if (!res.ok) {
    const d = body && body.detail;
    throw new Error(
      d && typeof d === "object"
        ? `${d.error || res.status}: ${d.message || ""}`
        : `${res.status} ${d || res.statusText}`
    );
  }
  return body;
}

function toast(message, kind = "") {
  const el = $("toast");
  el.textContent = message;
  el.className = kind;
  el.style.display = "block";
  clearTimeout(toast._t);
  toast._t = setTimeout(() => (el.style.display = "none"), 6500);
}

const esc = (s) =>
  String(s ?? "").replace(/[&<>"]/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

const kv = (k, v) =>
  `<div class="kv"><span class="k">${esc(k)}</span><span class="v">${v}</span></div>`;

const STATE_CLASS = {
  RESOLVED: "ok", APPROVED: "ok", EXECUTED: "info",
  PENDING_APPROVAL: "warn", BOB_UNAVAILABLE: "warn", FEEDBACK_RECORDED: "warn",
  ANALYSED: "info", EVIDENCE_COLLECTED: "grey",
  REJECTED: "bad", VERIFICATION_FAILED: "bad",
};
const badge = (s, cls) => `<span class="badge ${cls ?? STATE_CLASS[s] ?? "grey"}">${esc(s)}</span>`;

// ------------------------------------------------------------- lifecycle

const STAGES = [
  "Incident", "Evidence", "Correlated", "Analysis",
  "Proposal", "Review", "Execution", "Verified",
];

function renderSteps(incident) {
  let reached = 0;
  if (incident) {
    const s = incident.state;
    reached = 3;                                            // evidence + correlation
    if (incident.analysis_source && incident.analysis_source !== "unavailable") reached = 4;
    if (incident.recommended_action) reached = 5;
    if (["APPROVED", "REJECTED", "FEEDBACK_RECORDED"].includes(s)) reached = 6;
    if (["EXECUTING", "EXECUTED"].includes(s)) reached = 7;
    if (["RESOLVED", "VERIFICATION_FAILED"].includes(s)) reached = 8;
  }
  $("steps").innerHTML = STAGES.map((label, i) => {
    const n = i + 1;
    const cls = n < reached ? "done" : n === reached ? "active" : "";
    return `<div class="step ${cls}"><span class="n">${n}</span>${esc(label)}</div>`;
  }).join("");
  $("stage-note").textContent = incident
    ? `${incident.incident_id} — ${incident.state}`
    : "not started";
}

// --------------------------------------------------------------- loaders

async function loadDemo() {
  try {
    const d = await api("/api/demo");
    $("demo-state").innerHTML =
      kv("mode", d.demo_active
        ? badge("dry run (fixture cluster)", "info")
        : badge("live cluster", "grey")) +
      kv("live cluster", d.live_cluster_reachable
        ? badge("reachable", "ok") : badge("unreachable", "warn")) +
      (d.live_cluster_reachable ? "" :
        `<div class="muted" style="font-size:12px;margin-top:6px">${esc(d.live_cluster_detail)}</div>`);
    $("btn-demo-start").textContent = d.demo_active ? "Restart dry run" : "Start dry run";
    $("btn-demo-stop").disabled = !d.demo_active;
  } catch (e) {
    $("demo-state").innerHTML = `<div class="empty">${esc(e.message)}</div>`;
  }
}

async function loadCluster() {
  try {
    const d = await api("/api/cluster");
    const b = $("cluster-badge");
    if (!d.reachable) {
      b.textContent = "unreachable";
      $("brand-dot").style.background = "var(--warn)";
      $("workload").innerHTML =
        `<div class="empty">${esc(d.detail || "cluster unreachable")}</div>`;
      return;
    }
    b.textContent = d.demo ? "fixture" : "live";
    const w = d.workload || {}, h = d.application_health || {};
    const rollout = w.rollout_complete;
    $("brand-dot").style.background = rollout ? "var(--ok)" : "var(--bad)";
    $("workload").innerHTML =
      kv("deployment", esc(w.name)) +
      kv("image", esc(w.image)) +
      kv("revision", esc(w.revision)) +
      kv("replicas ready", `${esc(w.ready_replicas)}/${esc(w.desired_replicas)}`) +
      kv("rollout complete", badge(String(rollout), rollout ? "ok" : "bad")) +
      kv("app /health", badge(`HTTP ${h.status_code}`, h.healthy ? "ok" : "bad")) +
      (d.pods || []).map((p) =>
        kv(`pod ${esc((p.name || "").slice(-14))}`,
           badge(p.ready ? "ready" : "not ready", p.ready ? "ok" : "bad"))).join("") +
      (!rollout && h.healthy
        ? `<div class="note warn">The rollout is degraded while <code>/health</code>
           still returns 200 — the previous revision's pods are still serving.
           Either signal alone would mislead, which is why verification requires
           both.</div>` : "");
  } catch (e) {
    $("workload").innerHTML = `<div class="empty">${esc(e.message)}</div>`;
  }
}

async function loadProviders() {
  try {
    const d = await api("/health/ai");
    $("provider").textContent = d.active_provider || "none";
    const st = (s) => badge(s, s === "available" ? "ok" : s === "not_configured" ? "warn" : "bad");
    $("providers").innerHTML =
      kv("primary", `${esc(d.primary_provider)} ${st(d.primary_status)}`) +
      kv("fallback", `${esc(d.fallback_provider)} ${st(d.fallback_status)}`) +
      kv("fallback enabled", badge(String(d.fallback_enabled), d.fallback_enabled ? "ok" : "grey")) +
      kv("active", d.active_provider ? badge(d.active_provider, "info") : badge("none", "bad")) +
      (d.active_provider ? "" :
        `<div class="note warn">No engine is reachable. Incidents will report
         <strong>BOB_UNAVAILABLE</strong> and no plan will be built — the system
         reports the outage rather than inventing a diagnosis.</div>`);
  } catch (e) {
    $("providers").innerHTML = `<div class="empty">${esc(e.message)}</div>`;
  }
}

async function loadTickets() {
  try {
    const all = await api("/api/tickets");
    const open = all.filter((t) => !t.status || t.status === "open");
    $("ticket-count").textContent = open.length;
    $("tickets").innerHTML = open.length
      ? open.map((t) => `
          <li>
            <span class="tid">${esc(t.id)}</span>
            ${badge(t.severity || "high", t.severity === "medium" ? "warn" : "bad")}
            <div class="ttitle">${esc(t.title)}</div>
            <div class="tsig">${(t.signals || []).map(esc).join(" · ")}</div>
          </li>`).join("")
      : `<li class="empty">no open tickets</li>`;
  } catch (e) {
    $("tickets").innerHTML = `<li class="empty">${esc(e.message)}</li>`;
  }
}

async function loadIncidents() {
  try {
    const list = await api("/api/incidents");
    $("incidents").innerHTML = list.length
      ? list.map((i) => `
          <li>
            <a href="#" class="incident" data-id="${esc(i.incident_id)}">${esc(i.incident_id)}</a>
            ${badge(i.state)}
            <div class="tsig">${i.ticket_count} ticket(s) ·
              source ${esc(i.analysis_source || "—")} ·
              ${esc(i.recommended_action || "no plan")}</div>
          </li>`).join("")
      : `<li class="empty">none yet — collect evidence to create one</li>`;
    document.querySelectorAll("#incidents a").forEach((a) =>
      a.addEventListener("click", (e) => { e.preventDefault(); showIncident(a.dataset.id); }));
  } catch (e) {
    $("incidents").innerHTML = `<li class="empty">${esc(e.message)}</li>`;
  }
}

// ---------------------------------------------------------------- detail

async function showIncident(id) {
  current = id;
  const d = await api(`/api/incidents/${id}`);
  $("detail-card").hidden = false;
  $("d-id").textContent = id;
  $("d-state").className = `badge ${STATE_CLASS[d.state] || "grey"}`;
  $("d-state").textContent = d.state;

  const c = d.correlation;
  $("d-correlation").innerHTML = c ? `
    <h3 style="font-size:13px;margin:4px 0 8px">Correlation —
      ${c.member_tickets.length} ticket(s), one incident</h3>
    ${kv("members", esc(c.member_tickets.join(", ")))}
    ${kv("excluded", esc(c.excluded_tickets.join(", ")) || "—")}
    <div class="muted" style="font-size:12.5px;margin:8px 0 4px">why each ticket joined:</div>
    ${(c.correlation_basis || []).map((b) => `<div class="basis">${esc(b)}</div>`).join("")}` : "";

  const a = d.analysis;
  if (a && a.analysis_source !== "unavailable") {
    $("d-analysis").innerHTML = `
      <h3 style="font-size:13px;margin:18px 0 8px">Analysis ${badge(a.analysis_source, "info")}</h3>
      ${(a.hypotheses || []).map((h) => `
        <div class="hyp">
          <div class="top">
            ${badge(h.confidence, h.confidence === "high" ? "ok" : "warn")}
            <span class="muted" style="font-size:12px">rank ${esc(h.rank)}</span>
          </div>
          <div class="stmt">${esc(h.statement)}</div>
          <div class="why">${esc(h.confidence_reason)}</div>
          ${(h.supporting_evidence || []).map((e) => `<div class="ev for">${esc(e)}</div>`).join("")}
          ${(h.contradicting_evidence || []).map((e) => `<div class="ev against">${esc(e)}</div>`).join("")}
        </div>`).join("")}
      ${a.root_cause ? `
        <div style="margin-top:10px">
          ${badge(a.root_cause.is_inference ? "inference" : "fact", "infer")}
          ${badge(a.root_cause.confidence, a.root_cause.confidence === "high" ? "ok" : "warn")}
          <div class="stmt" style="margin-top:6px">${esc(a.root_cause.statement)}</div>
        </div>` : ""}
      ${a.dual_signal_note ? `<div class="note">${esc(a.dual_signal_note)}</div>` : ""}`;
  } else {
    $("d-analysis").innerHTML = `
      <h3 style="font-size:13px;margin:18px 0 8px">Analysis ${badge("unavailable", "warn")}</h3>
      <div class="note warn">The reasoning engine could not be reached, so no
      diagnosis was produced and no plan was built. This incident cannot be
      approved or executed. That is the designed behaviour — it reports the
      outage rather than inventing a cause.</div>
      ${a && a.reason ? `<div class="muted" style="font-size:12.5px;margin-top:8px">${esc(a.reason)}</div>` : ""}`;
  }

  const p = d.plan;
  $("d-plan").innerHTML = p ? `
    <h3 style="font-size:13px;margin:18px 0 8px">Proposed remediation</h3>
    ${kv("action", badge(p.action, "info"))}
    ${kv("target", esc(p.target))}
    ${kv("parameters", esc(JSON.stringify(p.action_parameters || {})))}
    ${kv("reversible", badge(String(p.reversible), p.reversible ? "ok" : "warn"))}
    ${p.reason ? `<div class="muted" style="font-size:12.5px;margin-top:8px">${esc(p.reason)}</div>` : ""}` : "";

  const reviewable = ["PENDING_APPROVAL", "ANALYSED"].includes(d.state);
  const revisable  = ["REJECTED", "FEEDBACK_RECORDED"].includes(d.state);
  $("d-review").hidden = !(reviewable || revisable || d.state === "APPROVED");
  $("btn-approve").disabled = !reviewable;
  $("btn-reject").disabled  = !reviewable;
  $("btn-revise").disabled  = !revisable;
  $("btn-execute").disabled = d.state !== "APPROVED";

  $("d-feedback-history").innerHTML = (d.feedback_history || []).length ? `
    <h3 style="font-size:13px;margin:18px 0 8px">Reviewer feedback
      <span class="muted" style="font-weight:400">revision ${esc(d.revision_count)}</span></h3>
    ${d.feedback_history.map((f, i) => `<div class="basis">${i + 1}. ${esc(f)}</div>`).join("")}` : "";

  const ex = d.execution;
  $("d-execution").innerHTML = ex ? `
    <h3 style="font-size:13px;margin:18px 0 8px">Execution</h3>
    ${kv("result", badge(ex.success ? "succeeded" : "failed", ex.success ? "ok" : "bad"))}
    ${kv("message", esc(ex.message))}
    ${kv("cluster said", esc(JSON.stringify(ex.raw_response || {})))}` : "";

  const v = d.verification;
  $("d-verification").innerHTML = v ? `
    <h3 style="font-size:13px;margin:18px 0 8px">Verification
      ${badge(v.outcome, v.outcome === "PASS" ? "ok" : "bad")}</h3>
    ${(v.signals || []).map((s) =>
      kv(s.name, `${badge(s.passed ? "pass" : "fail", s.passed ? "ok" : "bad")}
        <span class="muted"> ${esc(s.detail)}</span>`)).join("")}
    <div class="note safe">Both signals are re-read from the cluster after the
    action. The execution response is never accepted as proof of recovery.</div>` : "";

  $("d-audit").textContent = (d.audit_log || []).map((e) =>
    `${(e.step || e.stage || "?").padEnd(20)} ${JSON.stringify(
      Object.fromEntries(Object.entries(e).filter(([k]) => !["step", "stage"].includes(k))))}`
  ).join("\n");

  renderSteps({ ...d, incident_id: id,
                recommended_action: p ? p.action : null,
                analysis_source: a ? a.analysis_source : null });
}

// --------------------------------------------------------------- actions

async function refreshAll() {
  await Promise.all([loadDemo(), loadCluster(), loadProviders(), loadTickets(), loadIncidents()]);
  if (current) { try { await showIncident(current); } catch { current = null; } }
  else renderSteps(null);
}

function busy(btn, label) {
  btn.disabled = true;
  btn._label = btn.textContent;
  btn.innerHTML = `<span class="spin"></span> ${label}`;
  return () => { btn.disabled = false; btn.textContent = btn._label; };
}

$("btn-refresh").addEventListener("click", refreshAll);

$("btn-demo-start").addEventListener("click", async () => {
  const done = busy($("btn-demo-start"), "resetting…");
  try {
    const d = await api("/api/demo/start", { method: "POST" });
    current = null;
    toast(`Dry run ready — ${d.tickets.length} tickets, cluster broken`, "ok");
    $("detail-card").hidden = true;
    await refreshAll();
  } catch (e) { toast(e.message, "bad"); } finally { done(); }
});

$("btn-demo-stop").addEventListener("click", async () => {
  try {
    await api("/api/demo/stop", { method: "POST" });
    current = null;
    $("detail-card").hidden = true;
    toast("Back to the live cluster", "ok");
    await refreshAll();
  } catch (e) { toast(e.message, "bad"); }
});

$("btn-detect").addEventListener("click", async () => {
  const done = busy($("btn-detect"), "collecting & reasoning…");
  try {
    const inc = await api("/api/incidents", { method: "POST", body: "{}" });
    toast(`${inc.incident_id} — ${inc.state}`, inc.recommended_action ? "ok" : "bad");
    await refreshAll();
    await showIncident(inc.incident_id);
  } catch (e) { toast(e.message, "bad"); } finally { done(); }
});

async function review(decision, feedback) {
  const body = JSON.stringify({ decision, approver: "console", feedback: feedback || null });
  const r = await api(`/api/incidents/${current}/review`, { method: "POST", body });
  toast(`${decision} — now ${r.state}`, "ok");
  await refreshAll();
}

$("btn-approve").addEventListener("click", async () => {
  const done = busy($("btn-approve"), "recording…");
  try { await review("APPROVED"); } catch (e) { toast(e.message, "bad"); } finally { done(); }
});

// Reject opens a modal. The button is not the control -- the server refuses a
// reasonless rejection whatever this page allows -- but asking properly is
// what makes the reason worth writing.
$("btn-reject").addEventListener("click", () => {
  $("reject-reason").value = "";
  $("reject-reason").classList.remove("invalid");
  $("reject-modal").hidden = false;
  $("reject-reason").focus();
});
$("reject-cancel").addEventListener("click", () => { $("reject-modal").hidden = true; });
$("reject-modal").addEventListener("click", (e) => {
  if (e.target === $("reject-modal")) $("reject-modal").hidden = true;
});

$("reject-confirm").addEventListener("click", async () => {
  const reason = $("reject-reason").value.trim();
  if (!reason) {
    $("reject-reason").classList.add("invalid");
    toast("A reason is required — the agent needs it to propose something different", "bad");
    return;
  }
  const done = busy($("reject-confirm"), "recording…");
  try {
    await review("REJECTED", reason);
    $("reject-modal").hidden = true;
  } catch (e) { toast(e.message, "bad"); } finally { done(); }
});

$("btn-revise").addEventListener("click", async () => {
  const done = busy($("btn-revise"), "reasoning…");
  try {
    const r = await api(`/api/incidents/${current}/revise`, { method: "POST" });
    toast(`Revised — ${r.recommended_action || "no plan"} (revision ${r.revision_count})`, "ok");
    await refreshAll();
  } catch (e) { toast(e.message, "bad"); } finally { done(); }
});

$("btn-execute").addEventListener("click", async () => {
  const done = busy($("btn-execute"), "executing, waiting for rollout…");
  try {
    const r = await api(`/api/incidents/${current}/execute`, { method: "POST" });
    const outcome = r.verification ? r.verification.outcome : "not verified";
    toast(`Executed — verification ${outcome}`, outcome === "PASS" ? "ok" : "bad");
    await refreshAll();
  } catch (e) { toast(e.message, "bad"); } finally { done(); }
});

refreshAll();
setInterval(() => { if (!current) { loadCluster(); loadTickets(); } }, 20000);
