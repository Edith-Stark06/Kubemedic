"""
IBM watsonx.ai provider.

Two calls:

  1. IAM token exchange
     POST https://iam.cloud.ibm.com/identity/token
     grant_type=urn:ibm:params:oauth:grant-type:apikey&apikey=...
     Returns a bearer token, roughly one hour. Cached with its expiry, because
     re-exchanging on every incident puts IAM in the reasoning path.

  2. Inference
     POST {url}/ml/v1/text/chat?version=2023-05-29
     {model_id, project_id, messages}

VERIFY THE API SHAPE against current IBM documentation before depending on it.
Endpoint versions move, and this was written from the published shape rather
than from a live call.

Granite models are conversational and will wrap JSON in prose or fences.
providers/parsing.py handles that, which is exactly why it is shared.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

from agent.providers.base import BaseProvider
from agent.providers.prompt import SYSTEM_PROMPT
from agent.secrets import get_secrets

IAM_URL = "https://iam.cloud.ibm.com/identity/token"
API_VERSION = "2023-05-29"


class WatsonxProvider(BaseProvider):
    id = "watsonx"
    display_name = "IBM watsonx.ai"

    def __init__(self) -> None:
        super().__init__()
        secrets = get_secrets()
        self.api_key = secrets.get("KUBEMEDIC_WATSONX_API_KEY")
        self.project_id = secrets.get("KUBEMEDIC_WATSONX_PROJECT_ID")
        self.url = (
            os.getenv("KUBEMEDIC_WATSONX_URL")
            or "https://us-south.ml.cloud.ibm.com"
        ).rstrip("/")
        self.model_id = os.getenv(
            "KUBEMEDIC_WATSONX_MODEL_ID", "ibm/granite-3-8b-instruct"
        )
        self.timeout = int(os.getenv("KUBEMEDIC_WATSONX_TIMEOUT_SECONDS", "180"))
        self.max_tokens = int(os.getenv("KUBEMEDIC_WATSONX_MAX_TOKENS", "4000"))
        self._token: str | None = None
        self._token_expires_at = 0.0

    def is_configured(self) -> tuple[bool, str]:
        if not self.api_key:
            return False, "KUBEMEDIC_WATSONX_API_KEY is unset."
        if not self.project_id:
            return False, (
                "KUBEMEDIC_WATSONX_PROJECT_ID is unset. A watsonx.ai project "
                "with the runtime service is required."
            )
        return True, f"watsonx.ai {self.model_id} at {self.url}"

    def _invocation(self) -> list[str]:
        return [f"watsonx:{self.url}", f"model={self.model_id}"]

    def _bearer(self) -> str:
        # 60s of slack so a token cannot expire between the check and the call.
        if self._token and time.time() < self._token_expires_at - 60:
            return self._token

        body = urllib.parse.urlencode({
            "grant_type": "urn:ibm:params:oauth:grant-type:apikey",
            "apikey": self.api_key,
        }).encode()
        request = urllib.request.Request(
            IAM_URL,
            data=body,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.loads(response.read().decode())
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:300]
            raise RuntimeError(
                f"IAM token exchange failed (HTTP {exc.code}): {detail}"
            ) from exc
        except OSError as exc:
            raise RuntimeError(f"could not reach IBM IAM: {exc}") from exc

        token = payload.get("access_token")
        if not token:
            raise RuntimeError("IAM returned no access_token")
        self._token = token
        self._token_expires_at = time.time() + int(payload.get("expires_in", 3600))
        return token

    def _invoke(self, prompt: str) -> str:
        url = f"{self.url}/ml/v1/text/chat?version={API_VERSION}"
        body = {
            "model_id": self.model_id,
            "project_id": self.project_id,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": self.max_tokens,
            # Deterministic: an incident analysis should not vary run to run.
            "temperature": 0,
        }
        request = urllib.request.Request(
            url,
            data=json.dumps(body).encode(),
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Authorization": f"Bearer {self._bearer()}",
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
                    f"watsonx rejected the credentials (HTTP {exc.code}): {detail}"
                ) from exc
            raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
        except TimeoutError:
            raise
        except OSError as exc:
            raise RuntimeError(f"could not reach {self.url}: {exc}") from exc

        choices = payload.get("choices") or []
        if choices:
            content = (choices[0].get("message") or {}).get("content")
            if isinstance(content, str) and content.strip():
                return content
        # Older text/generation shape, kept as a fallback.
        results = payload.get("results") or []
        if results and results[0].get("generated_text"):
            return results[0]["generated_text"]
        # Hand the whole payload to the shared parser rather than guessing.
        return json.dumps(payload)
