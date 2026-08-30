"""
kubemedic — command line orchestration.

The whole incident lifecycle without a browser: check the cluster, observe
anomalies, correlate, reason, review, execute, verify. Useful for a demo where
a UI would obscure what is happening, and for operating the system on a machine
that has no dashboard running.

    kubemedic status                    cluster, provider and ticket summary
    kubemedic providers                 which engines are configured
    kubemedic watch                     one watcher pass, explained
    kubemedic tickets                   the ticket store
    kubemedic incident new              collect evidence, correlate, reason, plan
    kubemedic incident show <id>        everything known about one incident
    kubemedic incident list             recent incidents from the record store
    kubemedic approve <id>              record approval
    kubemedic reject <id> -m "reason"   record rejection; a reason is required
    kubemedic revise <id>               ask for a plan answering the objection
    kubemedic execute <id>              execute, settle, verify
    kubemedic run                       the whole loop, with prompts

Exit codes: 0 success, 1 failure, 2 refused by a safety guard. That makes it
scriptable -- a refusal is distinguishable from a crash.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

# Incidents live in the API process, so the CLI keeps its own in-process store.
# A record on disk is the durable artifact either way.
_INCIDENTS: dict[str, Any] = {}
_STORE = "records"

EXIT_OK, EXIT_FAIL, EXIT_REFUSED = 0, 1, 2


# --------------------------------------------------------------- output

class Out:
    """Plain text by default, JSON with --json, so this can be piped."""

    def __init__(self, as_json: bool = False) -> None:
        self.as_json = as_json

    def head(self, text: str) -> None:
        if not self.as_json:
            print(f"\n{text}")
            print("-" * len(text))

    def kv(self, key: str, value: Any) -> None:
        if not self.as_json:
            print(f"  {key:<22} {value}")

    def line(self, text: str = "") -> None:
        if not self.as_json:
            print(text)

    def bullet(self, text: str) -> None:
        if not self.as_json:
            print(f"    - {text}")

    def data(self, payload: Any) -> None:
        if self.as_json:
            print(json.dumps(payload, indent=2, default=str))

    def error(self, text: str) -> None:
        print(f"error: {text}", file=sys.stderr)


# --------------------------------------------------------------- commands

def cmd_status(args, out: Out) -> int:
    from agent.k8s_client import is_cluster_reachable
    from agent.providers import configured_provider_name, get_provider
    from mcp_server import tickets as store
    from mcp_server.db import init_db

    reachable, detail = is_cluster_reachable()
    provider = get_provider()
    configured, why = provider.is_configured()

    workload = None
    if reachable:
        try:
            from agent.adapters import collect_agent_evidence
            workload = collect_agent_evidence(
                args.namespace, args.deployment, args.service
            ).raw.get("workload")
        except Exception as exc:
            detail = f"evidence collection failed: {exc}"
            reachable = False

    init_db()
    open_tickets = store.list_tickets(status="open")

    out.head("cluster")
    out.kv("reachable", reachable)
    out.kv("detail", detail)
    if workload:
        out.kv("deployment", workload.get("name"))
        out.kv("image", workload.get("image"))
        out.kv("revision", workload.get("revision"))
        out.kv("replicas ready",
               f"{workload.get('ready_replicas')}/{workload.get('desired_replicas')}")
        out.kv("rollout complete", workload.get("rollout_complete"))

    out.head("reasoning")
    out.kv("provider", configured_provider_name())
    out.kv("configured", configured)
    out.kv("detail", why)

    out.head("tickets")
    out.kv("open", len(open_tickets))

    out.data({
        "cluster": {"reachable": reachable, "detail": detail, "workload": workload},
        "reasoning": {"provider": configured_provider_name(),
                      "configured": configured, "detail": why},
        "tickets": {"open": len(open_tickets)},
    })
    return EXIT_OK if reachable else EXIT_FAIL


def cmd_providers(args, out: Out) -> int:
    from agent.providers import provider_status

    status = provider_status()
    out.head("reasoning providers")
    for entry in status["providers"]:
        marker = "*" if entry.get("active") else " "
        state = "configured" if entry.get("configured") else "not configured"
        out.kv(f"{marker} {entry['name']}", state)
        out.line(f"      {entry.get('detail', '')[:88]}")
        if entry.get("calls"):
            out.line(f"      calls={entry['calls']} ok={entry['successes']} "
                     f"failed={entry['failure_total']} avg={entry['avg_ms']}ms")
    out.kv("secrets backend", status["secrets_backend"])
    out.data(status)
    return EXIT_OK


def cmd_watch(args, out: Out) -> int:
    from mcp_server.db import init_db
    from mcp_server.watcher import KubeWatcher

    init_db()
    watcher = KubeWatcher(args.namespace, args.deployment, args.service)
    created = watcher.check_once()
    detail = watcher.last_pass or {}

    out.head("watcher pass")
    out.kv("anomalies observed", len(detail.get("observed", [])))
    for kind in detail.get("observed", []):
        out.bullet(kind)
    out.kv("tickets filed", len(created))
    for ticket_id in created:
        out.bullet(ticket_id)
    if detail.get("skipped"):
        # Never report a bare zero. "0 filed" and "0 filed because these are
        # already open" are different facts, and confusing them has cost time.
        out.kv("already open", ", ".join(detail["skipped"]))
    out.data({"created": created, **detail})
    return EXIT_OK


def cmd_tickets(args, out: Out) -> int:
    from mcp_server import tickets as store
    from mcp_server.db import init_db

    init_db()
    rows = store.list_tickets(status=args.status)
    out.head(f"tickets ({args.status or 'all'})")
    for ticket in rows:
        out.kv(ticket.id, f"[{ticket.severity.value}] {ticket.title[:66]}")
        out.line(f"      {' · '.join(ticket.signals or [])[:88]}")
    if not rows:
        out.line("  none")
    out.data([t.model_dump(mode="json") for t in rows])
    return EXIT_OK


def cmd_incident_new(args, out: Out) -> int:
    from agent.adapters import collect_agent_evidence, tickets_to_references
    from agent.correlation import correlate
    from agent.models import IncidentState
    from agent.pipeline import plan_remediation
    from agent.reasoning import run_analysis
    from mcp_server import tickets as store
    from mcp_server.db import init_db

    init_db()
    try:
        evidence = collect_agent_evidence(args.namespace, args.deployment, args.service)
    except Exception as exc:
        out.error(f"evidence collection failed: {exc}")
        return EXIT_FAIL

    references = tickets_to_references(store.list_tickets(status="open"))
    incident, excluded = correlate(references, evidence)

    out.head("correlation")
    out.kv("incident", incident.incident_id)
    out.kv("members", len(incident.tickets))
    out.kv("excluded", len(excluded))
    for reason in (incident.correlation.correlation_basis or []):
        out.bullet(reason)

    incident, analysis = run_analysis(incident)
    out.head("reasoning")
    out.kv("source", analysis.analysis_source)
    if incident.state == IncidentState.BOB_UNAVAILABLE:
        out.kv("state", incident.state.value)
        out.line("  No diagnosis was produced and no plan was built. The engine")
        out.line("  could not be reached; the incident cannot be approved.")
    else:
        for hypothesis in analysis.hypotheses[:3]:
            out.bullet(f"[{hypothesis.rank}] ({hypothesis.confidence}) "
                       f"{hypothesis.statement[:74]}")
        if analysis.root_cause:
            out.kv("root cause", analysis.root_cause.statement[:66])
            out.kv("is inference", analysis.root_cause.is_inference)
        incident = plan_remediation(incident)

    if incident.plan:
        out.head("proposed remediation")
        out.kv("action", incident.plan.action.value)
        out.kv("target", incident.plan.target)
        out.kv("parameters", incident.plan.action_parameters)
        out.kv("state", incident.state.value)
        out.line(f"\n  review it:  kubemedic approve {incident.incident_id}")
        out.line(f"              kubemedic reject  {incident.incident_id} -m \"reason\"")

    _INCIDENTS[incident.incident_id] = incident
    _save(incident)
    out.data({"incident_id": incident.incident_id, "state": incident.state.value})
    return EXIT_OK


def cmd_incident_list(args, out: Out) -> int:
    from mcp_server.incidents import list_incidents

    result = list_incidents(limit=args.limit)
    out.head("recent incidents")
    for record in result.get("incidents", []):
        out.kv(record.get("incident_id", record.get("file", "?")),
               f"{record.get('final_state')} · {record.get('analysis_source')} · "
               f"verification {record.get('verification_outcome')}")
    if not result.get("incidents"):
        out.line("  none")
    out.data(result)
    return EXIT_OK


def cmd_incident_show(args, out: Out) -> int:
    from mcp_server.incidents import get_incident

    incident = _INCIDENTS.get(args.incident_id)
    record = incident.model_dump(mode="json") if incident else get_incident(args.incident_id)
    if "error" in record:
        out.error(record["error"])
        return EXIT_FAIL

    out.head(f"incident {args.incident_id}")
    for key in ("state", "final_state", "analysis_source", "recommended_action",
                "human_decision", "revision_count", "executed",
                "verification_outcome"):
        if key in record:
            out.kv(key, record[key])
    for reason in record.get("feedback_history", []):
        out.bullet(f"feedback: {reason}")
    out.head("audit trail")
    for entry in record.get("audit_log", []):
        out.kv(entry.get("step") or entry.get("stage", "?"),
               str({k: v for k, v in entry.items()
                    if k not in ("step", "stage")})[:70])
    out.data(record)
    return EXIT_OK


def _decide(args, out: Out, decision: str) -> int:
    from agent.audit import record_decision
    from agent.models import HumanDecision

    incident = _INCIDENTS.get(args.incident_id)
    if incident is None:
        out.error(
            f"{args.incident_id} is not in this session. The CLI holds incidents "
            "in memory, so review one in the same session that created it."
        )
        return EXIT_FAIL

    if decision == "rejected" and not (args.message or "").strip():
        # Refused here as well as in the model, so the CLI gives the same
        # answer the API gives: a rejection has to say why, because the reason
        # becomes the context for the revised plan.
        out.error("a rejection must state why -- pass -m \"reason\"")
        return EXIT_REFUSED

    try:
        incident = record_decision(incident, HumanDecision(
            decision=decision, approver=args.approver, feedback=args.message))
    except ValueError as exc:
        out.error(str(exc))
        return EXIT_REFUSED

    _INCIDENTS[incident.incident_id] = incident
    out.head(f"{decision}")
    out.kv("state", incident.state.value)
    if incident.feedback_history:
        out.kv("feedback stored", incident.feedback_history[-1][:66])
    out.data({"state": incident.state.value})
    return EXIT_OK


def cmd_approve(args, out: Out) -> int:
    return _decide(args, out, "approved")


def cmd_reject(args, out: Out) -> int:
    return _decide(args, out, "rejected")


def cmd_revise(args, out: Out) -> int:
    from agent.pipeline import request_revision

    incident = _INCIDENTS.get(args.incident_id)
    if incident is None:
        out.error(f"{args.incident_id} is not in this session")
        return EXIT_FAIL
    try:
        incident = request_revision(incident)
    except ValueError as exc:
        out.error(str(exc))
        return EXIT_REFUSED

    _INCIDENTS[incident.incident_id] = incident
    out.head("revised")
    out.kv("state", incident.state.value)
    out.kv("revision", incident.revision_count)
    if incident.plan:
        out.kv("new action", f"{incident.plan.action.value} -> {incident.plan.target}")
    out.data({"state": incident.state.value})
    return EXIT_OK


def cmd_execute(args, out: Out) -> int:
    from agent.executor import execute
    from agent.k8s_client import LiveCluster
    from agent.verification import verify, wait_for_recovery

    incident = _INCIDENTS.get(args.incident_id)
    if incident is None:
        out.error(f"{args.incident_id} is not in this session")
        return EXIT_FAIL

    cluster = LiveCluster()
    try:
        incident, result = execute(incident, cluster)
    except ValueError as exc:
        # The guard, not the CLI. Exit 2 so a script can tell a refusal from a
        # crash.
        out.error(str(exc))
        return EXIT_REFUSED

    out.head("execution")
    out.kv("success", result.success)
    out.kv("message", result.message)
    if not result.success:
        _save(incident)
        return EXIT_FAIL

    namespace = incident.evidence.namespace if incident.evidence else args.namespace
    settled, detail = wait_for_recovery(cluster, incident.plan.target, namespace)
    incident.audit_log.append({"step": "settle", "settled": settled, "detail": detail})
    out.kv("settled", f"{settled} ({detail})")

    incident, verification = verify(incident, cluster)
    out.head("verification")
    out.kv("outcome", verification.outcome)
    for signal in verification.signals:
        out.kv(f"  {signal.name}", f"{'pass' if signal.passed else 'FAIL'} · {signal.detail}")
    out.kv("state", incident.state.value)

    _INCIDENTS[incident.incident_id] = incident
    out.kv("record", _save(incident))
    out.data({"verification": verification.outcome, "state": incident.state.value})
    return EXIT_OK if verification.outcome == "PASS" else EXIT_FAIL


def cmd_run(args, out: Out) -> int:
    """The whole loop in one command, pausing at the human gate."""
    if cmd_incident_new(args, out) != EXIT_OK:
        return EXIT_FAIL
    if not _INCIDENTS:
        return EXIT_FAIL
    incident_id = list(_INCIDENTS)[-1]
    incident = _INCIDENTS[incident_id]

    if incident.plan is None:
        out.line("\n  No plan to review. Stopping -- as designed.")
        return EXIT_OK

    out.line("")
    answer = input("  Approve this remediation? [y/N/r=reject with reason] ").strip().lower()
    args.incident_id = incident_id

    if answer == "y":
        if cmd_approve(args, out) != EXIT_OK:
            return EXIT_FAIL
        return cmd_execute(args, out)
    if answer == "r":
        args.message = input("  Reason for rejection: ").strip()
        return cmd_reject(args, out)

    out.line("  Not approved. Nothing was executed and the cluster is unchanged.")
    return EXIT_OK


# --------------------------------------------------------------- helpers

def _save(incident) -> str:
    from agent.audit import write_record

    try:
        return str(write_record(incident))
    except Exception as exc:          # persistence must not lose the result
        return f"(record not written: {exc})"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kubemedic",
        description="KubeMedic incident orchestration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--namespace", default=os.getenv("KUBEMEDIC_NAMESPACE", "opspilot"))
    parser.add_argument("--deployment", default=os.getenv("KUBEMEDIC_DEPLOYMENT", "ticket-booking"))
    parser.add_argument("--service", default=os.getenv("KUBEMEDIC_SERVICE", "ticket-booking"))
    parser.add_argument("--approver", default=os.getenv("USER") or "cli")

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="cluster, provider and ticket summary").set_defaults(fn=cmd_status)
    sub.add_parser("providers", help="which reasoning engines are configured").set_defaults(fn=cmd_providers)
    sub.add_parser("watch", help="one watcher pass, explained").set_defaults(fn=cmd_watch)
    sub.add_parser("run", help="the whole loop, pausing at the human gate").set_defaults(fn=cmd_run)

    tickets = sub.add_parser("tickets", help="the ticket store")
    tickets.add_argument("--status", default="open")
    tickets.set_defaults(fn=cmd_tickets)

    incident = sub.add_parser("incident", help="incident lifecycle")
    isub = incident.add_subparsers(dest="subcommand", required=True)
    isub.add_parser("new", help="collect, correlate, reason, plan").set_defaults(fn=cmd_incident_new)
    show = isub.add_parser("show", help="everything known about one incident")
    show.add_argument("incident_id")
    show.set_defaults(fn=cmd_incident_show)
    listing = isub.add_parser("list", help="recent incidents from the record store")
    listing.add_argument("--limit", type=int, default=10)
    listing.set_defaults(fn=cmd_incident_list)

    for name, fn, help_text in (
        ("approve", cmd_approve, "record approval"),
        ("reject", cmd_reject, "record rejection; a reason is required"),
        ("revise", cmd_revise, "ask for a plan answering the objection"),
        ("execute", cmd_execute, "execute, settle, verify"),
    ):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("incident_id")
        p.add_argument("-m", "--message", default=None, help="reason (required to reject)")
        p.set_defaults(fn=fn)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    out = Out(as_json=args.json)
    if not hasattr(args, "message"):
        args.message = None
    try:
        return args.fn(args, out)
    except KeyboardInterrupt:
        out.error("interrupted -- nothing was executed")
        return EXIT_FAIL


if __name__ == "__main__":
    sys.exit(main())
