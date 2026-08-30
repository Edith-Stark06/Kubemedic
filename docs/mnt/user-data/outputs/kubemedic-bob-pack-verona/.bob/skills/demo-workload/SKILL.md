---
name: demo-workload
description: >-
  Builds and maintains the ticket-booking FastAPI demo workload and its
  deterministic failure injection. Activates on the ticket-booking app, demo
  workload, failure injection, breaking the app on purpose, or the healthy and
  bad image versions.
user-invocable: true
---

# The demo workload

**The ticket-booking app is not the product. It is the patient.**

It exists so the agent has something real to diagnose. Getting this backwards
is the single most common way a team like ours builds the wrong thing. It
needs to be *believable*, not good.

## Do not gold-plate it

No authentication, no database, no payment flow, no admin panel, no styling
beyond what is needed to look real on camera. In-memory storage. Every hour
spent here is an hour not spent on the dashboard, which is what is actually
judged.

If the app already exists and works, **change as little as possible.** Read it
first. The instruction is to preserve the existing workload and its failure
levers, not to rewrite them.

## Endpoints

```
GET  /            landing page, shows the app is alive and looks real
GET  /health      liveness — 200 while the process is up
GET  /ready       readiness — 200 only when it can actually serve bookings
POST /book        create a booking, return a BK- prefixed id
GET  /bookings    list bookings, so a created one can be read back
```

The `/health` endpoint is not decoration — it is one of the two signals
verification requires. It must be honest. If the app cannot serve, `/health`
must not return 200.

## Failure injection must be deterministic

Whatever mechanism already exists — the `HEALTHY=true` / `HEALTHY=false`
environment lever, or good and bad image tags — preserve it. It works, the
team knows it, and it produces a real rollout revision, which is what makes
`rollback_deployment` the genuinely correct fix rather than a staged one.

Requirements for the lever:

- Produces its symptom within about twenty seconds, every time
- Creates a real deployment revision, so rollout history has something true in
  it for the change-history investigator to find
- Is reversible in under thirty seconds
- Is idempotent and safe to run repeatedly in any order

Run break and reset alternately ten times before trusting it. You will run
these scripts more than any code you write this weekend.

## Structured logging

Log to stdout as JSON: timestamp, level, request id, path, status,
duration_ms. When the app fails, log a clear structured error naming what went
wrong before it dies.

The log investigator needs something true to find. An app that dies silently
gives the agent nothing to diagnose and makes the demo look staged.

## The dual-signal property

With `maxUnavailable: 0`, a failed rollout leaves the previous revision's pods
serving traffic. That produces the project's best teaching moment:

```
Kubernetes rollout:  DEGRADED
Application health:  200 OK
```

Do not "fix" this. It is deliberate, it is realistic, and it is the clearest
demonstration of why one health signal is not enough. If someone proposes
changing the rollout strategy to make the demo tidier, say no.

## Sanity check before handing off

`POST /book`, then `GET /bookings`, and confirm the booking is there. That
readback is what verification asserts. If it does not work, the demo has no
ending.
