---
name: filmable-ui
description: >-
  Makes the dashboard legible when screen-recorded at 1080p and compressed by
  a video platform. Activates on demo recording legibility, screen recording,
  UI polish before filming, or making the dashboard readable on video.
user-invocable: true
---

# Build it to be filmed, not to be read on a laptop

The dashboard will be judged almost entirely through a compressed video, at
whatever size the judge's player is, probably not full screen. Something
comfortable at arm's length on a 27-inch monitor can be unreadable there.

## Sizing

- Body text no smaller than **16px**. Evidence and monospace blocks no smaller
  than **14px**. This will feel large in the browser. That is correct.
- Line height 1.5 or more. Compression smears tight text.
- Generous padding. Dense-but-cramped reads as noise on video; dense-but-spaced
  reads as substantial.
- Design at 1920×1080 and check at 1280×720, because that is roughly what
  survives compression and platform scaling.

## Contrast

- Dark background, high-contrast text. At least 7:1 for body text.
- Avoid mid-grey on dark. It is the first thing to disappear.
- Do not encode meaning in colour alone. A red badge and a green badge look
  similar after compression and identical to a colour-blind judge. Pair every
  colour with a word: `VERIFIED`, `REJECTED`, `FAILED`.

## Status must be readable across a room

The incident state is the single most-referenced element in the video. Make it
a large text badge, high contrast, top of the screen, in a fixed position that
does not move between states. A viewer should be able to glance and know where
in the lifecycle they are.

## No truncation on the things that matter

Root cause statements, rejection reasons, evidence citations and error
messages must render in full. A CSS ellipsis on the human's rejection reason
cuts exactly the content the shot exists to prove.

If something genuinely needs to be long, let the panel be tall. Vertical space
is free; a truncated argument is not.

## No animation on information

- No fade-in, no slide, no staggered reveal on content the narration refers
  to. It either plays before the viewer is looking or delays the point.
- No auto-refresh that redraws mid-sentence.
- Loading states appear only when something is genuinely loading, and they say
  what is loading: "Collecting evidence…", not a bare spinner.

Transitions between incident states are the one exception, and even then keep
them under 150ms.

## Before every recording session

- Zoom to 100%. A browser left at 110% from yesterday changes every layout
  assumption you tested.
- Hide bookmarks, extensions, notifications, and any tab whose title gives
  something away.
- Check the window is at the recording resolution, not maximised on a
  differently-sized display.
- Load every state once and confirm each renders: analysed, awaiting review,
  rejected with a reason, executing, verified, and **verification failed**.
- Watch a thirty-second sample muted. If the story is not followable without
  audio, the layout needs work, not the narration.
