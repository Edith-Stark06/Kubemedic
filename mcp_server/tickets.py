import json
import logging
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from mcp_server.models import Ticket, TicketSeverity, TicketStatus
from mcp_server.db import get_connection

logger = logging.getLogger(__name__)

def _generate_ticket_id() -> str:
    now = datetime.now(timezone.utc)
    return f"TKT-{now.strftime('%Y%m%d-%H%M%S-%f')[:20]}"

def _row_to_ticket(row) -> Ticket:
    return Ticket(
        id=row["id"],
        title=row["title"],
        status=TicketStatus(row["status"]),
        severity=TicketSeverity(row["severity"]),
        namespace=row["namespace"],
        deployment=row["deployment"],
        service=row["service"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        signals=json.loads(row["signals"]),
        related_ticket_ids=json.loads(row["related_ticket_ids"]),
        diagnosis=json.loads(row["diagnosis"]) if row["diagnosis"] else None,
        plan=json.loads(row["plan"]) if row["plan"] else None,
        resolution=json.loads(row["resolution"]) if row["resolution"] else None
    )

def create_ticket(title: str, severity: str, namespace: str, deployment: str, service: str, signals: List[str]) -> Ticket:
    conn = get_connection()
    cursor = conn.cursor()
    now_str = datetime.now(timezone.utc).isoformat()
    ticket_id = _generate_ticket_id()
    
    cursor.execute('''
        INSERT INTO tickets (
            id, title, status, severity, namespace, deployment, service, 
            created_at, updated_at, signals, related_ticket_ids, 
            diagnosis, plan, resolution
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        ticket_id, title, TicketStatus.open.value, severity, namespace, deployment, service,
        now_str, now_str, json.dumps(signals), json.dumps([]),
        None, None, None
    ))
    conn.commit()
    conn.close()
    
    return get_ticket(ticket_id)

def get_ticket(ticket_id: str) -> Optional[Ticket]:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return _row_to_ticket(row)
    return None

def list_tickets(status: Optional[str] = None, limit: int = 50) -> List[Ticket]:
    conn = get_connection()
    cursor = conn.cursor()
    
    if status:
        cursor.execute("SELECT * FROM tickets WHERE status = ? ORDER BY created_at DESC LIMIT ?", (status, limit))
    else:
        cursor.execute("SELECT * FROM tickets ORDER BY created_at DESC LIMIT ?", (limit,))
        
    rows = cursor.fetchall()
    conn.close()
    
    return [_row_to_ticket(row) for row in rows]

def update_ticket(ticket_id: str, **fields) -> Ticket:
    conn = get_connection()
    cursor = conn.cursor()
    
    valid_fields = ["title", "status", "severity", "signals", "related_ticket_ids", "diagnosis", "plan", "resolution"]
    updates = []
    values = []
    
    for key, value in fields.items():
        if key in valid_fields:
            updates.append(f"{key} = ?")
            if isinstance(value, (list, dict)):
                values.append(json.dumps(value))
            elif isinstance(value, Enum):
                values.append(value.value)
            else:
                values.append(value)
                
    if updates:
        updates.append("updated_at = ?")
        values.append(datetime.now(timezone.utc).isoformat())
        values.append(ticket_id)
        
        query = f"UPDATE tickets SET {', '.join(updates)} WHERE id = ?"
        cursor.execute(query, tuple(values))
        conn.commit()
        
    conn.close()
    return get_ticket(ticket_id)

def link_tickets(ticket_id: str, related_id: str) -> None:
    t1 = get_ticket(ticket_id)
    t2 = get_ticket(related_id)
    if t1 and t2:
        if related_id not in t1.related_ticket_ids:
            new_related = t1.related_ticket_ids + [related_id]
            update_ticket(ticket_id, related_ticket_ids=new_related)
        if ticket_id not in t2.related_ticket_ids:
            new_related = t2.related_ticket_ids + [ticket_id]
            update_ticket(related_id, related_ticket_ids=new_related)
