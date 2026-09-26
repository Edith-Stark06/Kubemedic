# Ticket-Booking — Operational Playbook

Standing guidance for the `ticket-booking` deployment in `opspilot`, written by
the team ahead of any specific incident. This is policy and prior experience,
not cluster evidence — it is handed to the reasoning engine alongside the
evidence, not in place of it, and it does not override what the evidence
actually shows. If this playbook and the evidence disagree, say so explicitly
rather than silently preferring one.

## Known failure classes and preferred action

### 1. Readiness regression immediately following a deployment

Signature: rollout stalled, new revision's pods stuck `0/1 Ready`, previous
revision's pods still healthy, the failing pods' image differs from the
previous revision's.

**Prefer `rollback_deployment` to the most recent prior revision whose pods
show zero restarts and a passing readiness probe.** Do not use
`restart_deployment` for this class: a restart recreates pods on the *same*
image, and if the image itself is the regression, the new pods will fail
readiness again in the same way. We have seen this exact mistake cost an extra
readiness-probe cycle (tens of seconds) for no benefit.

### 2. Elevated restart count with no recent deployment

Signature: restart count climbing on one or more pods, no new revision in the
recent rollout history, image unchanged from the last known-good state.

**Prefer `restart_deployment`.** This class is usually a transient resource or
dependency blip (a slow downstream call, a bad connection pool state), not a
bad image, so a clean restart is normally sufficient. Rolling back would change
the running revision for no reason and adds an unnecessary audit trail entry.

### 3. Sustained elevated latency with passing readiness

Signature: application health returns 200, pods are Ready, but tickets report
slow responses under load; no recent deployment.

**Prefer `scale_workload`.** Neither a rollback nor a restart relieves
load-driven latency. For this service specifically, do not scale above 4
replicas without a capacity review — the downstream payment-service dependency
has not been load-tested past that point on this cluster.

## Timing

Avoid `scale_workload` changes between 00:00 and 06:00 UTC except to answer an
active incident: booking demand is low in that window and an unreviewed
capacity change then is more likely to be responding to noise than to real load.

## What this playbook does not cover

Any failure signature not listed above should be reasoned about from the
evidence alone, with a lower confidence than a listed class would warrant, and
the playbook's absence of guidance should be stated plainly rather than
silently extrapolated from an unrelated section above.
