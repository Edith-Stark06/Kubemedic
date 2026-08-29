---
name: correlation-viz
description: >-
  How to make many-to-one incident correlation visually obvious in seconds —
  several tickets converging into one master incident with the shared signals
  that justify the merge. Activates on correlation visualization, showing
  multiple tickets as one incident, or master incident display.
user-invocable: true
---

# Visualizing many-to-one correlation

This is one of the three claimed innovations. If a judge cannot see it in five
seconds, the claim scores nothing regardless of how well the backend does it.

## The shape

```
  TICKET-101  ─┐
  TICKET-102  ─┼──▶  IBM Bob  ──▶  INCIDENT INC-501  ──▶  Root cause
  TICKET-103  ─┘
```

Render this as an actual visual convergence — three things on the left,
funnelling into one on the right. Not a list with a heading that says
"correlated". The convergence has to be the picture.

Plain SVG or CSS. No charting library, no new dependency.

## Show the reasoning, not just the result

Convergence alone looks like grouping by workload name, which is unimpressive.
What makes it land is the `correlation_basis` array beside it:

```
Correlated because:
  · all three reference deployment/ticket-booking
  · all onset within 4 minutes of the first Warning event at 09:38:12Z
  · a stalled rollout is the known upstream cause of the readiness
    failures in T-102 and the intermittent 5xx in T-103
```

That third line is the one that reads as real reasoning rather than string
matching. Give it room.

## Render exclusions too

If `excluded_tickets` is non-empty, show it — a ticket sitting outside the
funnel with the reason it was kept separate.

A correlation that only ever merges looks like it merges everything. Showing
one that was deliberately left out proves discrimination, and it costs you
about six lines of markup. It is disproportionately convincing.

## Before and after

Where the layout allows, show the contrast the correlation removes:

```
Without correlation:  3 incidents,  3 investigations,  3 engineers
With correlation:     1 incident,   1 root cause,      1 decision
```

Two lines, and they make the value legible to a judge who has not been
following closely.

## What not to do

- No animation on the convergence. On a screen recording it either plays
  before the viewer is looking or delays the information. Static.
- Do not compute the correlation in the browser. It arrives in the
  `correlation` block from the API. You are rendering a conclusion, not
  reaching one.
- Do not show ticket ids alone. Show enough of each ticket's reported symptom,
  in the reporter's own words, that the merge is judgeable. "TICKET-101,
  TICKET-102, TICKET-103" tells the viewer nothing about whether merging them
  was correct.
