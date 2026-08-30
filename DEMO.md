# KubeMedic Demo Reset & Run Runbook

## Quick start

```bash
# 1. Start the workload (healthy)
cd workload
pip install -r requirements.txt
uvicorn main:app --port 8001

# 2. Start the dashboard
cd dashboard
pip install -r requirements.txt
uvicorn app:app --port 8080

# 3. Open the dashboard
open http://localhost:8080
```

---

## Inject failure (for demo)

```bash
HEALTHY=false uvicorn main:app --port 8001
```

This causes `/health` and `/ready` to return 500, generating real
`Warning/Unhealthy` events in the Kubernetes event stream that the
MCP evidence collector will find.

---

## Reset to healthy

Stop the failing workload and restart it:

```bash
# Ctrl+C the workload process, then:
uvicorn main:app --port 8001
```

Or with the Kubernetes deployment, change the image/env var and let
Kubernetes roll it out.

---

## Verify reset succeeded

```bash
curl http://localhost:8001/health
# Expected: {"healthy": true, "status": "OK", "version": "1.0"}

curl http://localhost:8001/ready
# Expected: {"ready": true, "version": "1.0"}

curl -X POST http://localhost:8001/book \
  -H "Content-Type: application/json" \
  -d '{"event": "Reset test", "seats": 1, "name": "Test User"}'
# Expected: {"booking_id": "BK-XXXXXXXX", ...}

curl http://localhost:8001/bookings
# Expected: list containing the booking above
```

---

## Dashboard environment variables

| Variable | Default | Purpose |
|---|---|---|
| `KUBEMEDIC_AGENT_BASE_URL` | `""` (mock) | Set to Ramana's agent HTTP base URL when it exists |
| `KUBEMEDIC_REVIEWER_NAME` | `reviewer` | Name recorded as approver/rejector in decisions |

---

## Connect dashboard to Ramana's backend

Once Ramana's HTTP API is running:

```bash
export KUBEMEDIC_AGENT_BASE_URL=http://localhost:8000
cd dashboard
uvicorn app:app --port 8080
```

The dashboard will forward all incident reads and decision POSTs to the
real agent backend. The mock provider is bypassed automatically.

Expected agent endpoints (Ramana to implement — see docs/handoffs.md #2):

```
GET  /incidents                     → list of incidents
GET  /incidents/{id}                → full Incident JSON
POST /incidents/{id}/decision       → record approval or rejection
     body: { "decision": "approved"|"rejected",
             "approver": "...",
             "feedback": "..." }
```

---

## Demo flow

1. Visit http://localhost:8001 — confirm booking service is healthy
2. POST a booking: `curl -X POST http://localhost:8001/book -H "Content-Type: application/json" -d '{"event":"Concert","seats":2,"name":"Alice"}'`
3. Inject failure: restart workload with `HEALTHY=false`
4. Watch dashboard at http://localhost:8080 — incident INC-501 is in PENDING_APPROVAL
5. Click **Reject Remediation** → fill in reason → submit → see REJECTED + "Remediation was NOT executed"
6. Reset (restart healthy workload), start fresh incident
7. Click **Approve Remediation** → incident advances to APPROVED → EXECUTING → RESOLVED
8. Show verification signals both PASS

---

## Files created (Verona's lane)

```
dashboard/
  app.py              FastAPI server + Jinja2 templates + API routes
  api_adapter.py      API seam — mock provider + real adapter stub
  __init__.py
  requirements.txt
  templates/
    index.html        Incident list
    incident.html     Full incident detail (8 panels)
  static/
    style.css         Dark theme, filmable, 16px+, 7:1 contrast
    app.js            Fetch layer, approval/rejection, dialog

workload/
  main.py             FastAPI ticket-booking demo (5 endpoints)
  Dockerfile
  requirements.txt

DEMO.md               This file
docs/handoffs.md      Handoffs to Ramana (#2 HTTP API) and Shivraj (#1 MCP profile)
```

## What is waiting on Ramana

- HTTP API layer in `agent/` (handoff #2) — without it, the dashboard uses mock data
- Confirmation of closed `IncidentState` enum (handoff #3)

## What is waiting on Shivraj

- `k8s/` manifests with `maxUnavailable: 0`
- `scripts/` break and reset scripts
- `mcp_server/` with `--profile evidence` flag (handoff #1)
