"""
Google Gemini provider — development and demo fallback.

WHY IT EXISTS
-------------
KubeMedic's reasoning path is IBM. But the IBM engines are unreachable on this
account: the watsonx WML instance is Inactive, and the Bob REST endpoint
returns 401 on every path tried. Without a working fallback, a fresh clone has
no reasoning at all, and a demo cannot show the loop.

So this is a *fallback*, not the default. `AI_PRIMARY_PROVIDER` stays IBM;
Gemini answers only when the primary is unavailable and
`AI_FALLBACK_ENABLED=true`.

TRANSPORT
---------
The REST generateContent endpoint over urllib, matching every other provider
here -- no SDK, no new dependency, nothing to install in a clean checkout.

    POST https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent

The key travels in the `x-goog-api-key` header rather than the query string,
so it cannot end up in a proxy log or an error message containing the URL.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from agent.providers.base import BaseProvider
from agent.providers.prompt import SYSTEM_PROMPT
from agent.secrets import get_secrets

API_BASE = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_MODEL = "gemini-2.0-flash"


class GeminiProvider(BaseProvider):
    id = "gemini"
    display_name = "Google Gemini"

    def __init__(self) -> None:
        super().__init__()
        secrets = get_secrets()
        # GEMINI_API_KEY is the name the Google tooling uses; the namespaced
        # form is accepted too so every provider can be configured the same way.
        self.api_key = (
            secrets.get("KUBEMEDIC_GEMINI_API_KEY")
            or secrets.get("GEMINI_API_KEY")
        )
        self.model = (
            os.getenv("KUBEMEDIC_GEMINI_MODEL")
            or os.getenv("GEMINI_MODEL")
            or DEFAULT_MODEL
        )
        self.timeout = int(os.getenv("KUBEMEDIC_GEMINI_TIMEOUT_SECONDS", "180"))
        self.max_tokens = int(os.getenv("KUBEMEDIC_GEMINI_MAX_TOKENS", "4000"))

    def is_configured(self) -> tuple[bool, str]:
        if not self.api_key:
            return False, (
                "GEMINI_API_KEY is unset. Get a key from "
                "https://aistudio.google.com/apikey and export it."
            )
        return True, f"Gemini {self.model}"

    def _invocation(self) -> list[str]:
        # The key is never part of this -- it goes in a header, and this list
        # lands in the audit record.
        return [f"gemini:{API_BASE}", f"model={self.model}"]

    def _invoke(self, prompt: str) -> str:
        url = f"{API_BASE}/models/{self.model}:generateContent"
        body = {
            "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                # Deterministic: an incident analysis should not vary run to run.
                "temperature": 0,
                "maxOutputTokens": self.max_tokens,
                "responseMimeType": "application/json",
            },
        }
        request = urllib.request.Request(
            url,
            data=json.dumps(body).encode(),
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": self.api_key,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode())
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:400]
            if exc.code in (401, 403):
                raise RuntimeError(
                    f"Gemini rejected the API key (HTTP {exc.code})"
                ) from exc
            if exc.code == 429:
                raise RuntimeError(f"rate limited by Gemini: {detail}") from exc
            raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
        except TimeoutError:
            raise
        except OSError as exc:
            raise RuntimeError(
                f"could not reach generativelanguage.googleapis.com: {exc}"
            ) from exc

        candidates = payload.get("candidates") or []
        if candidates:
            parts = (candidates[0].get("content") or {}).get("parts") or []
            text = "".join(p.get("text", "") for p in parts)
            if text.strip():
                return text
            # A blocked or truncated answer has a reason worth surfacing rather
            # than letting the parser fail with "no JSON found".
            reason = candidates[0].get("finishReason")
            if reason and reason != "STOP":
                raise RuntimeError(f"Gemini returned no content ({reason})")

        blocked = (payload.get("promptFeedback") or {}).get("blockReason")
        if blocked:
            raise RuntimeError(f"Gemini blocked the prompt ({blocked})")

        # Hand the whole payload to the shared parser rather than guessing.
        return json.dumps(payload)
