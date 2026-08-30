"""
IBM Bob provider -- the project's default reasoning engine.

INVOCATION
----------
IBM Bob v1.126.0 (the Antigravity IDE, `bobide`) has no headless subprocess
mode: `bobide chat` opens the GUI and returns exit 0 with no stdout, and
`bobide-tunnel agent host` needs the IDE running as supervisor. The only
programmatic path is the cloud RemoteAgent REST API:

    POST {base}/api/v1/chats                 -> {id}
    POST {base}/api/v1/chats/{id}/execute    -> result

UNVERIFIED
----------
The default base is https://cloud.manufact.com, read from the IDE extension's
RemoteAgent class. Nothing in this repository establishes it as the sanctioned
IBM Bob API for the contest. Confirm against IBM Bob documentation before
depending on it.

There is a second, credential-free path: run Bob interactively in the workspace
(it launches the read-only MCP evidence server itself) and ingest the JSON with
the `manual` provider or scripts/ingest_bob_analysis.py.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from agent.providers.base import BaseProvider
from agent.secrets import get_secrets


class IBMBobProvider(BaseProvider):
    id = "ibm-bob"
    display_name = "IBM Bob"

    def __init__(self) -> None:
        super().__init__()
        secrets = get_secrets()
        self.api_key = secrets.get("KUBEMEDIC_BOB_API_KEY")
        self.agent_id = secrets.get("KUBEMEDIC_BOB_AGENT_ID")
        self.base = (
            os.getenv("KUBEMEDIC_BOB_API_BASE") or "https://cloud.manufact.com"
        ).rstrip("/")
        self.mode = os.getenv("KUBEMEDIC_BOB_MODE", "kubemedic-analyst")
        self.timeout = int(os.getenv("KUBEMEDIC_BOB_TIMEOUT_SECONDS", "180"))

    def is_configured(self) -> tuple[bool, str]:
        if not self.api_key:
            return False, (
                "KUBEMEDIC_BOB_API_KEY is unset. Set it with "
                "KUBEMEDIC_BOB_AGENT_ID, or run Bob interactively in the "
                "workspace and use the manual provider."
            )
        if not self.agent_id:
            return False, (
                "KUBEMEDIC_BOB_AGENT_ID is unset. The agent id is in the "
                "IBM Bob cloud console."
            )
        return True, f"IBM Bob REST at {self.base}, mode {self.mode}"

    def _invocation(self) -> list[str]:
        return [f"REST:{self.base}/api/v1/chats", f"mode={self.mode}"]

    def _post(self, url: str, body: dict, timeout: int) -> str:
        request = urllib.request.Request(
            url,
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json", "x-api-key": self.api_key},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read().decode()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:400]
            if exc.code == 401:
                raise RuntimeError(
                    "authentication failed -- check KUBEMEDIC_BOB_API_KEY"
                ) from exc
            raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
        except TimeoutError:
            raise
        except OSError as exc:
            raise RuntimeError(f"could not reach {self.base}: {exc}") from exc

    def _invoke(self, prompt: str) -> str:
        created = self._post(
            f"{self.base}/api/v1/chats",
            {
                "title": f"KubeMedic incident analysis - mode:{self.mode}",
                "agent_id": self.agent_id,
                "type": "agent_execution",
            },
            timeout=30,
        )
        chat_id = json.loads(created).get("id")
        if not chat_id:
            raise RuntimeError("chat creation returned no id")

        return self._post(
            f"{self.base}/api/v1/chats/{chat_id}/execute",
            {"query": prompt, "max_steps": 20},
            timeout=self.timeout,
        )
