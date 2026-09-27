"""
Who may act, who is recorded as having acted, what survives a restart, and
whether the audit trail can be quietly edited.
"""
from __future__ import annotations

import sqlite3
import threading

import pytest

from agent import api, auth, store
from agent.store import IncidentStore
from tests.test_api import _create, client, cluster  # noqa: F401  (fixtures)

APPROVER = "alice-token-0123456789"
VIEWER = "victor-token-0123456789"
ADMIN = "root-token-0123456789"


@pytest.fixture
def authed(monkeypatch):
    monkeypatch.setenv("KUBEMEDIC_REQUIRE_AUTH", "true")
    monkeypatch.setenv(
        "KUBEMEDIC_API_TOKENS",
        f"alice:approver:{APPROVER},victor:viewer:{VIEWER},root:admin:{ADMIN}",
    )


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


# -- authentication -----------------------------------------------------------

class TestAuthentication:
    def test_liveness_needs_no_token(self, client, authed):  # noqa: F811
        assert client.get("/api/health").status_code == 200

    def test_no_token_is_401(self, client, authed):  # noqa: F811
        r = client.get("/api/incidents")
        assert r.status_code == 401
        assert r.headers["www-authenticate"] == "Bearer"

    def test_wrong_token_is_401(self, client, authed):  # noqa: F811
        r = client.get("/api/incidents", headers=bearer("nope"))
        assert r.status_code == 401
        assert r.json()["detail"]["error"] == "invalid_token"

    def test_wrong_scheme_is_401(self, client, authed):  # noqa: F811
        r = client.get("/api/incidents", headers={"Authorization": f"Basic {VIEWER}"})
        assert r.status_code == 401

    def test_auth_required_with_no_tokens_fails_closed(self, client, monkeypatch):  # noqa: F811
        monkeypatch.setenv("KUBEMEDIC_REQUIRE_AUTH", "true")
        monkeypatch.delenv("KUBEMEDIC_API_TOKENS", raising=False)
        r = client.get("/api/incidents", headers=bearer("anything"))
        assert r.status_code == 503
        assert r.json()["detail"]["error"] == "auth_misconfigured"

    def test_malformed_entries_are_ignored_not_half_accepted(self, monkeypatch):
        monkeypatch.setenv(
            "KUBEMEDIC_API_TOKENS",
            "ok:viewer:goodtoken,broken,x:superuser:tok,:viewer:tok,y:viewer:",
        )
        tokens = auth.load_tokens()
        assert [(t, p.identity) for t, p in tokens] == [("goodtoken", "ok")]

    def test_development_mode_needs_no_token(self, client):  # noqa: F811
        assert client.get("/api/incidents").status_code == 200
        assert client.get("/api/limits").json()["auth"]["auth_required"] is False

    def test_limits_reports_auth_without_leaking_tokens(self, client, authed):  # noqa: F811
        body = client.get("/api/limits", headers=bearer(VIEWER)).text
        assert VIEWER not in body and APPROVER not in body and ADMIN not in body


# -- roles ------------------------------------------------------------------

class TestRoles:
    def test_viewer_can_read_but_not_act(self, client, authed):  # noqa: F811
        assert client.get("/api/incidents", headers=bearer(VIEWER)).status_code == 200
        r = client.post("/api/incidents", json={}, headers=bearer(VIEWER))
        assert r.status_code == 403
        assert r.json()["detail"]["error"] == "forbidden"

    def test_approver_can_open_review_and_execute(self, client, authed):  # noqa: F811
        h = bearer(APPROVER)
        incident_id = client.post("/api/incidents", json={}, headers=h).json()["incident_id"]
        assert client.post(
            f"/api/incidents/{incident_id}/review",
            json={"decision": "APPROVED"}, headers=h,
        ).status_code == 200
        assert client.post(
            f"/api/incidents/{incident_id}/execute", headers=h
        ).status_code == 200

    def test_viewer_cannot_approve_or_execute(self, client, authed):  # noqa: F811
        incident_id = client.post(
            "/api/incidents", json={}, headers=bearer(APPROVER)
        ).json()["incident_id"]
        assert client.post(
            f"/api/incidents/{incident_id}/review",
            json={"decision": "APPROVED"}, headers=bearer(VIEWER),
        ).status_code == 403
        assert client.post(
            f"/api/incidents/{incident_id}/execute", headers=bearer(VIEWER)
        ).status_code == 403

    def test_approver_cannot_use_presenter_tools(self, client, authed):  # noqa: F811
        for path in ("/api/live/inject", "/api/demo/start", "/api/live/reset"):
            assert client.post(path, headers=bearer(APPROVER)).status_code == 403

    def test_presenter_tools_are_absent_in_production_even_for_admin(self, client, authed):  # noqa: F811
        r = client.post("/api/live/inject", headers=bearer(ADMIN))
        assert r.status_code == 404

    def test_engine_switch_is_presenter_tooling_too(self, client, authed):  # noqa: F811
        r = client.post("/api/provider/select", json={"provider": "gemini"},
                        headers=bearer(APPROVER))
        assert r.status_code == 403

    def test_presenter_tools_can_be_enabled_explicitly(self, client, authed, monkeypatch):  # noqa: F811
        monkeypatch.setenv("KUBEMEDIC_ENABLE_PRESENTER_TOOLS", "true")
        assert auth.presenter_tools_enabled() is True
        r = client.post("/api/provider/select", json={"provider": "nonsense"},
                        headers=bearer(ADMIN))
        assert r.status_code == 400          # reached the handler


