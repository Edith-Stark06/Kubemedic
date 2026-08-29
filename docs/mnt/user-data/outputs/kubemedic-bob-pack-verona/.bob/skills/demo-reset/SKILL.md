---
name: demo-reset
description: >-
  A documented, repeatable path back to a clean healthy state between demo
  takes. Activates on demo reset, returning the workload to healthy, replaying
  the demo, or preparing for another recording take.
user-invocable: true
---

# Reset discipline

You will run the demo more times than you expect. Four to six recording takes,
plus rehearsals, plus every time something breaks mid-explanation. If reset is
slow or unreliable, Sunday morning becomes frantic instead of boring.

Boring is the goal.

## The requirement

One documented command returns everything to a known-clean state in under
thirty seconds:

- workload healthy, all replicas ready, running the good revision
- `/health` returning 200
- incident records cleared or archived, so the dashboard starts empty
- tickets cleared
- dashboard reloads to a clean initial view

Note that `scripts/` is Shivraj's directory. If the cluster-side reset needs a
change, file a handoff rather than editing it. Your side is the app state, the
records, and the dashboard's starting view.

## Verify the reset, do not assume it

A reset that reports success while a terminating pod lingers will produce a
confusing first thirty seconds of the next take. The script should poll for
the desired state rather than sleeping a fixed interval and hoping.

After reset, confirm affirmatively: replicas ready, `/health` returns 200, the
dashboard shows no active incident.

## Document it where someone tired can find it

Put the exact commands in `DEMO.md`, in order, with what each one does and
what "it worked" looks like. Not in a chat message, not in someone's head.
During recording, whoever is running reset may not be you.

## Rehearse the recovery path

Separately from reset: if the environment breaks badly mid-recording, how fast
can you be back? Time it once and know the number. A rehearsed two-minute
recovery is survivable; an unrehearsed one ends the session.

## Record a backup take

After the dress rehearsal, while everything is warm and working, record a full
clean take immediately. If the final recording session goes wrong, that backup
is the submission. This is the cheapest insurance available and it is always
the thing teams skip.
