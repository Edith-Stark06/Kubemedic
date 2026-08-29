"""
End-to-end validation against a live cluster.

Asserts the whole loop with hard checks and a non-zero exit on any failure:

    healthy -> inject -> observe -> correlate -> propose
            -> REJECT (reason required) -> revise
            -> APPROVE -> execute -> verify -> resolve -> reset

Every assertion reads the real cluster or the real store. Nothing here is
mocked, and nothing is asserted that was not observed.

IBM BOB
-------
If KUBEMEDIC_BOB_API_KEY and KUBEMEDIC_BOB_AGENT_ID are set, the plan comes
from Bob and the run asserts analysis_source == "ibm-bob".

If they are not, Bob is correctly unavailable and no plan is produced. Rather
than skipping the rest, the harness supplies an operator-specified rollback so
the approval gate, executor and verifier are still exercised end to end -- and
it labels that plan as operator-specified in the output and in the audit
record. It never claims Bob reasoned when Bob did not.

Usage:  python scripts/validate_incident.py [--skip-reset]
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from agent.adapters import collect_agent_evidence, previous_revision  # noqa: E402
from agent.audit import record_decision, write_record  # noqa: E402
from agent.correlation import correlate  # noqa: E402
from agent.executor import execute  # noqa: E402
from agent.k8s_client import LiveCluster, is_cluster_reachable  # noqa: E402
from agent.models import (  # noqa: E402
    AllowedAction,
    HumanDecision,
    Incident,
    IncidentState,
    RemediationPlan,
)
from agent.pipeline import plan_remediation, request_revision  # noqa: E402
from agent.reasoning import run_analysis  # noqa: E402
from agent.verification import verify  # noqa: E402
from mcp_server import tickets as ticket_store  # noqa: E402
from mcp_server.db import init_db  # noqa: E402
from mcp_server.watcher import KubeWatcher  # noqa: E402

NAMESPACE = os.getenv("KUBEMEDIC_NAMESPACE", "opspilot")
DEPLOYMENT = os.getenv("KUBEMEDIC_DEPLOYMENT", "ticket-booking")
SERVICE = os.getenv("KUBEMEDIC_SERVICE", "ticket-booking")
SCRIPTS = REPO / "scripts"

_failures: list[str] = []
_step = 0


def step(title: str) -> None:
    global _step
    _step += 1
    print(f"\n=== {_step}. {title} ===")


def check(label: str, condition: bool, detail: str = "") -> bool:
    mark = "PASS" if condition else "FAIL"
    print(f"  [{mark}] {label}" + (f" :: {detail}" if detail else ""))
    if not condition:
        _failures.append(label)
    return condition


def _bash() -> str:
    """
    Locate a bash that can see Windows paths.

    On Windows, PATH often resolves `bash` to WSL's bash.exe, which cannot open
    a C:/ path and exits 127 with a misleading "No such file or directory".
    validate.sh exports KUBEMEDIC_BASH so the shell that launched us is reused;
    otherwise fall back to Git Bash, then to whatever is on PATH.
    """
    override = os.getenv("KUBEMEDIC_BASH")
    if override and Path(override).is_file():
        return override
    for candidate in (
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files\Git\usr\bin\bash.exe",
    ):
        if Path(candidate).is_file():
            return candidate
    return "bash"


def run_script(name: str) -> None:
    # as_posix(): bash on Windows treats backslashes as escapes, so a native
    # path arrives mangled ("C:UsersshivrajDesktop...").
    subprocess.run([_bash(), (SCRIPTS / name).as_posix()], check=True)


def wait_for(predicate, timeout=120, interval=5, what="condition"):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    print(f"  ! timed out after {timeout}s waiting for {what}")
    return False


def workload():
    return collect_agent_evidence(NAMESPACE, DEPLOYMENT, SERVICE).raw["workload"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-reset", action="store_true",
                        help="leave the cluster in its final state")
    args = parser.parse_args()

    print("KubeMedic end-to-end validation")
    print(f"  namespace={NAMESPACE} deployment={DEPLOYMENT} service={SERVICE}")

    step("Preflight")
    reachable, detail = is_cluster_reachable()
    if not check("cluster reachable", reachable, detail):
        return 1
    init_db()
    cluster = LiveCluster()

    step("Baseline: restore and confirm healthy")
    run_script("reset_healthy.sh")
    wait_for(lambda: workload()["rollout_complete"], what="a healthy rollout")
    before = workload()
    check("rollout complete", before["rollout_complete"],
          f"{before['ready_replicas']}/{before['desired_replicas']} ready")
    check("serving the good image", before["image"].endswith(":1.0"), before["image"])

    for stale in ticket_store.list_tickets(status="open"):
        ticket_store.update_ticket(stale.id, status="closed")

    step("Inject the incident")
    run_script("inject_incident.sh")
    wait_for(lambda: not workload()["rollout_complete"], timeout=90,
             what="the rollout to stall")
    during = workload()
    check("rollout is stalled", not during["rollout_complete"],
          f"{during['ready_replicas']}/{during['desired_replicas']} ready")
    check("bad image is deployed", during["image"].endswith(":1.1"), during["image"])

    step("Observe: the watcher files tickets")
    created = KubeWatcher(NAMESPACE, DEPLOYMENT, SERVICE).check_once()
    check("at least one ticket filed", len(created) >= 1, f"{len(created)} created")
    for ticket_id in created:
        print(f"      {ticket_id}  {ticket_store.get_ticket(ticket_id).title}")
    check("re-polling files nothing new",
          KubeWatcher(NAMESPACE, DEPLOYMENT, SERVICE).check_once() == [],
          "deduplicated by signal kind")

    step("Correlate: many tickets, one incident")
    from agent.adapters import tickets_to_references

    evidence = collect_agent_evidence(NAMESPACE, DEPLOYMENT, SERVICE)
    open_tickets = ticket_store.list_tickets(status="open")
    incident, excluded = correlate(tickets_to_references(open_tickets), evidence)
    check("every open ticket joined the incident",
          len(incident.tickets) == len(open_tickets) and not excluded,
          f"{len(incident.tickets)} members, {len(excluded)} excluded")
    check("one master incident id", bool(incident.correlation.master_incident_id),
          incident.correlation.master_incident_id)

    step("Reason: ask IBM Bob")
    incident, analysis = run_analysis(incident)
    bob_available = incident.state != IncidentState.BOB_UNAVAILABLE
    if bob_available:
        check("Bob produced an analysis", analysis.analysis_source == "ibm-bob")
        incident = plan_remediation(incident)
        check("a plan was proposed", incident.plan is not None,
              incident.plan.action.value if incident.plan else "none")
    else:
        print("  [INFO] IBM Bob unavailable -- no credentials configured.")
        print("         The agent produced NO plan and NO diagnosis, which is")
        print("         correct: it reports the outage rather than inventing one.")
        check("no plan was fabricated", incident.plan is None)
        check("analysis is marked unavailable",
              analysis.analysis_source == "unavailable")

        target = previous_revision(evidence)
        if target is None:
            check("a previous revision exists to roll back to", False)
            return 1
        print(f"  [INFO] Supplying an OPERATOR-SPECIFIED rollback to revision "
              f"{target} so the gate, executor and verifier are still exercised.")
        incident.plan = RemediationPlan(
            action=AllowedAction.rollback_deployment,
            target=DEPLOYMENT,
            action_parameters={"to_revision": target},
            reason=(
                "Operator-specified rollback (IBM Bob unavailable). "
                "This plan was NOT produced by Bob."
            ),
        )
        incident.transition(IncidentState.PENDING_APPROVAL)

    step("Gate: execution is impossible before approval")
    try:
        execute(incident, cluster)
        check("unapproved execution refused", False, "IT WAS NOT REFUSED")
    except ValueError as exc:
        check("unapproved execution refused", True, str(exc))
    after_attempt = workload()
    check("cluster unchanged by the refused attempt",
          after_attempt["image"] == during["image"], after_attempt["image"])

    step("Human review: REJECT requires a reason")
    try:
        HumanDecision(decision="rejected", approver="validator", feedback="")
        check("rejection without a reason refused", False, "IT WAS ACCEPTED")
    except Exception:
        check("rejection without a reason refused", True)

    reason = "Confirm the rollout history names a healthy revision before acting."
    incident = record_decision(
        incident,
        HumanDecision(decision="rejected", approver="validator", feedback=reason),
    )
    check("incident recorded the rejection",
          incident.state == IncidentState.FEEDBACK_RECORDED, incident.state.value)
    check("the reason was stored", incident.feedback_history == [reason])
    rejected_state = workload()
    check("a rejected plan never reached the cluster",
          rejected_state["image"] == during["image"], rejected_state["image"])

    step("Revise: the reason goes back to Bob")
    if bob_available:
        incident = request_revision(incident)
        check("a revised plan was produced", incident.plan is not None)
        check("the revision is awaiting review",
              incident.state == IncidentState.PENDING_APPROVAL, incident.state.value)
    else:
        print("  [INFO] Bob unavailable, so no revision round-trip is possible.")
        print("         Re-proposing the operator-specified plan for approval.")
        incident.plan = RemediationPlan(
            action=AllowedAction.rollback_deployment,
            target=DEPLOYMENT,
            action_parameters={"to_revision": previous_revision(evidence)},
            reason=(
                "Operator-specified rollback (IBM Bob unavailable). "
                "This plan was NOT produced by Bob."
            ),
        )
        incident.human_decision = None
        incident.transition(IncidentState.ANALYSED)
        incident.transition(IncidentState.PENDING_APPROVAL)

    step("Human review: APPROVE")
    incident = record_decision(
        incident, HumanDecision(decision="approved", approver="validator")
    )
    check("incident approved", incident.state == IncidentState.APPROVED)

    step("Execute")
    incident, result = execute(incident, cluster)
    check("execution succeeded", result.success, result.message)
    check("the cluster reports the change",
          result.raw_response.get("action") == "rollback_deployment",
          str(result.raw_response))

    step("Verify: independent, two signals")
    wait_for(lambda: workload()["rollout_complete"], what="recovery")
    incident, verification = verify(incident, cluster)
    for signal in verification.signals:
        print(f"      {signal.name}: passed={signal.passed} :: {signal.detail}")
    check("verification passed", verification.outcome == "PASS", verification.outcome)
    check("both signals were checked", len(verification.signals) == 2)
    check("incident resolved", incident.state == IncidentState.RESOLVED,
          incident.state.value)

    recovered = workload()
    check("the good image is serving again", recovered["image"].endswith(":1.0"),
          recovered["image"])

    step("Audit record")
    path = write_record(incident)
    check("record written", Path(path).is_file(), str(path))
    from agent.models import IncidentRecord

    record = IncidentRecord.from_incident(incident)
    check("record states the analysis source",
          record.analysis_source in ("ibm-bob", "unavailable", "none"),
          record.analysis_source)
    check("record carries the rejection reason",
          record.feedback_history == [reason])
    check("record shows execution happened", record.executed is True)
    check("record shows verification passed", record.verification_outcome == "PASS")

    for ticket in ticket_store.list_tickets(status="open"):
        ticket_store.update_ticket(ticket.id, status="resolved")

    if not args.skip_reset:
        step("Reset")
        run_script("reset_healthy.sh")

    print("\n" + "=" * 62)
    if _failures:
        print(f"FAILED -- {len(_failures)} check(s) did not pass:")
        for failure in _failures:
            print(f"  - {failure}")
        return 1
    print("ALL CHECKS PASSED")
    if not bob_available:
        print("\nNOTE: IBM Bob was unavailable for this run. The reasoning stage")
        print("was NOT exercised; the plan was operator-specified and labelled")
        print("as such. Set KUBEMEDIC_BOB_API_KEY and KUBEMEDIC_BOB_AGENT_ID to")
        print("validate the full path including Bob.")
    print("=" * 62)
    return 0


if __name__ == "__main__":
    sys.exit(main())