# -- who is recorded ----------------------------------------------------------

class TestAccountability:
    def test_approver_is_the_token_identity_not_the_body(self, client, authed):  # noqa: F811
        h = bearer(APPROVER)
        incident_id = client.post("/api/incidents", json={}, headers=h).json()["incident_id"]
        client.post(
            f"/api/incidents/{incident_id}/review",
            json={"decision": "APPROVED", "approver": "the-cto"}, headers=h,
        )
        decision = [
            e for e in client.get(f"/api/incidents/{incident_id}", headers=h)
            .json()["audit_log"] if e.get("step") == "human_decision"
        ][0]
        assert decision["approver"] == "alice"

    def test_execution_is_attributed(self, client, authed):  # noqa: F811
        h = bearer(APPROVER)
        incident_id = client.post("/api/incidents", json={}, headers=h).json()["incident_id"]
        client.post(f"/api/incidents/{incident_id}/review",
                    json={"decision": "APPROVED"}, headers=h)
        client.post(f"/api/incidents/{incident_id}/execute", headers=h)
        log = client.get(f"/api/incidents/{incident_id}", headers=h).json()["audit_log"]
        assert [e["by"] for e in log if e.get("step") == "execute_requested"] == ["alice"]
        assert [e["by"] for e in log if e.get("step") == "incident_opened"] == ["alice"]

    def test_development_mode_still_honours_the_body_approver(self, client):  # noqa: F811
        incident_id = _create(client)
        client.post(f"/api/incidents/{incident_id}/review",
                    json={"decision": "APPROVED", "approver": "bench-tester"})
        log = client.get(f"/api/incidents/{incident_id}").json()["audit_log"]
        assert [e["approver"] for e in log if e.get("step") == "human_decision"] == ["bench-tester"]


# -- persistence --------------------------------------------------------------

class TestPersistence:
    def test_incident_survives_a_restart(self, client):  # noqa: F811
        incident_id = _create(client)
        client.post(f"/api/incidents/{incident_id}/review",
                    json={"decision": "REJECTED", "feedback": "roll back instead"})
        api._INCIDENTS.clear()                       # a fresh process

        body = client.get(f"/api/incidents/{incident_id}").json()
        assert body["state"] == "FEEDBACK_RECORDED"
        assert body["feedback_history"] == ["roll back instead"]

    def test_listing_includes_stored_incidents_after_a_restart(self, client):  # noqa: F811
        incident_id = _create(client)
        api._INCIDENTS.clear()
        ids = [i["incident_id"] for i in client.get("/api/incidents").json()]
        assert incident_id in ids

    def test_a_rejection_leaves_a_durable_trace(self, client):  # noqa: F811
        """The decisions the product is about must not depend on an execution."""
        incident_id = _create(client)
        client.post(f"/api/incidents/{incident_id}/review",
                    json={"decision": "REJECTED", "feedback": "no"})
        steps = [e["event"].get("step") for e in
                 client.get(f"/api/incidents/{incident_id}/events").json()["events"]]
        assert "human_decision" in steps and "rejection_recorded" in steps

    def test_a_pending_incident_can_still_be_decided_after_a_restart(self, client):  # noqa: F811
        incident_id = _create(client)
        api._INCIDENTS.clear()
        r = client.post(f"/api/incidents/{incident_id}/review",
                        json={"decision": "APPROVED"})
        assert r.status_code == 200 and r.json()["state"] == "APPROVED"

    def test_persistence_failure_is_a_503_not_a_silent_loss(self, client, monkeypatch):  # noqa: F811
        class Broken:
            def save(self, incident):
                raise sqlite3.OperationalError("disk full")

        monkeypatch.setattr(api, "get_store", lambda: Broken())
        r = client.post("/api/incidents", json={})
        assert r.status_code == 503
        assert r.json()["detail"]["error"] == "persistence_failed"


# -- concurrent execution -----------------------------------------------------

