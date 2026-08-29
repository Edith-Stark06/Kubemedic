import sqlite3
import os
import json

DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "kubemedic.db"))

def get_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
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
