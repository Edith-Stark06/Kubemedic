/* KubeMedic minimal console.
 *
 * Talks to the agent API on the same origin. No framework, no build step.
 *
 * One rule this page follows: it never renders anything the API did not say.
 * There are no placeholder incidents, no simulated verification results, and
 * no optimistic state. If a field is absent it renders as absent -- because
 * the whole point of the system is that it does not claim what it has not
 * checked, and a UI that fills gaps in with plausible content would undo that.
 */

const $ = (id) => document.getElementById(id);
let current = null;   // incident id under review

// ---------------------------------------------------------------- helpers

async function api(path, options) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  let body = null;
  try { body = await res.json(); } catch { /* empty body is fine */ }
  if (!res.ok) {
    const detail = body && body.detail;
    const message =
      detail && typeof detail === "object"
        ? `${detail.error || res.status}: ${detail.message || ""}`
        : `${res.status} ${detail || res.statusText}`;
    throw new Error(message);
  }
  return body;
}

function toast(message, kind = "") {
  const el = $("toast");
  el.textContent = message;
  el.className = kind;
  el.style.display = "block";
  clearTimeout(toast._t);
  toast._t = setTimeout(() => (el.style.display = "none"), 6000);
}

const esc = (s) =>
  String(s ?? "").replace(/[&<>"]/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

function row(k, v) {
  return `<div class="row"><span class="k">${esc(k)}</span><span class="v">${v}</span></div>`;
}

const STATE_CLASS = {
  RESOLVED: "ok",
  APPROVED: "ok",
  EXECUTED: "info",
  PENDING_APPROVAL: "warn",
  BOB_UNAVAILABLE: "warn",
  FEEDBACK_RECORDED: "warn",
  REJECTED: "bad",
  VERIFICATION_FAILED: "bad",
};
const stateBadge = (s) =>
  `<span class="badge ${STATE_CLASS[s] || ""}">${esc(s)}</span>`;

// ---------------------------------------------------------------- loaders

async function loadCluster() {
  try {
    const d = await api("/api/cluster");
    const badge = $("cluster-badge");
    if (!d.reachable) {
      badge.className = "badge bad";
      badge.textContent = "unreachable";
      $("workload").innerHTML =
        `<div class="empty">${esc(d.detail || "cluster unreachable")}</div>`;
      return;
    }
    badge.className = "badge ok";
    badge.textContent = "reachable";

    const w = d.workload || {};
    const h = d.application_health || {};
    const healthy = w.rollout_complete;
    $("workload").innerHTML =
      row("deployment", esc(w.name)) +
      row("image", esc(w.image)) +
      row("revision", esc(w.revision)) +
      row("replicas ready",
          `${esc(w.ready_replicas)}/${esc(w.desired_replicas)}`) +
      row("rollout complete",
          `<span class="badge ${healthy ? "ok" : "bad"}">${healthy}</span>`) +
      row("app /health",
          `<span class="badge ${h.healthy ? "ok" : "bad"}">HTTP ${esc(h.status_code)}</span>`) +
      (d.pods || []).map((p) =>
        row(`pod ${esc((p.name || "").slice(-12))}`,
            `<span class="badge ${p.ready ? "ok" : "bad"}">${p.ready ? "ready" : "not ready"}</span>`)
      ).join("") +
      (!healthy && h.healthy
        ? `<div class="note" style="margin-top:10px">The rollout is degraded while
           <code>/health</code> still returns 200 — the previous revision's pods are
           still serving. Either signal alone would mislead, which is why
           verification requires both.</div>`
        : "");
  } catch (e) {
    $("cluster-badge").className = "badge bad";
    $("cluster-badge").textContent = "error";
    $("workload").innerHTML = `<div class="empty">${esc(e.message)}</div>`;
  }
}

async function loadProviders() {
  try {
    const d = await api("/api/provider");
    $("provider").textContent = d.active;
    $("providers").innerHTML =
      d.providers.map((p) => {
        const cls = p.configured ? "ok" : "warn";
        const label = p.configured ? "configured" : "not configured";
        const calls = p.calls
          ? ` <span class="muted">${p.calls} calls, ${p.failure_total} failed</span>`
          : "";
        return row(
          (p.active ? "▸ " : "  ") + p.name,
          `<span class="badge ${cls}">${label}</span>${calls}`
        );
      }).join("") +
      row("secrets backend", esc(d.secrets_backend));
  } catch (e) {
    $("providers").innerHTML = `<div class="empty">${esc(e.message)}</div>`;
  }
}

async function loadTickets() {
  try {
    const all = await api("/api/tickets");
    const open = all.filter((t) => t.status === "open");
    $("tickets").innerHTML = open.length
      ? open.map((t) => `
          <li class="ticket">
            <div class="id">${esc(t.id)} <span class="badge warn">${esc(t.severity)}</span></div>
            <div>${esc(t.title)}</div>
            <div class="sig">${(t.signals || []).map(esc).join(" · ")}</div>
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
            <div><a href="#" data-id="${esc(i.incident_id)}" class="id">${esc(i.incident_id)}</a>
                 ${stateBadge(i.state)}</div>
            <div class="sig">${i.ticket_count} ticket(s)
                 · source ${esc(i.analysis_source || "—")}
                 · ${esc(i.recommended_action || "no plan")}</div>
          </li>`).join("")
      : `<li class="empty">none yet — collect evidence to create one</li>`;
    document.querySelectorAll("#incidents a").forEach((a) =>
      a.addEventListener("click", (e) => {
        e.preventDefault();
        showIncident(a.dataset.id);
      })
    );
  } catch (e) {
    $("incidents").innerHTML = `<li class="empty">${esc(e.message)}</li>`;
  }
}

// ---------------------------------------------------------------- detail

async function showIncident(id) {
  current = id;
  const d = await api(`/api/incidents/${id}`);
  $("detail-panel").hidden = false;
  $("d-id").textContent = id;
  $("d-state").outerHTML = stateBadge(d.state).replace("<span", '<span id="d-state"');

  // Correlation -- why these tickets are one incident.
  const c = d.correlation;
  $("d-correlation").innerHTML = c
    ? `<h2 style="margin-top:14px">Correlation — ${c.member_tickets.length} ticket(s), one incident</h2>
       ${row("members", esc(c.member_tickets.join(", ")))}
       ${row("excluded", esc(c.excluded_tickets.join(", ")) || "—")}
       <div class="muted" style="margin-top:6px">why each ticket joined:</div>
       ${(c.correlation_basis || []).map((b) => `<div class="basis">• ${esc(b)}</div>`).join("")}`
    : "";

  // Analysis -- facts, inference and recommendation kept visibly separate.
  const a = d.analysis;
  if (a && a.analysis_source !== "unavailable") {
    $("d-analysis").innerHTML = `
      <h2 style="margin-top:16px">Analysis
        <span class="badge info">${esc(a.analysis_source)}</span></h2>
      ${(a.hypotheses || []).map((h) => `
        <div class="hyp">
          <span class="badge ${h.confidence === "high" ? "ok" : "warn"}">${esc(h.confidence)}</span>
          <span class="muted">rank ${esc(h.rank)}</span>
          <div class="stmt">${esc(h.statement)}</div>
          <div class="muted" style="font-size:12px">${esc(h.confidence_reason)}</div>
          ${(h.supporting_evidence || []).map((e) => `<div class="ev">+ ${esc(e)}</div>`).join("")}
          ${(h.contradicting_evidence || []).map((e) => `<div class="ev against">− ${esc(e)}</div>`).join("")}
        </div>`).join("")}
      ${a.root_cause ? `
        <div style="margin-top:10px">
          <span class="badge inference">${a.root_cause.is_inference ? "inference" : "fact"}</span>
          <span class="badge ${a.root_cause.confidence === "high" ? "ok" : "warn"}">${esc(a.root_cause.confidence)}</span>
          <div class="stmt">${esc(a.root_cause.statement)}</div>
        </div>` : ""}
      ${a.dual_signal_note ? `<div class="note" style="margin-top:10px">${esc(a.dual_signal_note)}</div>` : ""}`;
  } else {
    $("d-analysis").innerHTML = `
      <h2 style="margin-top:16px">Analysis <span class="badge warn">unavailable</span></h2>
      <div class="note">The reasoning engine could not be reached, so no diagnosis
      was produced and no plan was built. The incident cannot be approved or
      executed. This is the designed behaviour — it reports the outage rather
      than inventing a cause.</div>
      ${a && a.reason ? `<div class="muted" style="margin-top:8px">${esc(a.reason)}</div>` : ""}`;
  }

  // Plan
  const p = d.plan;
  $("d-plan").innerHTML = p
    ? `<h2 style="margin-top:16px">Proposed remediation</h2>
       ${row("action", `<span class="badge info">${esc(p.action)}</span>`)}
       ${row("target", esc(p.target))}
       ${row("parameters", esc(JSON.stringify(p.action_parameters || {})))}
       ${row("reversible", `<span class="badge ${p.reversible ? "ok" : "warn"}">${p.reversible}</span>`)}
       ${p.reason ? `<div class="muted" style="margin-top:6px">${esc(p.reason)}</div>` : ""}`
    : "";

  // Review controls, only where a decision is actually possible.
  $("d-review").hidden = !["PENDING_APPROVAL", "ANALYSED", "APPROVED",
                           "REJECTED", "FEEDBACK_RECORDED"].includes(d.state);
  $("btn-execute").disabled = d.state !== "APPROVED";
  $("btn-approve").disabled = !["PENDING_APPROVAL", "ANALYSED"].includes(d.state);
  $("btn-reject").disabled = !["PENDING_APPROVAL", "ANALYSED"].includes(d.state);
  $("btn-revise").disabled = !["REJECTED", "FEEDBACK_RECORDED"].includes(d.state);

  $("d-feedback-history").innerHTML = (d.feedback_history || []).length
    ? `<h2 style="margin-top:16px">Reviewer feedback
         <span class="muted">revision ${esc(d.revision_count)}</span></h2>
       ${d.feedback_history.map((f, i) => `<div class="basis">${i + 1}. ${esc(f)}</div>`).join("")}`
    : "";

  const ex = d.execution;
  $("d-execution").innerHTML = ex
    ? `<h2 style="margin-top:16px">Execution</h2>
       ${row("result", `<span class="badge ${ex.success ? "ok" : "bad"}">${ex.success ? "succeeded" : "failed"}</span>`)}
       ${row("message", esc(ex.message))}
       ${row("cluster said", esc(JSON.stringify(ex.raw_response || {})))}`
    : "";

  const v = d.verification;
  $("d-verification").innerHTML = v
    ? `<h2 style="margin-top:16px">Verification
         <span class="badge ${v.outcome === "PASS" ? "ok" : "bad"}">${esc(v.outcome)}</span></h2>
       ${(v.signals || []).map((s) =>
          row(s.name, `<span class="badge ${s.passed ? "ok" : "bad"}">${s.passed ? "pass" : "fail"}</span>
                       <span class="muted">${esc(s.detail)}</span>`)).join("")}
       <div class="note safety" style="margin-top:8px">Both signals are re-read
       from the cluster after the action. The execution response is never
       accepted as proof of recovery.</div>`
    : "";

  $("d-audit").textContent = (d.audit_log || [])
    .map((e) => `${(e.step || e.stage || "?").padEnd(20)} ${JSON.stringify(
      Object.fromEntries(Object.entries(e).filter(([k]) => !["step", "stage"].includes(k)))
    )}`).join("\n");
}

// ---------------------------------------------------------------- actions

async function refreshAll() {
  await Promise.all([loadCluster(), loadProviders(), loadTickets(), loadIncidents()]);
  if (current) { try { await showIncident(current); } catch { /* gone */ } }
}

$("btn-refresh").addEventListener("click", refreshAll);

$("btn-detect").addEventListener("click", async () => {
  const btn = $("btn-detect");
  btn.disabled = true;
  btn.textContent = "collecting…";
  try {
    const inc = await api("/api/incidents", { method: "POST", body: "{}" });
    toast(`Incident ${inc.incident_id} — ${inc.state}`, "ok");
    await refreshAll();
    await showIncident(inc.incident_id);
  } catch (e) {
    toast(e.message, "bad");
  } finally {
    btn.disabled = false;
    btn.textContent = "Collect evidence & correlate";
  }
});

async function review(decision) {
  const feedback = $("d-feedback").value.trim();
  try {
    const body = JSON.stringify({ decision, approver: "console", feedback: feedback || null });
    const r = await api(`/api/incidents/${current}/review`, { method: "POST", body });
    toast(`${decision} — now ${r.state}`, "ok");
    $("d-feedback").value = "";
    await refreshAll();
  } catch (e) {
    // The server refuses a reasonless rejection regardless of this page.
    toast(e.message, "bad");
  }
}

$("btn-approve").addEventListener("click", () => review("APPROVED"));
$("btn-reject").addEventListener("click", () => review("REJECTED"));

$("btn-revise").addEventListener("click", async () => {
  try {
    const r = await api(`/api/incidents/${current}/revise`, { method: "POST" });
    toast(`Revised — ${r.recommended_action || "no plan"} (revision ${r.revision_count})`, "ok");
    await refreshAll();
  } catch (e) { toast(e.message, "bad"); }
});

$("btn-execute").addEventListener("click", async () => {
  const btn = $("btn-execute");
  btn.disabled = true;
  btn.textContent = "executing, waiting for rollout…";
  try {
    const r = await api(`/api/incidents/${current}/execute`, { method: "POST" });
    const outcome = r.verification ? r.verification.outcome : "not verified";
    toast(`Executed — verification ${outcome}`, outcome === "PASS" ? "ok" : "bad");
    await refreshAll();
  } catch (e) {
    toast(e.message, "bad");
  } finally {
    btn.textContent = "Execute & verify";
  }
});

refreshAll();
setInterval(() => { loadCluster(); loadTickets(); }, 15000);
