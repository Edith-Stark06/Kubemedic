"""
Anthropic Claude provider -- development and fallback only.

NOT THE DEFAULT, DELIBERATELY
-----------------------------
KubeMedic is an IBM Bob project. This provider exists so the abstraction is
demonstrably real rather than a single-implementation interface, and so the
system has a working reasoning path when IBM credentials are not provisioned.
The default in agent/providers/__init__.py is ibm-bob and should stay there.

CREDENTIALS
-----------
Needs an Anthropic API key (KUBEMEDIC_ANTHROPIC_API_KEY, `sk-ant-...`) from
console.anthropic.com. A Claude.ai or Claude Code login is NOT this: those are
a different product with separate billing, and no server process can use them.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from agent.providers.base import BaseProvider
from agent.providers.prompt import SYSTEM_PROMPT
from agent.secrets import get_secrets

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"


class AnthropicProvider(BaseProvider):
    id = "anthropic"
    display_name = "Anthropic Claude"

    def __init__(self) -> None:
        super().__init__()
        self.api_key = get_secrets().get("KUBEMEDIC_ANTHROPIC_API_KEY")
        self.model = os.getenv("KUBEMEDIC_ANTHROPIC_MODEL", "claude-sonnet-5")
        self.timeout = int(os.getenv("KUBEMEDIC_ANTHROPIC_TIMEOUT_SECONDS", "180"))
        self.max_tokens = int(os.getenv("KUBEMEDIC_ANTHROPIC_MAX_TOKENS", "4000"))

    def is_configured(self) -> tuple[bool, str]:
        if not self.api_key:
            return False, (
                "KUBEMEDIC_ANTHROPIC_API_KEY is unset. This must be an API key "
                "from console.anthropic.com -- a Claude.ai subscription login "
                "does not grant API access."
            )
        return True, f"Anthropic {self.model}"

    def _invocation(self) -> list[str]:
        return ["anthropic:messages", f"model={self.model}"]

    def _invoke(self, prompt: str) -> str:
        body = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            # Deterministic: an incident analysis should not vary run to run.
            "temperature": 0,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": prompt}],
        }
        request = urllib.request.Request(
            API_URL,
            data=json.dumps(body).encode(),
            headers={
                "Content-Type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": API_VERSION,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode())
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:400]
            if exc.code == 401:
                raise RuntimeError(
                    "Anthropic rejected the API key -- check "
                    "KUBEMEDIC_ANTHROPIC_API_KEY"
                ) from exc
            if exc.code == 429:
                raise RuntimeError(f"rate limited by Anthropic: {detail}") from exc
            raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
        except TimeoutError:
            raise
        except OSError as exc:
            raise RuntimeError(f"could not reach api.anthropic.com: {exc}") from exc

        blocks = payload.get("content") or []
        text = "".join(
            block.get("text", "")
            for block in blocks
            if isinstance(block, dict) and block.get("type") == "text"
        )
        # Empty text hands the raw payload to the shared parser, which will
        # fail cleanly rather than this guessing at a shape.
        return text or json.dumps(payload)
