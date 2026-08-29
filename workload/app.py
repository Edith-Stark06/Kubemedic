"""Ticket Booking — minimal demo workload for OpsPilot.

Deliberately tiny and dependency-light (no DB) so the setup is reproducible.
The HEALTHY env var is the deterministic-incident lever: the "bad" deployment
revision sets HEALTHY=false, which makes /health return 503 so the readiness
probe fails and the rollout regresses. This is real, explainable, and reversible
(roll back to the previous revision to recover).
"""
import os

from fastapi import FastAPI, Response

APP_VERSION = os.getenv("APP_VERSION", "1.0")

app = FastAPI(title="Ticket Booking", version=APP_VERSION)

SEATS_TOTAL = 50
_seats_booked = 0


def _is_healthy() -> bool:
    return os.getenv("HEALTHY", "true").strip().lower() != "false"


@app.get("/")
def root():
    return {
        "service": "ticket-booking",
        "version": APP_VERSION,
        "seats_total": SEATS_TOTAL,
        "seats_booked": _seats_booked,
        "seats_remaining": SEATS_TOTAL - _seats_booked,
    }


@app.get("/health")
def health(response: Response):
    """Readiness/liveness signal. Returns 503 when HEALTHY=false."""
    if not _is_healthy():
        response.status_code = 503
        return {"status": "unhealthy", "version": APP_VERSION}
    return {"status": "healthy", "version": APP_VERSION}


@app.post("/book")
def book(response: Response):
    global _seats_booked
    if not _is_healthy():
        response.status_code = 503
        return {"error": "service unhealthy"}
    if _seats_booked >= SEATS_TOTAL:
        response.status_code = 409
        return {"error": "sold out"}
    _seats_booked += 1
    return {
        "booked": True,
        "seats_booked": _seats_booked,
        "seats_remaining": SEATS_TOTAL - _seats_booked,
    }
