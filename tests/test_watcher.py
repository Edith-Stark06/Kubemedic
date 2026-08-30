"""
Watcher tests.

The behaviour that matters: one bad rollout produces several distinct tickets,
because that is what makes the many-to-one correlation downstream mean
anything. The old watcher joined every anomaly into one title and filed a
single ticket, so a real run correlated one ticket into one incident.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from mcp_server import db as db_module
from mcp_server import tickets
from mcp_server.watcher import (
    HEALTH_FAILING,
    KIND_TAG,
    POD_NOT_READY,
    POD_RESTARTING,
    ROLLOUT_STALLED,
    KubeWatcher,
)


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "DB_PATH", str(tmp_path / "watcher.db"))
    db_module.init_db()
    yield


def _workload(ready=0, desired=2, complete=False):
    return SimpleNamespace(
        rollout_complete=complete, ready_replicas=ready, desired_replicas=desired,
        updated_replicas=desired, unavailable_replicas=desired - ready,
        image="ticketbooking:1.1", revision="31",
    )


def _pod(name="ticket-booking-abc", ready=False, restarts=0, terminating=False):
    return SimpleNamespace(
        name=name, ready=ready, restarts=restarts, terminating=terminating,
        phase="Running", image="ticketbooking:1.1", reason=None,
    )


def _health(healthy=False, code=503):
    return SimpleNamespace(healthy=healthy, status_code=code, error=None, body="{}")


def _cluster(monkeypatch, workload=None, pods=None, health=None):
    monkeypatch.setattr(
        "mcp_server.watcher.inspect_workload",
        lambda *a, **kw: workload if workload is not None else _workload(2, 2, True),
    )
    monkeypatch.setattr(
        "mcp_server.watcher.inspect_pods", lambda *a, **kw: pods if pods is not None else []
    )
    monkeypatch.setattr(
        "mcp_server.watcher.check_application_health",
        lambda *a, **kw: health if health is not None else _health(True, 200),
    )


@pytest.fixture
def watcher():
    return KubeWatcher()


class TestHealthyClusterIsQuiet:
    def test_no_tickets_when_everything_is_fine(self, watcher, monkeypatch):
        _cluster(monkeypatch)
        assert watcher.check_once() == []
        assert tickets.list_tickets() == []


class TestOneTicketPerSignal:
    def test_a_bad_rollout_files_three_distinct_tickets(self, watcher, monkeypatch):
        """
        The many-to-one demo depends on this: three real observations from
        three sources, not one ticket with three sentences in the title.
        """
        _cluster(
            monkeypatch,
            workload=_workload(0, 2, False),
            pods=[_pod()],
            health=_health(),
        )
        created = watcher.check_once()
        assert len(created) == 3

        kinds = {t.title.split(":", 1)[0] for t in tickets.list_tickets()}
        assert kinds == {ROLLOUT_STALLED, POD_NOT_READY, HEALTH_FAILING}

    def test_each_ticket_carries_its_own_signals(self, watcher, monkeypatch):
        _cluster(
            monkeypatch, workload=_workload(0, 2, False), pods=[_pod()], health=_health()
        )
        watcher.check_once()
        by_kind = {
            t.title.split(":", 1)[0]: t.signals for t in tickets.list_tickets()
        }
        assert any("desired=2" in s for s in by_kind[ROLLOUT_STALLED])
        assert any("status_code=503" in s for s in by_kind[HEALTH_FAILING])

    def test_restart_threshold(self, watcher, monkeypatch):
        _cluster(
            monkeypatch,
            workload=_workload(2, 2, True),
            pods=[_pod(ready=True, restarts=9)],
        )
        watcher.check_once()
        kinds = {t.title.split(":", 1)[0] for t in tickets.list_tickets()}
        assert POD_RESTARTING in kinds

    def test_terminating_pod_is_not_reported_as_not_ready(self, watcher, monkeypatch):
        """A pod draining after a rollback is expected, not an anomaly."""
        _cluster(
            monkeypatch,
            workload=_workload(2, 2, True),
            pods=[_pod(ready=False, terminating=True)],
        )
        assert watcher.check_once() == []

    def test_health_failure_alone_files_one_ticket(self, watcher, monkeypatch):
        _cluster(monkeypatch, workload=_workload(2, 2, True), health=_health())
        assert len(watcher.check_once()) == 1


class TestDeduplication:
    def test_same_signal_is_not_filed_twice(self, watcher, monkeypatch):
        _cluster(
            monkeypatch, workload=_workload(0, 2, False), pods=[_pod()], health=_health()
        )
        first = watcher.check_once()
        second = watcher.check_once()
        assert len(first) == 3
        assert second == [], "the watcher re-filed tickets that were already open"
        assert len(tickets.list_tickets()) == 3

    def test_a_new_signal_is_filed_even_when_another_is_open(
        self, watcher, monkeypatch
    ):
        """
        Per-kind dedup is the point: a stalled rollout must not suppress the
        ticket for a health check that starts failing afterwards.
        """
        _cluster(monkeypatch, workload=_workload(0, 2, False))
        assert len(watcher.check_once()) == 1

        _cluster(monkeypatch, workload=_workload(0, 2, False), health=_health())
        assert len(watcher.check_once()) == 1
        assert len(tickets.list_tickets()) == 2

    def test_resolved_tickets_do_not_suppress_new_ones(self, watcher, monkeypatch):
        _cluster(monkeypatch, workload=_workload(0, 2, False))
        created = watcher.check_once()
        tickets.update_ticket(created[0], status="resolved")
        assert len(watcher.check_once()) == 1

    def test_dedup_is_scoped_to_this_deployment(self, watcher, monkeypatch):
        tickets.create_ticket(
            title=f"{ROLLOUT_STALLED}: other-service — 0/2 replicas ready",
            severity="high", namespace="opspilot", deployment="other-service",
            service="other-service", signals=[],
        )
        _cluster(monkeypatch, workload=_workload(0, 2, False))
        assert len(watcher.check_once()) == 1


class TestFailedReadsDoNotInventHealth:
    def test_a_failed_workload_read_is_skipped_not_guessed(self, watcher, monkeypatch):
        def boom(*a, **kw):
            raise RuntimeError("API server unreachable")

        monkeypatch.setattr("mcp_server.watcher.inspect_workload", boom)
        monkeypatch.setattr("mcp_server.watcher.inspect_pods", lambda *a, **kw: [])
        monkeypatch.setattr(
            "mcp_server.watcher.check_application_health",
            lambda *a, **kw: _health(True, 200),
        )
        # No exception, and no ticket claiming health it could not observe.
        assert watcher.check_once() == []

    def test_other_signals_still_reported_when_one_read_fails(
        self, watcher, monkeypatch
    ):
        def boom(*a, **kw):
            raise RuntimeError("pods unreadable")

        monkeypatch.setattr(
            "mcp_server.watcher.inspect_workload", lambda *a, **kw: _workload(0, 2, False)
        )
        monkeypatch.setattr("mcp_server.watcher.inspect_pods", boom)
        monkeypatch.setattr(
            "mcp_server.watcher.check_application_health", lambda *a, **kw: _health()
        )
        assert len(watcher.check_once()) == 2


class TestTicketsAreObservationsNotDiagnoses:
    def test_no_ticket_claims_a_cause_or_a_fix(self, watcher, monkeypatch):
        """
        The watcher reports what it saw. Cause and remediation belong to Bob,
        downstream, behind the approval gate.
        """
        _cluster(
            monkeypatch, workload=_workload(0, 2, False), pods=[_pod()], health=_health()
        )
        watcher.check_once()
        banned = ("caused by", "root cause", "rollback", "you should", "fix by")
        for ticket in tickets.list_tickets():
            lowered = ticket.title.lower()
            for phrase in banned:
                assert phrase not in lowered, f"{ticket.title!r} diagnoses"


class TestDedupIsDataDrivenNotTitleParsing:
    """
    Dedup used to re-derive the anomaly kind by splitting the ticket title on
    ':'. That holds until a deployment name or a detail string contains a
    colon -- then dedup silently stops matching and the watcher re-files the
    same anomaly on every poll. The kind is now carried in the signals.
    """

    def test_kind_is_recorded_in_signals(self, watcher, monkeypatch):
        _cluster(monkeypatch, workload=_workload(0, 2, False))
        watcher.check_once()
        signals = tickets.list_tickets(status="open")[0].signals
        assert any(s.startswith(KIND_TAG) for s in signals)

    def test_dedup_survives_a_colon_in_the_deployment_name(self, monkeypatch):
        awkward = KubeWatcher(deployment="ticket-booking:eu-west")
        _cluster(monkeypatch, workload=_workload(0, 2, False))
        first = awkward.check_once()
        second = awkward.check_once()
        assert len(first) == 1
        assert second == [], "a colon in the name broke deduplication"

    def test_old_untagged_tickets_still_deduplicate(self, watcher, monkeypatch):
        """An upgrade must not re-file every anomaly that is already open."""
        tickets.create_ticket(
            title=f"{ROLLOUT_STALLED}: ticket-booking — 0/2 replicas ready",
            severity="high", namespace="opspilot", deployment="ticket-booking",
            service="ticket-booking", signals=["desired=2"],   # no kind tag
        )
        _cluster(monkeypatch, workload=_workload(0, 2, False))
        assert watcher.check_once() == []


class TestPassIsExplainable:
    """
    A bare "0 filed" is indistinguishable from a broken watcher. One dry run
    reported zero while tickets existed, and the absence of any explanation is
    what made it expensive to investigate.
    """

    def test_created_ids_match_the_tickets_actually_filed(self, watcher, monkeypatch):
        _cluster(
            monkeypatch, workload=_workload(0, 2, False), pods=[_pod()], health=_health()
        )
        before = {t.id for t in tickets.list_tickets(status="open")}
        created = watcher.check_once()
        after = {t.id for t in tickets.list_tickets(status="open")}
        assert set(created) == after - before, (
            "the returned ids must be exactly the tickets that were filed"
        )

    def test_last_pass_explains_a_zero(self, watcher, monkeypatch):
        _cluster(monkeypatch, workload=_workload(0, 2, False))
        watcher.check_once()
        watcher.check_once()
        assert watcher.last_pass["created"] == []
        assert watcher.last_pass["skipped"] == [ROLLOUT_STALLED]
        assert watcher.last_pass["observed"] == [ROLLOUT_STALLED]

    def test_last_pass_records_a_healthy_cluster(self, watcher, monkeypatch):
        _cluster(monkeypatch)
        assert watcher.check_once() == []
