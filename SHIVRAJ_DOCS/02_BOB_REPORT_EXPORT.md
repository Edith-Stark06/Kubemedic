# SUB-003 — Export the IBM Bob report

**Owner:** Shivraj · **Est:** 30 min · **Priority: required deliverable**

---

## Why this is not optional

ENTRY REQUIREMENTS, Official Rules, deliverable 4, quoted exactly:

> "Working code repository or evidence of technology proof-of-concept solution,
> **including exported IBM Bob report of all relevant tasks/sessions used for
> the contest**"

It is buried inside the fourth bullet, which is exactly why teams miss it. An
otherwise complete entry can be marked non-compliant for its absence.

Required **whether or not `BOB-001` succeeds.** The report covers the Bob
sessions used to *build* the project, not only Bob calls made *by* the project.
Every Bob session Ramana ran on the `.bob/` asset pack, the modes, the skills,
the consolidation work — those are all "relevant tasks/sessions used for the
contest".

---

## Where it lives

```
submission/
├── bob-report/
│   ├── README.md               what this is, and which sessions it covers
│   └── <exported files>        whatever IBM Bob produces
├── evidence/
│   ├── validate-run.txt        scripts/validate.sh output
│   ├── pytest-run.txt          full suite output
│   └── INC-*.json              a real audit record
├── PROBLEM_AND_SOLUTION.md     SUB-001
└── HOW_WE_USED_IBM_BOB.md      SUB-002
```

`.gitignore` currently ignores `records/*.json`, so a curated record copied
into `submission/evidence/` **is** tracked. That was deliberate.

---

## How to export

I cannot do this step — it is a GUI action in the IBM Bob application, which I
have no way to drive.

1. Open IBM Bob (Antigravity IDE). On this machine it is at
   `C:\Users\shivraj\AppData\Local\Programs\IBM Bob\bin\bobide.CMD` — that is
   where `agent/bob.py` located it.
2. Find the session or task history for this workspace.
3. Export **every session related to this contest** — the asset-pack install,
   the consolidation work, the skills and modes, any analysis runs.
4. Save into `submission/bob-report/`.

**If Bob offers no export button**, do not stop. Capture what you can and say
so plainly in the README below:
- Screenshots of the session list and of representative sessions
- The `.bob/` directory itself — `custom_modes.yaml`, the seven skills, the six
  agent personas, `mcp.json` — which is concrete, reviewable evidence of how
  Bob was configured and used
- A written session log: what was asked, in which mode, and what came back

A clearly-labelled best-effort export beats a missing deliverable. It does not
beat a fabricated one — do not reconstruct sessions that did not happen.

---

## `submission/bob-report/README.md` — template

```markdown
# IBM Bob Report

Exported IBM Bob tasks and sessions used to build KubeMedic for the IBM
TechXchange 2026 Pre-conference Dev Day Hackathon.

## Contest window

Contest period: 2026-08-28 10:00 ET to 2026-08-30 10:00 ET.
Sessions in this export fall within that window.

## What IBM Bob was used for

1. **Project configuration.** `.bob/` in the repository root is a Bob asset
   pack authored for this project: four custom modes
   (`kubemedic-analyst`, `kubemedic-dev`, `kubemedic-auditor`, ...), seven
   skills (`incident-correlation`, `remediation-planning`,
   `verification-review`, `runbook-bad-rollout`, `track-consolidation`,
   `submission-audit`, `gemini-audit`), six investigator personas, and
   `AGENTS.md` -- the standing instructions Bob loads in every session.

2. **Building the system.** Bob sessions in `kubemedic-dev` mode were used to
   consolidate two competing implementations into the submitted architecture.

3. **Auditing the system.** `kubemedic-auditor` mode and the `gemini-audit`
   and `submission-audit` skills were used to sweep the repository for
   provider leftovers, secrets, and claims not backed by code.

4. **Runtime reasoning.** `agent/bob.py` is the single boundary through which
   the running system calls IBM Bob to correlate tickets and reason about
   root cause. See `submission/HOW_WE_USED_IBM_BOB.md`.

## Files

| File | Session | Date | Mode |
|---|---|---|---|
| ... | ... | ... | ... |

## Note on completeness

<Delete whichever does not apply.>

- All contest sessions are included.
- IBM Bob v1.126.0 provides no session export function. This directory
  contains screenshots of the session history plus the complete `.bob/`
  configuration, which is the reviewable artifact of how Bob was configured
  and used. No session has been reconstructed or paraphrased from memory.
```

---

## Before you commit it

```bash
grep -rniE "api[_-]?key|secret|token|password|C:\\\\Users" submission/bob-report/
```

`AGENTS.md`: *"Never commit credentials of any kind... This includes inside the
exported Bob report in `submission/bob-report/`."* A Bob transcript can easily
contain a pasted key or an absolute local path.

---

## Definition of done

- [ ] `submission/bob-report/` exists and is committed
- [ ] It contains either a real export or a labelled best-effort substitute
- [ ] `README.md` names what is included and what is not
- [ ] No credentials, no absolute local paths
- [ ] Referenced from the top-level README and the submission form
