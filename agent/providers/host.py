"""
Host-session provider — reason using whatever agentic IDE is hosting this
workspace: Claude Code, the IBM Bob IDE, or Antigravity.

WHAT THIS IS NOT
----------------
None of these hosts exposes an inbound API a child process can call. There is
no ambient endpoint, no local socket, no "ask the session" function. A provider
that claimed to call them silently would be fiction, and the first thing a
reviewer would find.

WHAT THIS ACTUALLY DOES
-----------------------
It uses the one channel that genuinely exists between a running process and an
agentic IDE: the workspace filesystem. The host agent is already sitting in
this directory with read and write access.

    1. The pipeline writes the reasoning request to
       .kubemedic/reasoning-request.md -- the same prompt any other provider
       would have sent, including the evidence and any human feedback.
    2. The host agent reads it, reasons, and writes the JSON analysis to
       .kubemedic/reasoning-response.json.
    3. This provider picks it up and validates it exactly as a headless
       response is validated -- same schema, same allowlist, same failure
       policy.

So the reasoning really is done by the host model. Nothing is fabricated, and
the audit record names which host answered.

PROVENANCE
----------
The host is detected from the environment and stamped honestly:

    IBM Bob IDE   -> ibm-bob      (it genuinely is Bob)
    Claude Code   -> claude-code
    Antigravity   -> antigravity
    anything else -> host

If you did not answer the request, do not point this provider at a stale
response file. Validation checks shape, not origin.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from agent.providers.base import BaseProvider

WORKDIR = Path(os.getenv("KUBEMEDIC_HOST_DIR", ".kubemedic"))
REQUEST_FILE = "reasoning-request.md"
RESPONSE_FILE = "reasoning-response.json"

# How long to wait for the host agent to answer. Zero means "write the request
# and return immediately", which is what a scripted run wants.
DEFAULT_WAIT_S = 0
POLL_INTERVAL_S = 2

FENCE = "``" + "`"


def detect_host() -> tuple[str, str]:
    """
    Identify the agentic IDE hosting this workspace.

    Returns (provider_id, human label). Order matters: Antigravity and the Bob
    IDE can both set editor-generic markers, so the specific ones are checked
    first.
    """
    env = os.environ

    if env.get("KUBEMEDIC_HOST_KIND"):
        kind = env["KUBEMEDIC_HOST_KIND"].strip().lower()
        return kind, f"{kind} (forced by KUBEMEDIC_HOST_KIND)"

    if any(k.startswith("BOBIDE") or k.startswith("IBM_BOB") for k in env):
        return "ibm-bob", "IBM Bob IDE"
    if env.get("ANTIGRAVITY") or env.get("ANTIGRAVITY_SESSION_ID"):
        return "antigravity", "Antigravity IDE"
    if env.get("CLAUDECODE") or env.get("CLAUDE_CODE_ENTRYPOINT"):
        return "claude-code", "Claude Code session"
    if env.get("AI_AGENT"):
        return "host", f"agentic host ({env['AI_AGENT']})"
    return "host", "no agentic host detected"


class HostSessionProvider(BaseProvider):
    """Reason through the agentic IDE hosting this workspace."""

    display_name = "Host IDE session"

    def __init__(self, workdir: Path | None = None) -> None:
        super().__init__()
        self.id, self.host_label = detect_host()
        self.display_name = f"Host session ({self.host_label})"
        self.dir = Path(workdir or WORKDIR)
        self.request_path = self.dir / REQUEST_FILE
        self.response_path = self.dir / RESPONSE_FILE
        self.wait_s = int(os.getenv("KUBEMEDIC_HOST_WAIT_SECONDS", DEFAULT_WAIT_S))

    def is_configured(self) -> tuple[bool, str]:
        # Always available: it needs no credential, only somebody to answer.
        return True, (
            f"{self.host_label}; hand-off via {self.dir}/ "
            f"(wait {self.wait_s}s for a response)"
        )

    def _invocation(self) -> list[str]:
        return [f"host:{self.id}", str(self.request_path)]

    def _consume_response(self) -> str | None:
        """
        Take an answer that is newer than the outstanding request.

        The normal workflow is two steps: one run writes the request, the host
        agent answers, the next run picks it up. So a response has to survive
        between runs -- but only if it answers the *current* request, and only
        once. It is deleted on read so a stale analysis can never be replayed
        into a later incident.
        """
        if not self.response_path.is_file():
            return None
        if not self.request_path.is_file():
            # No outstanding request, so this answers nothing we asked. A
            # leftover file from a previous incident is exactly the replay we
            # are guarding against.
            return None
        if self.response_path.stat().st_mtime < self.request_path.stat().st_mtime:
            return None                    # answers an older request
        text = self.response_path.read_text(encoding="utf-8").strip()
        self.response_path.unlink(missing_ok=True)
        return text or None

    def _write_request(self, prompt: str) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        self.request_path.write_text(
            "# KubeMedic reasoning request\n\n"
            f"Host detected: **{self.host_label}**\n\n"
            "Answer the prompt below and write the JSON object -- and nothing "
            f"else -- to `{self.response_path.as_posix()}`.\n\n"
            "The schema is "
            "`.bob/skills/incident-correlation/references/evidence-schema.md`. "
            "Your answer is validated exactly as a headless model response is: "
            "an action outside the allowlist, a missing target, or an invalid "
            "confidence value is refused.\n\n"
            "---\n\n"
            f"{FENCE}\n{prompt}\n{FENCE}\n",
            encoding="utf-8",
        )

    def _invoke(self, prompt: str) -> str:
        # An answer to the outstanding request takes priority: this is the
        # second half of the two-step workflow, and writing a fresh request
        # first would delete the very answer we are here to collect.
        answered = self._consume_response()
        if answered:
            return answered

        self._write_request(prompt)

        deadline = time.monotonic() + max(0, self.wait_s)
        while True:
            answered = self._consume_response()
            if answered:
                return answered
            if time.monotonic() >= deadline:
                break
            time.sleep(min(POLL_INTERVAL_S, max(0, deadline - time.monotonic())))

        # No answer. Say exactly what to do -- this is the normal first run,
        # not an error condition to be embarrassed about.
        raise RuntimeError(
            f"no response from {self.host_label}. The request is at "
            f"{self.request_path.as_posix()}. Ask the host agent to read it and "
            f"write its JSON analysis to {self.response_path.as_posix()}, then "
            "run the same command again. Set KUBEMEDIC_HOST_WAIT_SECONDS to "
            "wait in-process instead of returning immediately."
        )
