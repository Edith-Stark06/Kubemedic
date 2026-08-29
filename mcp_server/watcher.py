"""
Anomaly watcher — turns observed cluster state into tickets.

WHY ONE TICKET PER SIGNAL
-------------------------
This used to join every anomaly it found into a single title and open one
ticket per polling burst. A real failure therefore produced exactly one ticket,
and correlating one ticket into one incident demonstrates nothing — which is
why the mocked dashboard had to fabricate three.

One genuine bad rollout really does produce several distinct complaints: the
rollout is stalled, a pod is not becoming ready, the endpoint is failing. Those
are three observations, from three sources, that a human would file separately.
Emitting them separately is both more honest and what makes the many-to-one
correlation in agent/correlation.py meaningful.

Deduplication is per signal kind, not per deployment, so a stalled rollout does
not suppress the ticket for a failing health check.

This module observes and reports. It does not diagnose: no ticket here says
what caused anything. That is Bob's job, downstream.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

from mcp_server import tickets
from mcp_server.evidence import (
    check_application_health,
    inspect_pods,
    inspect_workload,
)
from mcp_server.models import TicketSeverity, TicketStatus

logger = logging.getLogger(__name__)

# Signal kinds. The prefix goes in the ticket title so an already-open ticket
# for the same kind can be found again without a schema change.
ROLLOUT_STALLED = "Rollout stalled"
POD_NOT_READY = "Pod not ready"
POD_RESTARTING = "Pod restarting repeatedly"
HEALTH_FAILING = "Application health failing"

RESTART_THRESHOLD = 3
OPEN_STATUSES = (TicketStatus.open.value, TicketStatus.investigating.value)


@dataclass
class Anomaly:
    """One observation. Facts only — no cause, no recommendation."""
    kind: str
    detail: str
    severity: TicketSeverity
    signals: list[str] = field(default_factory=list)

    def title(self, deployment: str) -> str:
        return f"{self.kind}: {deployment} — {self.detail}"


class KubeWatcher:
    def __init__(
        self,
        namespace="opspilot",
        deployment="ticket-booking",
        service="ticket-booking",
        poll_interval=15,
    ):
        self.namespace = namespace
        self.deployment = deployment
        self.service = service
        self.poll_interval = poll_interval
        self._running = False
        self._task = None

    def start(self):
        if not self._running:
            self._running = True
            self._task = asyncio.create_task(self._loop())
            logger.info("Watcher started.")

    def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
        logger.info("Watcher stopped.")

    async def _loop(self):
        while self._running:
            try:
                # Evidence collection is blocking network I/O. Run it off the
                # event loop or every poll stalls the whole MCP server.
                await asyncio.to_thread(self.check_once)
            except Exception as e:
                logger.error(f"Error during watcher loop: {e}")
            await asyncio.sleep(self.poll_interval)

    # -- observation -------------------------------------------------------

    def detect_anomalies(self) -> list[Anomaly]:
        """
        Read the cluster and return every distinct anomaly observed.

        A failed read is logged and skipped, never guessed at: a missing signal
        is not evidence of health.
        """
        anomalies: list[Anomaly] = []

        try:
            workload = inspect_workload(self.namespace, self.deployment)
            if not workload.rollout_complete:
                anomalies.append(Anomaly(
                    kind=ROLLOUT_STALLED,
                    detail=(
                        f"{workload.ready_replicas}/{workload.desired_replicas} "
                        "replicas ready"
                    ),
                    severity=TicketSeverity.high,
                    signals=[
                        f"desired={workload.desired_replicas}",
                        f"ready={workload.ready_replicas}",
                        f"updated={workload.updated_replicas}",
                        f"unavailable={workload.unavailable_replicas}",
                        f"image={workload.image}",
                        f"revision={workload.revision}",
                    ],
                ))
        except Exception as e:
            logger.warning(f"Failed to inspect workload: {e}")

        try:
            for pod in inspect_pods(self.namespace, self.deployment):
                if not pod.ready and not pod.terminating:
                    anomalies.append(Anomaly(
                        kind=POD_NOT_READY,
                        detail=f"{pod.name} is not ready",
                        severity=TicketSeverity.high,
                        signals=[
                            f"pod={pod.name}",
                            f"phase={pod.phase}",
                            f"image={pod.image}",
                            f"restarts={pod.restarts}",
                            f"reason={pod.reason}",
                        ],
                    ))
                if pod.restarts > RESTART_THRESHOLD:
                    anomalies.append(Anomaly(
                        kind=POD_RESTARTING,
                        detail=f"{pod.name} restarted {pod.restarts} times",
                        severity=TicketSeverity.high,
                        signals=[f"pod={pod.name}", f"restarts={pod.restarts}"],
                    ))
        except Exception as e:
            logger.warning(f"Failed to inspect pods: {e}")

        try:
            health = check_application_health(self.namespace, self.service)
            if not health.healthy:
                anomalies.append(Anomaly(
                    kind=HEALTH_FAILING,
                    detail=f"/health returned {health.status_code}",
                    severity=TicketSeverity.critical,
                    signals=[
                        f"status_code={health.status_code}",
                        f"error={health.error}",
                        f"body={(health.body or '')[:120]}",
                    ],
                ))
        except Exception as e:
            logger.warning(f"Failed to check app health: {e}")

        return anomalies

    # -- ticketing ---------------------------------------------------------

    def _open_kinds(self) -> set[str]:
        """Signal kinds that already have an unresolved ticket."""
        existing: set[str] = set()
        for status in OPEN_STATUSES:
            for ticket in tickets.list_tickets(status=status):
                if ticket.deployment != self.deployment:
                    continue
                head = ticket.title.split(":", 1)[0].strip()
                if head:
                    existing.add(head)
        return existing

    def check_once(self) -> list[str]:
        """
        One polling pass. Returns the ids of tickets created.

        Deduplication is per signal kind: a stalled rollout that is already
        ticketed will not be filed again, but it also will not suppress a new
        ticket for a failing health check.
        """
        anomalies = self.detect_anomalies()
        if not anomalies:
            return []

        already_open = self._open_kinds()
        created: list[str] = []
        seen_this_pass: set[str] = set()

        for anomaly in anomalies:
            if anomaly.kind in already_open or anomaly.kind in seen_this_pass:
                logger.debug(
                    "Ticket already open for %r on %s, skipping",
                    anomaly.kind, self.deployment,
                )
                continue
            ticket = tickets.create_ticket(
                title=anomaly.title(self.deployment),
                severity=anomaly.severity.value,
                namespace=self.namespace,
                deployment=self.deployment,
                service=self.service,
                signals=anomaly.signals,
            )
            created.append(ticket.id)
            seen_this_pass.add(anomaly.kind)
            logger.info("Created ticket %s: %s", ticket.id, ticket.title)

        return created

    # Retained for callers of the previous private name.
    _check_anomalies = check_once
