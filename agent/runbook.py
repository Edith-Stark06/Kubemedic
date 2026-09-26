"""
Optional operator-authored reference material handed to the reasoning engine
alongside cluster evidence -- the "document understanding" input.

Distinct from evidence (read from the cluster) and from human feedback (a
specific reviewer's objection to one plan): a runbook is standing operational
knowledge, written by a team ahead of any single incident, that evidence alone
cannot recover -- which of two viable actions this team prefers for a given
failure class, and why. Bob is asked to weigh it, not obey it: if the evidence
and the playbook disagree, the prompt tells it to say so rather than silently
picking one.
"""
from __future__ import annotations

import os
from pathlib import Path

DEFAULT_RUNBOOK_PATH = "docs/RUNBOOK_TICKET_BOOKING.md"
# Bounded like every other prompt input (see agent/providers/prompt.py). A
# playbook is short by nature; anything past this is almost certainly the
# wrong file.
MAX_RUNBOOK_CHARS = 8000


def load_runbook(path: str | None = None) -> str | None:
    """
    The configured runbook's text, or None if none is configured or found.

    KUBEMEDIC_RUNBOOK_PATH selects the file; set it to the empty string to
    disable the feature outright. A missing file at the default path is
    normal (most workspaces will not have one) and returns None rather than
    raising -- reasoning must still work without a runbook.
    """
    configured = path if path is not None else os.getenv("KUBEMEDIC_RUNBOOK_PATH")
    if configured == "":
        return None
    target = Path(configured or DEFAULT_RUNBOOK_PATH)
    try:
        text = target.read_text(encoding="utf-8")
    except OSError:
        return None
    if not text.strip():
        return None
    if len(text) > MAX_RUNBOOK_CHARS:
        text = text[:MAX_RUNBOOK_CHARS] + "\n...[truncated]"
    return text