class TestExecutionLock:
    def test_a_second_concurrent_execute_is_refused(self, client, cluster):  # noqa: F811
        incident_id = _create(client)
        client.post(f"/api/incidents/{incident_id}/review",
                    json={"decision": "APPROVED"})

        api._exec_lock(incident_id).acquire()
        try:
            r = client.post(f"/api/incidents/{incident_id}/execute")
        finally:
            api._exec_lock(incident_id).release()

        assert r.status_code == 409
        assert r.json()["detail"]["error"] == "execution_in_progress"
        assert cluster.calls == []

    def test_execution_happens_exactly_once_under_a_race(self, client, cluster):  # noqa: F811
        incident_id = _create(client)
        client.post(f"/api/incidents/{incident_id}/review",
                    json={"decision": "APPROVED"})

        codes: list[int] = []

        def go():
            codes.append(client.post(f"/api/incidents/{incident_id}/execute").status_code)

        threads = [threading.Thread(target=go) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len([c for c in cluster.calls if c[0] == "rollback"]) == 1
        assert set(codes) <= {200, 409}


# -- the audit chain ----------------------------------------------------------

class TestAuditChain:
    def test_chain_verifies_after_normal_use(self, client):  # noqa: F811
        incident_id = _create(client)
        client.post(f"/api/incidents/{incident_id}/review",
                    json={"decision": "APPROVED"})
        body = client.get("/api/audit/verify").json()
        assert body["intact"] is True and body["broken_at_seq"] is None
        assert len(body["head"]) == 64

    def test_editing_a_past_event_is_detected(self, client):  # noqa: F811
        incident_id = _create(client)
        client.post(f"/api/incidents/{incident_id}/review",
                    json={"decision": "APPROVED"})
        path = store.get_store().path
        conn = sqlite3.connect(path)
        conn.execute(
            "UPDATE audit_events SET event = replace(event, 'approved', 'rejected') "
            "WHERE event LIKE '%human_decision%'"
        )
        conn.commit()
        conn.close()

        body = client.get("/api/audit/verify").json()
        assert body["intact"] is False and body["broken_at_seq"] is not None

    def test_deleting_an_event_is_detected(self, tmp_path):
        s = IncidentStore(tmp_path / "chain.db")
        from tests.test_lifecycle import _analysed_incident

        inc = _analysed_incident("INC-C")
        inc.audit_log.extend([{"step": "a"}, {"step": "b"}, {"step": "c"}])
        s.save(inc)
        conn = sqlite3.connect(s.path)
        conn.execute("DELETE FROM audit_events WHERE idx = 1")
        conn.commit()
        conn.close()
        assert s.verify_chain()[0] is False

    def test_saving_twice_does_not_duplicate_events(self, tmp_path):
        from tests.test_lifecycle import _analysed_incident

        s = IncidentStore(tmp_path / "chain.db")
        inc = _analysed_incident("INC-D")
        inc.audit_log.append({"step": "one"})
        assert s.save(inc) == 1
        assert s.save(inc) == 0
        inc.audit_log.append({"step": "two"})
        assert s.save(inc) == 1
        assert [e["event"].get("step") for e in s.events("INC-D")] == ["one", "two"]
        assert s.verify_chain() == (True, None)

    def test_empty_chain_is_intact(self, tmp_path):
        s = IncidentStore(tmp_path / "empty.db")
        assert s.verify_chain() == (True, None)
        assert s.chain_head() == "0" * 64

    def test_the_chain_is_shared_across_incidents_by_design(self, tmp_path):
        """
        A security-focused Bob audit session proposed scoping prev_hash per
        incident_id, on the theory that a global chain lets events from
        different incidents be silently swapped. It does not: deleting one
        incident's event is caught even though a different incident's rows
        are never touched, because whichever row comes next in insertion
        order -- regardless of which incident it belongs to -- has a
        prev_hash pointing at the hash that no longer exists. Scoping the
        chain per incident, as proposed, would remove exactly this property:
        an attacker could then forge one incident's history in isolation.
        """
        from tests.test_lifecycle import _analysed_incident

        s = IncidentStore(tmp_path / "shared-chain.db")

        a = _analysed_incident("INC-SHARED-A")
        a.audit_log.extend([{"step": "a1"}, {"step": "a2"}])
        s.save(a)

        b = _analysed_incident("INC-SHARED-B")
        b.audit_log.append({"step": "b1"})
        s.save(b)

        a.audit_log.append({"step": "a3"})
        s.save(a)

        assert s.verify_chain() == (True, None)

        conn = sqlite3.connect(s.path)
        conn.execute(
            "DELETE FROM audit_events WHERE incident_id = ? AND idx = 1",
            ("INC-SHARED-A",),
        )
        conn.commit()
        conn.close()

        intact, broken_at = s.verify_chain()
        assert intact is False
        assert broken_at is not None


class TestInsecureBind:
    """
    main() used to print a warning and start anyway when bound to a
    non-loopback address with auth off -- flagged by a security audit as
    advisory rather than blocking. insecure_bind() is the pure policy check
    main() now refuses to start on.
    """

    def test_loopback_with_no_auth_is_fine(self):
        for host in ("127.0.0.1", "localhost", "::1"):
            assert api.insecure_bind(host, auth_is_required=False) is False

    def test_non_loopback_with_no_auth_is_refused(self):
        assert api.insecure_bind("0.0.0.0", auth_is_required=False) is True

    def test_non_loopback_is_fine_once_auth_is_required(self):
        assert api.insecure_bind("0.0.0.0", auth_is_required=True) is False
