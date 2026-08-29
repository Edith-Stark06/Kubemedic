"""
KubeMedic Demo Workload — ticket-booking app.

The app is the PATIENT, not the product. It needs to be believable,
not production-grade. In-memory storage. No auth, no database.

Endpoints
---------
GET  /            Landing page — confirms app is alive
GET  /health      Liveness — 200 while process is up; HONEST (500 when HEALTHY=false)
GET  /ready       Readiness — 200 only when can actually serve bookings
POST /book        Create booking, return BK-prefixed id
GET  /bookings    List bookings (verification readback)

Failure lever
-------------
Set env var HEALTHY=false to inject failure.
The /ready and /health endpoints return 500, simulating a broken revision.
The app keeps logging structured JSON so the MCP evidence collector has
real events to find.

Run
---
    cd workload
    pip install -r requirements.txt
    uvicorn main:app --reload --port 8001

Inject failure:
    HEALTHY=false uvicorn main:app --port 8001

Reset (restore health):
    uvicorn main:app --port 8001
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from pydantic import BaseModel

# ── Structured logging ─────────────────────────────────────────────────────

class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            **(record.__dict__.get("extra_fields", {})),
        })


_handler = logging.StreamHandler(sys.stdout)
_handler.setFormatter(_JsonFormatter())
logging.basicConfig(handlers=[_handler], level=logging.INFO, force=True)
log = logging.getLogger("ticket-booking")

# ── Configuration ──────────────────────────────────────────────────────────

HEALTHY = os.getenv("HEALTHY", "true").lower() not in ("false", "0", "no")
APP_VERSION = os.getenv("APP_VERSION", "1.0")

if not HEALTHY:
    log.error(
        "Starting in FAILED mode — HEALTHY=false. "
        "Readiness probe will fail. This creates a real revision in rollout history.",
        extra={"extra_fields": {"healthy": False, "version": APP_VERSION}},
    )
else:
    log.info(
        "Starting healthy.",
        extra={"extra_fields": {"healthy": True, "version": APP_VERSION}},
    )

# ── In-memory state ────────────────────────────────────────────────────────

_bookings: dict[str, dict[str, Any]] = {}

# ── App ────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Ticket Booking Service",
    description="KubeMedic demo workload — the patient, not the product.",
    version=APP_VERSION,
)


@app.middleware("http")
async def _log_requests(request: Request, call_next):
    start = time.monotonic()
    response = await call_next(request)
    duration_ms = round((time.monotonic() - start) * 1000, 1)
    log.info(
        f"{request.method} {request.url.path} → {response.status_code}",
        extra={"extra_fields": {
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "duration_ms": duration_ms,
        }},
    )
    return response


# ── Endpoints ──────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def landing() -> HTMLResponse:
    """Landing page — establishes the app is alive on camera."""
    healthy_class = "healthy" if HEALTHY else "unhealthy"
    health_word   = "Healthy" if HEALTHY else "FAILED"
    count = len(_bookings)
    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Ticket Booking Service</title>
  <style>
    body {{ font-family: -apple-system, 'Segoe UI', sans-serif; max-width: 600px;
            margin: 60px auto; padding: 0 24px; color: #1f2328; }}
    h1 {{ font-size: 28px; margin-bottom: 6px; }}
    .status {{ font-size: 18px; font-weight: 700; padding: 8px 16px; border-radius: 4px;
               display: inline-block; margin: 12px 0; }}
    .healthy   {{ background: #d1fae5; color: #065f46; }}
    .unhealthy {{ background: #fee2e2; color: #991b1b; }}
    .meta {{ font-size: 14px; color: #57606a; margin-top: 16px; }}
  </style>
</head>
<body>
  <h1>Ticket Booking Service</h1>
  <div class="status {healthy_class}">Status: {health_word}</div>
  <div class="meta">
    <p>Version: {APP_VERSION}</p>
    <p>Bookings in memory: {count}</p>
    <p>HEALTHY env var: {os.getenv('HEALTHY', 'true')}</p>
  </div>
  <p style="margin-top:24px;font-size:14px;color:#57606a;">
    KubeMedic demo workload — this service is the patient, not the product.
  </p>
</body>
</html>""")


@app.get("/health")
async def health() -> JSONResponse:
    """
    Liveness probe. Returns 200 while the process is running.

    IMPORTANT: This must be honest. When HEALTHY=false the app is in a
    degraded state — the liveness probe deliberately returns 500 so the
    Kubernetes event stream has real Warning/Unhealthy events for the
    evidence MCP server to find.
    """
    if not HEALTHY:
        log.warning(
            "Health probe failed — HEALTHY=false",
            extra={"extra_fields": {"healthy": False, "probe": "liveness"}},
        )
        return JSONResponse(
            {"healthy": False, "status": "FAILED", "version": APP_VERSION},
            status_code=500,
        )
    return JSONResponse({"healthy": True, "status": "OK", "version": APP_VERSION})


@app.get("/ready")
async def ready() -> JSONResponse:
    """
    Readiness probe. Returns 200 only when the service can serve bookings.
    Kubernetes uses this to decide whether to route traffic to the pod.
    """
    if not HEALTHY:
        log.warning(
            "Readiness probe failed — service not ready",
            extra={"extra_fields": {"healthy": False, "probe": "readiness"}},
        )
        return JSONResponse(
            {"ready": False, "reason": "Service is degraded", "version": APP_VERSION},
            status_code=500,
        )
    return JSONResponse({"ready": True, "version": APP_VERSION})


class BookingRequest(BaseModel):
    event: str
    seats: int = 1
    name: str


@app.post("/book", status_code=201)
async def book(req: BookingRequest) -> JSONResponse:
    """
    Create a booking. Returns a BK-prefixed booking id.

    Returns 503 when the service is in a degraded state (HEALTHY=false),
    because the readiness probe failure means Kubernetes would not route
    traffic here — but we simulate it for direct testing.
    """
    if not HEALTHY:
        log.error(
            "POST /book rejected — service degraded",
            extra={"extra_fields": {"healthy": False}},
        )
        raise HTTPException(status_code=503, detail="Service unavailable — deployment is degraded")

    booking_id = f"BK-{uuid.uuid4().hex[:8].upper()}"
    booking = {
        "booking_id": booking_id,
        "event": req.event,
        "seats": req.seats,
        "name": req.name,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _bookings[booking_id] = booking
    log.info(
        f"Booking created: {booking_id}",
        extra={"extra_fields": {"booking_id": booking_id, "event": req.event}},
    )
    return JSONResponse(booking, status_code=201)


@app.get("/bookings")
async def list_bookings() -> JSONResponse:
    """
    List all bookings. Used by verification to confirm POST /book succeeded.
    The demo's ending: POST /book → GET /bookings → booking appears.
    """
    return JSONResponse(list(_bookings.values()))


@app.get("/healthz")
async def healthz() -> JSONResponse:
    """Simple process-level ping used by the dashboard's health dot."""
    return JSONResponse({"status": "ok"})
