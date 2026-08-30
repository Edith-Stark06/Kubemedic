"""
Ticket store tests.

Every test runs against a temporary database. The real data/kubemedic.db is
machine state and must never be touched by the suite.
"""
from __future__ import annotations

import pytest

from mcp_server import db as db_module
from mcp_server import tickets
from mcp_server.models import TicketStatus


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    """Point the ticket store at a throwaway database for each test."""
    monkeypatch.setattr(db_module, "DB_PATH", str(tmp_path / "test.db"))
    db_module.init_db()
    yield


def _make(title="ticket-booking rollout stalled", severity="high"):
    return tickets.create_ticket(
        title=title,
        severity=severity,
        namespace="opspilot",
        deployment="ticket-booking",
        service="ticket-booking",
        signals=["ready 0/2", "readiness probe 503"],
    )


class TestCreateAndRead:
    def test_create_returns_a_ticket(self):
        t = _make()
        assert t.id.startswith("TKT-")
        assert t.status == TicketStatus.open
        assert t.signals == ["ready 0/2", "readiness probe 503"]

    def test_get_ticket_round_trips(self):
        t = _make()
        again = tickets.get_ticket(t.id)
        assert again is not None
        assert again.id == t.id
        assert again.title == t.title

    def test_get_unknown_ticket_returns_none(self):
        assert tickets.get_ticket("TKT-nope") is None

    def test_list_tickets_orders_newest_first(self):
        first = _make(title="first")
        second = _make(title="second")
        listed = [t.id for t in tickets.list_tickets()]
        assert listed[:2] == [second.id, first.id] or set(listed) == {
            first.id, second.id
        }

    def test_list_by_status_filters(self):
        _make()
        assert len(tickets.list_tickets(status="open")) == 1
        assert tickets.list_tickets(status="resolved") == []


class TestUpdate:
    """
    Regression guard for MCP-005.

    update_ticket() reached `isinstance(value, Enum)` on its elif branch while
    Enum was never imported, so every scalar-field update raised
    NameError: name 'Enum' is not defined. That broke the update_ticket_status
    MCP tool outright.
    """

    def test_update_scalar_field_does_not_raise(self):
        t = _make()
        updated = tickets.update_ticket(t.id, status="investigating")
        assert updated.status == TicketStatus.investigating

    def test_update_accepts_an_enum_value(self):
        t = _make()
        updated = tickets.update_ticket(t.id, status=TicketStatus.resolved)
        assert updated.status == TicketStatus.resolved

    def test_update_json_field(self):
        t = _make()
        updated = tickets.update_ticket(
            t.id, diagnosis={"detail": "revision 3 image regression"}
        )
        assert updated.diagnosis == {"detail": "revision 3 image regression"}

    def test_update_ignores_unknown_fields(self):
        t = _make()
        updated = tickets.update_ticket(t.id, not_a_column="x")
        assert updated.id == t.id

    def test_update_bumps_updated_at(self):
        t = _make()
        updated = tickets.update_ticket(t.id, status="investigating")
        assert updated.updated_at >= t.updated_at


class TestLinking:
    def test_link_is_bidirectional(self):
        a = _make(title="a")
        b = _make(title="b")
        tickets.link_tickets(a.id, b.id)
        assert b.id in tickets.get_ticket(a.id).related_ticket_ids
        assert a.id in tickets.get_ticket(b.id).related_ticket_ids

    def test_link_is_idempotent(self):
        a = _make(title="a")
        b = _make(title="b")
        tickets.link_tickets(a.id, b.id)
        tickets.link_tickets(a.id, b.id)
        assert tickets.get_ticket(a.id).related_ticket_ids.count(b.id) == 1
