"""
Shared test configuration.

The suite must never sleep waiting for a cluster it does not have. Every
Kubernetes interaction in tests is a fake that answers instantly, so the settle
window before verification is set to zero here -- otherwise a fake reporting
"not ready" would make the suite wait out the real 90s production window.

The behaviour under test is unchanged: wait_for_recovery still runs, still
takes one reading, and still reports whether the cluster had settled. Only the
patience is removed.
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _no_settle_wait(monkeypatch):
    monkeypatch.setenv("KUBEMEDIC_SETTLE_TIMEOUT_SECONDS", "0")
    monkeypatch.setenv("KUBEMEDIC_SETTLE_INTERVAL_SECONDS", "0")


@pytest.fixture(autouse=True)
def _isolated_state(monkeypatch, tmp_path):
    """
    Every test gets its own durable store, and none inherits the developer's
    authentication settings -- otherwise the suite would write into data/ and
    behave differently on a machine with KUBEMEDIC_REQUIRE_AUTH exported.
    """
    from agent import store

    monkeypatch.setenv("KUBEMEDIC_STATE_DB", str(tmp_path / "state.db"))
    monkeypatch.setenv("KUBEMEDIC_TICKET_DB", str(tmp_path / "tickets.db"))
    for name in ("KUBEMEDIC_REQUIRE_AUTH", "KUBEMEDIC_API_TOKENS",
                 "KUBEMEDIC_ENABLE_PRESENTER_TOOLS"):
        monkeypatch.delenv(name, raising=False)
    store.reset_store()
    yield
    store.reset_store()
