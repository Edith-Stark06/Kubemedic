import sqlite3
import os
import json

DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "kubemedic.db"))

def db_path() -> str:
    """
    Where the ticket store lives. KUBEMEDIC_TICKET_DB wins so a container with a
    read-only root filesystem can point it at a mounted volume; otherwise the
    repository's data/ directory.
    """
    return os.getenv("KUBEMEDIC_TICKET_DB") or DB_PATH


def get_connection():
    path = db_path()
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    # A busy timeout: the watcher and the API can touch the file at once, and
    # SQLite's default is to fail immediately with "database is locked".
    conn = sqlite3.connect(path, timeout=15)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tickets (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            status TEXT NOT NULL,
            severity TEXT NOT NULL,
            namespace TEXT NOT NULL,
            deployment TEXT NOT NULL,
            service TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            signals TEXT NOT NULL,
            related_ticket_ids TEXT NOT NULL,
            diagnosis TEXT,
            plan TEXT,
            resolution TEXT
        )
    ''')
    conn.commit()
    conn.close()
