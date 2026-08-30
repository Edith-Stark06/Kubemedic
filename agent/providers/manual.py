"""
Manual provider -- an analysis produced in an interactive IBM Bob session.

WHY THIS IS A PROVIDER AND NOT JUST A SCRIPT
--------------------------------------------
IBM Bob has no headless mode, and the cloud REST path needs credentials that
may not be provisioned. But Bob still does the real work interactively: opened
as a workspace it launches the read-only MCP evidence server, calls those tools
against the live cluster, loads the incident-correlation skill, and returns a
JSON analysis.

Making that a provider means the interactive path goes through exactly the same
validation, the same audit entry and the same failure policy as a headless
call. There is no second code path with weaker checks.

PROVENANCE
----------
Validation checks shape, not origin. This provider records that the analysis
arrived from an interactive session, so an audit record never implies a
headless call that did not happen. If you did not run the session, do not point
this provider at a file.

    KUBEMEDIC_REASONING_PROVIDER=manual
    KUBEMEDIC_MANUAL_ANALYSIS_FILE=bob-analysis.json
"""
from __future__ import annotations

import os
from pathlib import Path

from agent.providers.base import BaseProvider

DEFAULT_FILE = "bob-analysis.json"
FENCE = "``" + "`"


class ManualProvider(BaseProvider):
    id = "ibm-bob"          # the analysis really is Bob's
    display_name = "IBM Bob (interactive session)"

    def __init__(self, path: str | None = None) -> None:
        super().__init__()
        self.path = Path(
            path or os.getenv("KUBEMEDIC_MANUAL_ANALYSIS_FILE", DEFAULT_FILE)
        )

    def is_configured(self) -> tuple[bool, str]:
        if not self.path.is_file():
            return False, (
                f"No analysis file at {self.path}. Run the incident session in "
                "IBM Bob (KubeMedic Analyst mode), save the JSON it returns, "
                "and set KUBEMEDIC_MANUAL_ANALYSIS_FILE."
            )
        return True, f"interactive IBM Bob session, analysis from {self.path}"

    def _invocation(self) -> list[str]:
        return ["interactive-session", "mode:kubemedic-analyst", str(self.path)]

    def _invoke(self, prompt: str) -> str:
        # The prompt is unused: a human already ran it inside Bob. It is still
        # built by the base class so the audit trail records the same shape of
        # request a headless provider would have sent.
        text = self.path.read_text(encoding="utf-8").strip()
        if text.startswith(FENCE):
            # Copying out of a chat window brings the fences along.
            text = "\n".join(
                line for line in text.splitlines()
                if not line.strip().startswith(FENCE)
            ).strip()
        if not text:
            raise RuntimeError(f"{self.path} is empty")
        return text
