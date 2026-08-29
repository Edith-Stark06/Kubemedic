---
name: demo-script
description: >-
  Writes the demo video script, shot list and narration for the hackathon
  submission, including the mandatory explanation of how IBM Bob was used.
  Activates on demo video, video script, shot list, narration, or recording
  plan.
user-invocable: true
---

# The demo video

For a judge, the video *is* the project. Everything else is evidence that the
video was not staged.

## Structure

Open with something working, then break it. Nobody looks away from that. Most
teams open with an architecture diagram and lose the room in fifteen seconds.

| Time | Shot | Why it is there |
|---|---|---|
| 0:00–0:25 | The app working. Book a ticket. It succeeds. | Establishes what is being protected |
| 0:25–0:45 | Inject the failure. Show it broken. | Stakes, before any hero appears |
| 0:45–1:05 | Three tickets arrive | Sets up the correlation payoff |
| 1:05–1:30 | MCP gathers evidence — pods, events, health, revisions | Shows the facts are real, not narrated |
| 1:30–2:10 | **IBM Bob correlates three tickets into one incident**, names a cause, cites its evidence | The first of three claimed innovations |
| 2:10–2:35 | The plan: action, blast radius, risk, reversibility, verification plan | The second innovation |
| 2:35–3:00 | **Reject.** Type a real reason. Show it recorded, action executed: NO | The third innovation, and the best fifteen seconds available |
| 3:00–3:20 | Approve. Execute. | The gate is real in both directions |
| 3:20–3:50 | **Independent verification.** Both signals. The app works again. | The closing loop |
| 3:50–4:30 | How IBM Bob was used: modes, skills, personas, MCP, named | Mandatory under the rules |

## The rejection shot

Do this before the approval, not after. It is the strongest sequence in the
project and it proves the human gate is real rather than a rubber stamp.

Type an actual reason on camera — something a real engineer would write, like
*"this deployment is an approved maintenance activity, do not roll back."*
Then show the recorded decision with **Action executed: NO**.

Say the sentence: *"The AI recommended a rollback. A human disagreed, said
why, and nothing happened to the cluster. That reason is now part of the
incident record."*

## The IBM Bob section is not optional

The rules require the video to demonstrate the solution **and** explain how
IBM Bob was used. A brilliant demo without that section is non-compliant.

Be specific. Name the mode the analyst runs in, name the skills, name the
subagent personas, name the MCP server. Show the `.bob/` directory on screen.
The strongest line available:

> "Bob has no tool that can change this cluster. Here is the MCP config —
> there is no rollback tool, no restart tool, no scale tool. Mutation happens
> in the executor, and only after a human approved it."

## Rules for the narration

- Never claim something the recording does not show. If the video does not
  show it, cut the sentence.
- Do not talk over the moment of recovery. Let the successful booking sit in
  silence for two seconds.
- Captions on every number.
- Screen recording plus voiceover. No webcam. Clear quiet audio over a screen
  capture beats a webcam every time, and bad audio is the most common reason a
  good demo does not land.
- Do not fabricate a Bob interaction for the camera.

## Before you call it done

Watch it once, muted, start to finish. If the story is unclear without sound,
re-cut it rather than rewriting the narration. Then check the audio on
somebody else's device.
