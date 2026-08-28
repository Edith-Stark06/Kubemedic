---
name: runbook-bad-rollout
description: >-
  Operational runbook for a degraded or stalled Kubernetes rollout after a
  deployment change — new pods not becoming ready, readiness probe failures,
  rollout stuck partway, old pods still serving. Activates on stalled rollout,
  degraded deployment, pods not ready after a deploy, or CrashLoopBackOff
  following a new revision.
user-invocable: true
---

# Runbook — degraded rollout after a deployment change

Written the way an SRE would hand it to a new joiner: opinionated, specific,
and honest about where it stops being right.

## Symptom signature

You are in this class when **most** of these hold:

- `rollout status` reports the deployment has not completed
- one or more pods on the newest revision report `0/1 Ready`, or restart
  repeatedly with a short backoff
- cluster events carry `Warning` with reason `Unhealthy` (readiness probe
  failed) or `BackOff`, first seen shortly after a new revision was created
- `rollout history` shows a revision created just before the first symptom
- pods on the **previous** revision are still `1/1 Ready`

That last one is the tell. If old pods are fine and new pods are not, the
change is the suspect, not the environment.

## Signals to check, in this order

1. **Rollout history first.** Is there a new revision, and when? If nothing
   changed, you are in the wrong runbook.
2. **Pod state, split by revision.** Which pods are on which image, and which
   of them are ready.
3. **Events in the window.** The *first* anomalous event and its timestamp —
   not the loudest, the first.
4. **Application health, separately.** This is where the dual-signal case
   shows up (see below).

## Standard remediation

Roll back to the last revision with confirmed-healthy pods.

- Prefer an explicit `to_revision` over "the previous one". Read it from
  rollout history and name it.
- Do not restart first. A restart on a bad revision reschedules the same
  broken image and wastes a minute of the incident.
- Do not scale up. More replicas of a failing revision is more failing pods.

## The dual-signal case — call it out every time

With `maxUnavailable: 0`, a failed rollout leaves the previous revision's pods
serving traffic. So you will see:

```
Kubernetes rollout:   DEGRADED
Application health:   200 OK
```

Both readings are correct. Neither alone tells the truth. Say this explicitly
in your analysis — it is the clearest demonstration in this project of why a
single health signal is not enough, and it is exactly the kind of nuance a
reviewer notices.

It also means **verification must require both signals**. A rollback that
returns rollout-healthy while `/health` fails has not resolved the incident.

## Verification criteria

All four must hold, re-read from the cluster after the action:

1. Rollout reports complete and healthy
2. Required replicas are Ready
3. No pod is running the suspect image
4. `/health` returns 200 on a fresh request

Watch for terminating pods creating a misleading intermediate state — a pod
draining still appears in a listing. Poll for the desired state; do not read
once immediately after the action and believe it.

## When this runbook is wrong

Three cases. Each one means stop and hand back to a human.

**The bad config exists in the previous revision too.** Rolling back lands you
on a revision that fails the same way, and now you have burned time and lost
the newer change. Check whether the suspect setting was introduced in this
revision or merely surfaced by it.

**The rollout is a deliberate maintenance activity.** A stalled rollout during
a planned migration may be expected, and rolling it back may undo intentional
work. This is precisely why the human gate exists — say so in
`notes_for_reviewer` and expect a rejection.

**The cause is external.** If a dependency the new revision needs is
unavailable — a database, a secret, a downstream service — the revision may be
correct and the environment wrong. Rolling back masks the real fault and it
will return on the next deploy. The tell is an error in the application's own
output naming an external resource, rather than a probe timing out silently.

In all three: return the diagnosis with the contradicting evidence stated, and
let the human decide.
