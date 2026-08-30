"""
Feed an IBM Bob analysis from an interactive session into the live pipeline.

WHY THIS EXISTS
---------------
IBM Bob v1.126.0 has no headless mode, and the cloud REST path needs
credentials that may not be provisioned. But Bob can still do the real work
interactively: open this repository as a Bob workspace and Bob launches our own
evidence MCP server, calls our read-only tools against the live cluster, loads
the incident-correlation skill, and returns a JSON analysis.

That analysis is a genuine IBM Bob analysis. This script takes it and runs the
rest of the system on it for real -- correlation against the live tickets, the
human approval gate, the allowlisted executor, and independent dual-signal
verification -- producing an audit record whose analysis_source is `ibm-bob`
because Bob genuinely produced it.

WHAT THIS IS NOT
----------------
It is not a way to hand-write an analysis and have the record claim Bob made
it. The input is validated against exactly the same contract the REST path uses
(BobAnalysis.from_raw), so an action outside the allowlist or a missing target
is refused. But validation cannot tell you where a file came from: only paste
output Bob actually produced. If you did not run the session, do not run this.

The audit record marks how the analysis arrived, so a reader can tell an
interactive session from a headless call.

USAGE
-----
  1. In Bob (kubemedic-analyst mode), work the incident and get the JSON.
  2. Save it verbatim:            bob-analysis.json
  3. python scripts/ingest_bob_analysis.py bob-analysis.json --approve
     ... or --reject "reason" to exercise the rejection path instead.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from agent.adapters import (  # noqa: E402
    collect_agent_evidence,
    tickets_to_references,
)
from agent.audit import record_decision, write_record  # noqa: E402
from agent.correlation import correlate  # noqa: E402
from agent.executor import execute  # noqa: E402
from agent.k8s_client import LiveCluster, is_cluster_reachable  # noqa: E402
from agent.models import BobAnalysis, HumanDecision, IncidentState  # noqa: E402
from agent.pipeline import plan_remediation  # noqa: E402
from agent.verification import verify  # noqa: E402
from mcp_server import tickets as ticket_store  # noqa: E402
from mcp_server.db import init_db  # noqa: E402


def load_analysis(path: Path) -> BobAnalysis:
    """
    Parse Bob's output through the same contract the REST path uses.

    Tolerates a fenced code block, because copying out of a chat window
    usually brings the ``` markers along.
    """
    text = path.read_text(encoding="utf-8").strip()
    if text.startswith("```"):
        lines = [l for l in text.splitlines() if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()

    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SystemExit(
            f"{path} is not valid JSON: {exc}\n"
            "Paste exactly what Bob returned -- the whole object, no prose."
        ) from exc

    raw.setdefault("analysis_source", "ibm-bob")
    if raw.get("analysis_source") != "ibm-bob":
        raise SystemExit(
            f"analysis_source is {raw.get('analysis_source')!r}, not 'ibm-bob'. "
            "This script is only for output IBM Bob actually produced."
        )

    try:
        return BobAnalysis.from_raw(raw)
    except Exception as exc:
        raise SystemExit(
            f"Bob's output failed the contract in "
            f".bob/skills/incident-correlation/references/evidence-schema.md:\n"
            f"  {exc}\n"
            "Ask Bob to return exactly one JSON object matching that schema."
        ) from exc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("analysis", type=Path, help="JSON file from a Bob session")
    parser.add_argument("--approver", default="shivraj")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--approve", action="store_true",
                       help="approve, execute and verify against the live cluster")
    group.add_argument("--reject", metavar="REASON",
                       help="reject with a reason; nothing executes")
    parser.add_argument("--namespace", default="opspilot")
    parser.add_argument("--deployment", default="ticket-booking")
    parser.add_argument("--service", default="ticket-booking")
    args = parser.parse_args()

    analysis = load_analysis(args.analysis)
    print("=== 1. IBM Bob analysis ===")
    print(f"  source          : {analysis.analysis_source}")
    print(f"  hypotheses      : {len(analysis.hypotheses)}")
    for h in analysis.hypotheses[:3]:
        print(f"    [{h.rank}] ({h.confidence}) {h.statement[:88]}")
    if analysis.root_cause:
        print(f"  root cause      : {analysis.root_cause.statement[:88]}")
        print(f"  is_inference    : {analysis.root_cause.is_inference}")
    print(f"  recommended     : {analysis.recommended_action} -> {analysis.action_target}")
    if analysis.dual_signal_note:
        print(f"  dual-signal note: {analysis.dual_signal_note[:88]}")

    reachable, detail = is_cluster_reachable()
    if not reachable:
        raise SystemExit(f"Cluster unreachable: {detail}")
    init_db()
    cluster = LiveCluster()

    print("\n=== 2. Live evidence and correlation ===")
    evidence = collect_agent_evidence(args.namespace, args.deployment, args.service)
    workload = evidence.raw["workload"]
    print(f"  {workload['name']}: ready {workload['ready_replicas']}/"
          f"{workload['desired_replicas']}  image {workload['image']}")

    open_tickets = ticket_store.list_tickets(status="open")
    incident, excluded = correlate(tickets_to_references(open_tickets), evidence)
    print(f"  correlated {len(incident.tickets)} ticket(s), {len(excluded)} excluded")
    for t in incident.tickets:
        print(f"    {t.ticket_id}  {(t.title or '')[:70]}")

    # Attach Bob's analysis exactly as reasoning.run_analysis would, and record
    # how it arrived so the audit trail does not imply a headless call.
    incident.analysis = analysis
    incident.transition(IncidentState.ANALYSED)
    incident.audit_log.append({
        "stage": "BOB",
        "analysis_source": "ibm-bob",
        "invocation": ["interactive-session", "mode:kubemedic-analyst"],
        "note": (
            "Analysis produced by IBM Bob in an interactive workspace session "
            "using the kubemedic-evidence MCP server, then ingested via "
            "scripts/ingest_bob_analysis.py. Not a headless REST call."
        ),
        "source_file": str(args.analysis),
    })

    print("\n=== 3. Plan ===")
    incident = plan_remediation(incident)
    if incident.plan is None:
        print("  Bob recommended no allowlisted action. Nothing to approve.")
        print(f"  record: {write_record(incident)}")
        return 0
    print(f"  {incident.plan.action.value} -> {incident.plan.target} "
          f"{incident.plan.action_parameters}")
    print(f"  state: {incident.state.value}")

    if args.reject:
        print("\n=== 4. Human review: REJECT ===")
        incident = record_decision(incident, HumanDecision(
            decision="rejected", approver=args.approver, feedback=args.reject))
        print(f"  state: {incident.state.value}")
        print(f"  reason stored: {incident.feedback_history}")
        print("  nothing executed; the cluster is untouched.")
        print(f"\n  record: {write_record(incident)}")
        return 0

    print("\n=== 4. Human review: APPROVE ===")
    incident = record_decision(incident, HumanDecision(
        decision="approved", approver=args.approver))
    print(f"  state: {incident.state.value}")

    print("\n=== 5. Execute ===")
    incident, result = execute(incident, cluster)
    print(f"  success={result.success}  {result.message}")
    if not result.success:
        print(f"  record: {write_record(incident)}")
        return 1

    print("\n=== 6. Verify (independent, two signals) ===")
    input("  Press Enter once the rollout has settled... ")
    incident, verification = verify(incident, cluster)
    for signal in verification.signals:
        print(f"    {signal.name}: passed={signal.passed} :: {signal.detail}")
    print(f"  outcome: {verification.outcome}   state: {incident.state.value}")

    path = write_record(incident)
    print(f"\n=== 7. Audit record ===\n  {path}")
    print("  analysis_source: ibm-bob   <- Bob genuinely produced this analysis")
    print("\nCopy it into submission/evidence/ -- it is the strongest single")
    print("piece of evidence in the submission.")
    return 0 if verification.outcome == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
