"""
Secret resolution seam.

Every credential in KubeMedic is read through a SecretProvider rather than
os.getenv directly, so where secrets live is a deployment decision and not a
code change. The backend is chosen with KUBEMEDIC_SECRETS_BACKEND.

Two rules hold for every backend:

  1. A secret value is never logged, never returned by a health endpoint, and
     never included in an audit record. `describe()` names the source, not the
     contents.
  2. A missing secret is a normal, reportable condition -- not an exception.
     A provider that cannot find its key must be able to say so calmly, because
     the whole system is built to report an unavailable reasoner rather than
     fabricate around one.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Protocol, runtime_checkable

log = logging.getLogger("kubemedic.secrets")

BACKEND = os.getenv("KUBEMEDIC_SECRETS_BACKEND", "env").strip().lower()


@runtime_checkable
class SecretProvider(Protocol):
    def get(self, name: str) -> str | None: ...
    def describe(self) -> str: ...


class EnvSecrets:
    """Process environment. The default, and what a developer expects."""

    def get(self, name: str) -> str | None:
        value = os.getenv(name)
        return value.strip() if value else None

    def describe(self) -> str:
        return "env"


class FileSecrets:
    """
    One file per secret, the Docker/Kubernetes mounted-secret convention:
    /run/secrets/KUBEMEDIC_WATSONX_API_KEY holds the value and nothing else.

    Falls through to the environment so a partial migration works.
    """

    def __init__(self, root: str | None = None) -> None:
        self.root = Path(root or os.getenv("KUBEMEDIC_SECRETS_DIR", "/run/secrets"))
        self._env = EnvSecrets()

    def get(self, name: str) -> str | None:
        path = self.root / name
        try:
            if path.is_file():
                return path.read_text(encoding="utf-8").strip() or None
        except OSError as exc:
            log.warning("[SECRETS] could not read %s: %s", path, exc)
        return self._env.get(name)

    def describe(self) -> str:
        return f"file:{self.root}"


class KubernetesSecrets:
    """
    Read a Kubernetes Secret through the client the project already depends on.

    Values are fetched once and cached for the process lifetime: a Secret is
    not expected to rotate mid-incident, and re-reading per lookup would put
    the API server in the path of every reasoning call.
    """

    def __init__(self, name: str | None = None, namespace: str | None = None) -> None:
        self.name = name or os.getenv("KUBEMEDIC_SECRETS_NAME", "kubemedic-secrets")
        self.namespace = namespace or os.getenv("KUBEMEDIC_NAMESPACE", "opspilot")
        self._cache: dict[str, str] | None = None
        self._env = EnvSecrets()

    def _load(self) -> dict[str, str]:
        if self._cache is not None:
            return self._cache
        self._cache = {}
        try:
            import base64

            from kubernetes import client, config

            try:
                config.load_incluster_config()
            except Exception:
                config.load_kube_config()
            secret = client.CoreV1Api().read_namespaced_secret(
                self.name, self.namespace
            )
            for key, encoded in (secret.data or {}).items():
                self._cache[key] = base64.b64decode(encoded).decode("utf-8").strip()
            log.info(
                "[SECRETS] loaded %d key(s) from %s/%s",
                len(self._cache), self.namespace, self.name,
            )
        except Exception as exc:
            # Not fatal: fall through to the environment. A provider will
            # report itself unconfigured, which is a state the system handles.
            log.warning(
                "[SECRETS] could not read Secret %s/%s: %s",
                self.namespace, self.name, exc,
            )
        return self._cache

    def get(self, name: str) -> str | None:
        return self._load().get(name) or self._env.get(name)

    def describe(self) -> str:
        return f"k8s:{self.namespace}/{self.name}"


class VaultSecrets:
    """
    HashiCorp Vault / IBM Cloud Secrets Manager.

    Deliberately not implemented. The seam exists so adding it is a new class
    and one registry entry rather than a refactor; selecting this backend
    fails loudly rather than silently serving nothing.
    """

    def get(self, name: str) -> str | None:
        raise NotImplementedError(
            "The vault secrets backend is a documented adapter point, not an "
            "implementation. Use env, file or k8s, or implement VaultSecrets."
        )

    def describe(self) -> str:
        return "vault (not implemented)"


_BACKENDS = {
    "env": EnvSecrets,
    "dotenv": EnvSecrets,   # .env is loaded into the environment by the shell
    "file": FileSecrets,
    "k8s": KubernetesSecrets,
    "kubernetes": KubernetesSecrets,
    "vault": VaultSecrets,
}

_active: SecretProvider | None = None


def get_secrets(backend: str | None = None) -> SecretProvider:
    """The process-wide secret provider. Cached; pass a backend to override."""
    global _active
    if backend is None and _active is not None:
        return _active

    name = (backend or BACKEND).strip().lower()
    if name not in _BACKENDS:
        raise SystemExit(
            f"Unknown secrets backend {name!r}. "
            f"Valid: {', '.join(sorted(set(_BACKENDS)))}."
        )
    provider = _BACKENDS[name]()
    if backend is None:
        _active = provider
    return provider


def reset_secrets_cache() -> None:
    """Test hook. Production code never needs this."""
    global _active
    _active = None


def redact(value: str | None) -> str:
    """
    Render a secret for a human without disclosing it.

    Health endpoints and logs use this. Short values are reported as set/unset
    rather than partially revealed -- a four-character prefix of an eight
    character secret is a meaningful leak.
    """
    if not value:
        return "unset"
    if len(value) < 12:
        return "set (short)"
    return f"set ({value[:4]}...{value[-2:]}, {len(value)} chars)"
