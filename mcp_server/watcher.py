import asyncio
import logging
from mcp_server.evidence import inspect_workload, inspect_pods, check_application_health
from mcp_server import tickets
from mcp_server.models import TicketStatus, TicketSeverity

logger = logging.getLogger(__name__)

class KubeWatcher:
    def __init__(self, namespace="opspilot", deployment="ticket-booking", service="ticket-booking", poll_interval=15):
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
                self._check_anomalies()
            except Exception as e:
                logger.error(f"Error during watcher loop: {e}")
            await asyncio.sleep(self.poll_interval)

    def _check_anomalies(self):
        # Prevent duplicate open tickets
        open_tickets = tickets.list_tickets(status=TicketStatus.open.value)
        inv_tickets = tickets.list_tickets(status=TicketStatus.investigating.value)
        active_tickets = [t for t in open_tickets + inv_tickets if t.deployment == self.deployment]
        
        if active_tickets:
            logger.debug(f"Active ticket exists for {self.deployment}, skipping anomaly creation.")
            return

        anomalies = []
        severity = TicketSeverity.medium
        signals = []
        
        # 1. Rollout not complete
        try:
            workload = inspect_workload(self.namespace, self.deployment)
            if not workload.rollout_complete:
                anomalies.append("Rollout not complete")
                severity = TicketSeverity.high
                signals.append(f"desired: {workload.desired_replicas}, ready: {workload.ready_replicas}, updated: {workload.updated_replicas}")
        except Exception as e:
            logger.warning(f"Failed to inspect workload: {e}")

        # 2. Any pod NotReady & 4. Pod restart count > 3
        try:
            pods = inspect_pods(self.namespace, self.deployment)
            for p in pods:
                if not p.ready:
                    anomalies.append(f"Pod {p.name} is NotReady")
                    severity = TicketSeverity.high if severity != TicketSeverity.critical else severity
                if p.restarts > 3:
                    anomalies.append(f"Pod {p.name} restart count > 3")
                    signals.append(f"Pod {p.name} restarts: {p.restarts}")
        except Exception as e:
            logger.warning(f"Failed to inspect pods: {e}")

        # 3. App health != 200
        try:
            health = check_application_health(self.namespace, self.service)
            if not health.healthy:
                anomalies.append(f"App health check failed: {health.status_code}")
                severity = TicketSeverity.critical
                signals.append(f"Health error: {health.error} / body: {health.body}")
        except Exception as e:
            logger.warning(f"Failed to check app health: {e}")

        if anomalies:
            title = f"Anomaly detected in {self.deployment}: {', '.join(anomalies)}"
            tickets.create_ticket(
                title=title,
                severity=severity.value,
                namespace=self.namespace,
                deployment=self.deployment,
                service=self.service,
                signals=signals
            )
            logger.info(f"Created ticket for anomalies: {anomalies}")
