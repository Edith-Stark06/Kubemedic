"""
The settle window before verification.

Found by a live dry run, not by the suite: POST /execute verified immediately
after the rollback, before Kubernetes had replaced the pods, and reported
VERIFICATION_FAILED on a remediation that had actually worked. The end-to-end
harness never caught it because scripts/validate.sh waits explicitly before
verifying; the API did not.

The danger in the fix is worse than the bug: a settle window that keeps waiting
until things look good would turn verification into a machine for producing
PASS. So these tests assert the window is bounded, that an expired window
reports honestly, and that verify() still gets to reach its own verdict.
"""
from __future__ import annotations

import pytest

from agent.verification import wait_for_recovery


class Reader:
    """Reports not-ready for the first `not_ready_for` calls, then ready."""

    def __init__(self, not_ready_for=0, raises=None):
        self.calls = 0
        self.not_ready_for = not_ready_for
        self.raises = raises

    def get_workload_status(self, name, namespace):
        self.calls += 1
        if self.raises:
            raise self.raises
        ready = self.calls > self.not_ready_for
        return {
            "ready": ready,
            "updated_replicas": 2 if ready else 1,
            "desired_replicas": 2,
        }

    def get_application_health(self, name, namespace):
        return {"status_code": 200, "healthy": True}


class TestSettles:
    def test_returns_immediately_when_already_healthy(self):
        reader = Reader()
        settled, detail = wait_for_recovery(reader, "ticket-booking", "opspilot")
        assert settled
        assert reader.calls == 1
        assert "settled" in detail

    def test_waits_then_settles(self):
        reader = Reader(not_ready_for=2)
        settled, detail = wait_for_recovery(
            reader, "ticket-booking", "opspilot", timeout_s=5, interval_s=0
        )
        assert settled
        assert reader.calls == 3
        assert "3 checks" in detail


class TestDoesNotManufacturePass:
    def test_expired_window_reports_honestly(self):
        """
        A window that never gives up would turn verification into a machine for
        producing PASS. It must be bounded and must say so.
        """
        reader = Reader(not_ready_for=999)
        settled, detail = wait_for_recovery(
            reader, "ticket-booking", "opspilot", timeout_s=0, interval_s=0
        )
        assert settled is False
        assert "did not settle" in detail
        assert "ready=False" in detail

    def test_settling_is_not_a_verdict(self):
        """
        wait_for_recovery only reports whether the cluster converged. verify()
        still reads both signals and reaches its own conclusion -- a settled
        rollout with a failing health endpoint must still fail.
        """
        settled, _ = wait_for_recovery(
            Reader(), "ticket-booking", "opspilot", timeout_s=0
        )
        assert settled is True
        # No incident state was changed by settling; nothing was decided.

    def test_a_read_failure_is_not_a_verdict_either(self):
        """
        If the reader errors while settling, that is not FAIL -- verify() makes
        the call, and an error there becomes INCONCLUSIVE.
        """
        reader = Reader(raises=RuntimeError("API server unreachable"))
        settled, detail = wait_for_recovery(
            reader, "ticket-booking", "opspilot", timeout_s=0, interval_s=0
        )
        assert settled is False
        assert "read failed" in detail

    def test_zero_timeout_still_takes_one_reading(self):
        """Even with no patience, the cluster is read once rather than assumed."""
        reader = Reader(not_ready_for=999)
        wait_for_recovery(reader, "ticket-booking", "opspilot", timeout_s=0)
        assert reader.calls == 1


class TestConfiguration:
    def test_window_is_read_at_call_time(self, monkeypatch):
        """
        Import-time configuration is what made this un-testable in the first
        place: the suite inherited a 90 second wait it could not shorten.
        """
        monkeypatch.setenv("KUBEMEDIC_SETTLE_TIMEOUT_SECONDS", "0")
        monkeypatch.setenv("KUBEMEDIC_SETTLE_INTERVAL_SECONDS", "0")
        reader = Reader(not_ready_for=999)
        settled, _ = wait_for_recovery(reader, "ticket-booking", "opspilot")
        assert settled is False
        assert reader.calls == 1
