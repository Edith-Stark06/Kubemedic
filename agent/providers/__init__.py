"""
Reasoning provider registry.

One switch selects the engine; everything downstream is unchanged because every
provider returns the same validated BobAnalysis contract:

    KUBEMEDIC_REASONING_PROVIDER=ibm-bob | watsonx | anthropic | manual

Per-provider credentials are namespaced and resolved through agent/secrets.py:

    KUBEMEDIC_BOB_API_KEY / _AGENT_ID / _API_BASE / _MODE
    KUBEMEDIC_WATSONX_API_KEY / _PROJECT_ID / _URL / _MODEL_ID
    KUBEMEDIC_ANTHROPIC_API_KEY / _MODEL
    KUBEMEDIC_MANUAL_ANALYSIS_FILE

An unknown provider name is a hard error. Silently falling back to a default
because a name was misspelled is the same failure the MCP --profile guard
exists to prevent: the system would look configured while serving something
else.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Callable

from agent.providers.base import (
    BaseProvider,
    BobResult,
    ProviderResult,
    ReasoningProvider,
    unavailable_analysis,
)
from agent.providers.prompt import build_prompt

log = logging.getLogger("kubemedic.providers")

DEFAULT_PROVIDER = "ibm-bob"

# Imported lazily so a missing optional dependency in one provider cannot stop
# the process starting with a different one selected.
_FACTORIES: dict[str, Callable[[], BaseProvider]] = {}


def _register() -> None:
    if _FACTORIES:
        return

    def ibm_bob() -> BaseProvider:
        from agent.providers.ibm_bob import IBMBobProvider
        return IBMBobProvider()

    def watsonx() -> BaseProvider:
        from agent.providers.watsonx import WatsonxProvider
        return WatsonxProvider()

    def anthropic() -> BaseProvider:
        from agent.providers.anthropic import AnthropicProvider
        return AnthropicProvider()

    def manual() -> BaseProvider:
        from agent.providers.manual import ManualProvider
        return ManualProvider()

    _FACTORIES.update({
        "ibm-bob": ibm_bob,
        "bob": ibm_bob,
        "watsonx": watsonx,
        "anthropic": anthropic,
        "claude": anthropic,
        "manual": manual,
    })


def provider_names() -> list[str]:
    _register()
    return ["ibm-bob", "watsonx", "anthropic", "manual"]


def configured_provider_name() -> str:
    return (
        os.getenv("KUBEMEDIC_REASONING_PROVIDER") or DEFAULT_PROVIDER
    ).strip().lower()


_active: BaseProvider | None = None
_active_name: str | None = None


def get_provider(name: str | None = None) -> BaseProvider:
    """
    The active reasoning provider. Cached per name so usage counters accumulate
    across an incident rather than resetting on every call.
    """
    global _active, _active_name
    _register()

    requested = (name or configured_provider_name()).strip().lower()
    if requested not in _FACTORIES:
        raise SystemExit(
            f"Unknown reasoning provider {requested!r}. "
            f"Valid: {', '.join(provider_names())}. "
            "Set KUBEMEDIC_REASONING_PROVIDER."
        )

    if _active is not None and _active_name == requested:
        return _active

    provider = _FACTORIES[requested]()
    _active, _active_name = provider, requested
    log.info("[PROVIDERS] active reasoning provider: %s", provider.id)
    return provider


def reset_provider_cache() -> None:
    """Test hook. Production code never needs this."""
    global _active, _active_name
    _active = _active_name = None


def provider_status() -> dict[str, Any]:
    """
    Configuration and usage for every registered provider.

    Deliberately does NOT probe the network. A health endpoint that reaches out
    to a model API turns a slow third party into a red dashboard and puts it in
    the path of a liveness check. Configuration is checked here; reachability is
    discovered by running an incident, where a failure is handled rather than
    merely reported.
    """
    _register()
    from agent.secrets import get_secrets

    saved = (_active, _active_name)
    entries = []
    try:
        for known in provider_names():
            try:
                reset_provider_cache()
                usage = get_provider(known).usage()
                # The registry key, not the provider id. `manual` reports its
                # id as ibm-bob -- the analysis really is Bob's -- so without
                # this the status list shows ibm-bob twice.
                usage["name"] = known
                entries.append(usage)
            except Exception as exc:        # status must never raise
                entries.append({
                    "name": known,
                    "provider": known,
                    "configured": False,
                    "detail": f"could not construct: {exc}",
                })
    finally:
        globals()["_active"], globals()["_active_name"] = saved

    return {
        "active": configured_provider_name(),
        "default": DEFAULT_PROVIDER,
        "secrets_backend": get_secrets().describe(),
        "providers": entries,
    }


__all__ = [
    "BaseProvider",
    "BobResult",
    "ProviderResult",
    "ReasoningProvider",
    "build_prompt",
    "configured_provider_name",
    "get_provider",
    "provider_names",
    "provider_status",
    "reset_provider_cache",
    "unavailable_analysis",
]
