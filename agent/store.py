"""
Durable incident state and a tamper-evident audit chain.

WHY THIS EXISTS
---------------
Incidents lived in one process's memory, so a restart lost every pending
approval, and the audit record was written only when something executed -- the
rejections, the unavailable analyses and the still-pending incidents, which are
exactly the human decisions the product is about, left no trace.

WHAT IT STORES
--------------
incidents     the current state of each incident, as JSON.
audit_events  every entry of every incident's audit log, append-only, in a hash
              chain: each row's hash covers the previous row's hash and its own
              content. Editing or deleting a past row breaks every hash after it,
              and `verify_chain()` says where.

A hash chain is tamper-EVIDENT, not tamper-proof: someone with write access to
the database can rewrite the whole chain. For that, ship the head hash
(`chain_head()`) somewhere the database's writer cannot reach.

SQLite is the right size for one process on one node. It is a deliberate seam:
the same interface over Postgres is the production step.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from agent.models import Incident

GENESIS = "0" * 64

_SCHEMA = """
CREATE TABLE IF NOT EXISTS incidents (
    incident_id TEXT PRIMARY KEY,
    state       TEXT NOT NULL,
    data        TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_events (
    seq         INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id TEXT NOT NULL,
    idx         INTEGER NOT NULL,
    recorded_at TEXT NOT NULL,
    event       TEXT NOT NULL,
    prev_hash   TEXT NOT NULL,
    hash        TEXT NOT NULL,
    UNIQUE (incident_id, idx)
);
"""


def _canonical(event: dict) -> str:
    return json.dumps(event, sort_keys=True, separators=(",", ":"), default=str)


def _digest(prev_hash: str, incident_id: str, idx: int, recorded_at: str, event: str) -> str:
    material = "\x1f".join([prev_hash, incident_id, str(idx), recorded_at, event])
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


class IncidentStore:
    def __init__(self, path: str | os.PathLike) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=15)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # -- incidents ---------------------------------------------------------

    def save(self, incident: Incident) -> int:
        """
        Persist the incident and append any audit-log entries not yet chained.
        Returns how many new audit events were recorded.
        """
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "INSERT INTO incidents (incident_id, state, data, updated_at) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT(incident_id) DO UPDATE SET state=excluded.state, "
                "data=excluded.data, updated_at=excluded.updated_at",
                (incident.incident_id, incident.state.value,
                 incident.model_dump_json(), now),
            )
            have = conn.execute(
                "SELECT COALESCE(MAX(idx) + 1, 0) FROM audit_events WHERE incident_id = ?",
                (incident.incident_id,),
            ).fetchone()[0]
            row = conn.execute(
                "SELECT hash FROM audit_events ORDER BY seq DESC LIMIT 1"
            ).fetchone()
            prev = row[0] if row else GENESIS

            added = 0
            for idx in range(have, len(incident.audit_log)):
                event = _canonical(incident.audit_log[idx])
                digest = _digest(prev, incident.incident_id, idx, now, event)
                conn.execute(
                    "INSERT INTO audit_events "
                    "(incident_id, idx, recorded_at, event, prev_hash, hash) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (incident.incident_id, idx, now, event, prev, digest),
                )
                prev = digest
                added += 1
            return added

    def get(self, incident_id: str) -> Incident | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT data FROM incidents WHERE incident_id = ?", (incident_id,)
            ).fetchone()
        return Incident.model_validate_json(row[0]) if row else None

    def list(self) -> list[Incident]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT data FROM incidents ORDER BY updated_at DESC"
            ).fetchall()
        return [Incident.model_validate_json(r[0]) for r in rows]

    # -- audit chain -------------------------------------------------------

    def events(self, incident_id: str) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT seq, idx, recorded_at, event, hash FROM audit_events "
                "WHERE incident_id = ? ORDER BY idx",
                (incident_id,),
            ).fetchall()
        return [
            {"seq": s, "idx": i, "recorded_at": t, "event": json.loads(e), "hash": h}
            for s, i, t, e, h in rows
        ]

    def chain_head(self) -> str:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT hash FROM audit_events ORDER BY seq DESC LIMIT 1"
            ).fetchone()
        return row[0] if row else GENESIS

    def verify_chain(self) -> tuple[bool, int | None]:
        """
        Recompute every hash from the start. Returns (True, None) when intact,
        otherwise (False, seq) for the first row that does not verify.
        """
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT seq, incident_id, idx, recorded_at, event, prev_hash, hash "
                "FROM audit_events ORDER BY seq"
            ).fetchall()
        prev = GENESIS
        for seq, incident_id, idx, recorded_at, event, prev_hash, digest in rows:
            if prev_hash != prev or _digest(prev, incident_id, idx, recorded_at, event) != digest:
                return False, seq
            prev = digest
        return True, None


_store: IncidentStore | None = None
_store_path: str | None = None
_store_lock = threading.Lock()


def state_path() -> str:
    return os.getenv("KUBEMEDIC_STATE_DB", "data/kubemedic-state.db")


def get_store() -> IncidentStore:
    """One store per configured path, created on first use."""
    global _store, _store_path
    path = state_path()
    with _store_lock:
        if _store is None or _store_path != path:
            _store, _store_path = IncidentStore(path), path
        return _store


def reset_store() -> None:
    """Test hook."""
    global _store, _store_path
    with _store_lock:
        _store, _store_path = None, None
