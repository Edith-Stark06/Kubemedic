---
name: gemini-audit
description: >-
  Audits the repository for leftover Gemini, google-genai or GOOGLE_API_KEY
  references and classifies each by whether it sits on the demonstrated
  reasoning path. Activates on Gemini audit, model provider sweep, checking
  which AI provider the code actually uses, or pre-submission compliance sweep.
user-invocable: true
---

# Gemini dependency audit

The contest requires IBM Bob to be genuinely used. A repo whose README says
Bob while `agent/reasoning.py` imports `google.generativeai` tells a reviewer
the story is decoration. This skill finds every such gap.

## Sweep

Run all of these and keep the raw output:

```bash
grep -RniE "gemini|google-genai|google\.generative|genai|GOOGLE_API_KEY|GEMINI_API_KEY" . \
  --exclude-dir=.git --exclude-dir=.venv --exclude-dir=node_modules --exclude-dir=__pycache__

grep -RniE "gemini|google" requirements*.txt pyproject.toml 2>/dev/null
git log --oneline -20
```

Also check by hand, because these do not always grep cleanly: dashboard
templates and JS strings, `.env.example`, CI workflow files, README badges,
architecture diagrams (including image files — an old PNG can say Gemini),
docstrings, and log message prefixes.

## Classify every hit

Do not report a flat list. Sort into four buckets:

**BLOCKER — on the demonstrated reasoning path.** The primary analysis calls
Gemini, or a fresh clone needs a Google credential to run the demo. This is a
compliance risk, not a tidiness issue.

**MAJOR — user-visible inconsistency.** UI labels, README, architecture docs
or the demo video path say Gemini while the submission claims Bob. The
implementation, documentation, UI and Bob report must tell one story.

**MINOR — inert.** A dependency in requirements that nothing imports; a
commented-out block; a variable name.

**HISTORICAL — legitimate.** The git history genuinely contains a Gemini
phase. Do not rewrite history to hide it. If it comes up, the honest framing
is that the project was consolidated onto IBM Bob during the contest.

## Report format

For each finding: file path, line number, the bucket, one line on why, and the
fix in one line. End with the single question that matters:

> Does a fresh clone, following only the README, execute the demonstrated
> reasoning flow without any Google credential?

If the answer is not an unqualified yes, list exactly what stands between the
repo and that yes.

## Do not

Do not delete functionality to make the grep clean. Replace the model adapter;
keep the typed models, correlation, planning, executor, verification, audit
and tests. Those are the valuable parts and they are provider-agnostic.
