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

# `auto` picks the first configured engine, ending at the host IDE session --
# so a fresh clone with no credentials still has a working reasoning path.
DEFAULT_PROVIDER = "auto"

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

    def host() -> BaseProvider:
        from agent.providers.host import HostSessionProvider
        return HostSessionProvider()

    def gemini() -> BaseProvider:
        from agent.providers.gemini import GeminiProvider
        return GeminiProvider()

    _FACTORIES.update({
        "ibm-bob": ibm_bob,
        "bob": ibm_bob,
        "watsonx": watsonx,
        "anthropic": anthropic,
        "claude": anthropic,
        "manual": manual,
        "host": host,
        "ide": host,             # convenience alias
        "gemini": gemini,
    })


def provider_names() -> list[str]:
    _register()
    return ["ibm-bob", "watsonx", "anthropic", "gemini", "manual", "host"]


# Tried in order when the provider is `auto`. The IBM engines come first
# because this is an IBM Bob project; `host` is last because it always
# succeeds -- it needs no credential, only somebody to answer -- so anything
# after it would be unreachable.
AUTO_ORDER = ("ibm-bob", "watsonx", "anthropic", "gemini", "manual", "host")


def resolve_auto() -> str:
    """
    First configured provider wins.

    Without this, a machine with no API keys has no working reasoning path at
    all, and the honest fallback -- asking the agentic IDE that is already
    sitting in the workspace -- is exactly what an operator would do by hand.
    """
    _register()
    for name in AUTO_ORDER:
        try:
            if _FACTORIES[name]().is_configured()[0]:
                return name
        except Exception:                # a broken provider is simply skipped
            continue
    return "host"


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
    if requested == "auto":
        requested = resolve_auto()
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

    saved_provider, saved_name = _active, _active_name
    entries = []
    try:
        for known in provider_names():
            try:
                if saved_provider is not None and known == saved_name:
                    # Report the live instance, not a fresh one. Constructing a
                    # new provider here would zero the call and failure
                    # counters this endpoint exists to surface.
                    usage = saved_provider.usage()
                else:
                    reset_provider_cache()
                    usage = get_provider(known).usage()
                # The registry key, not the provider id. `manual` reports its
                # id as ibm-bob -- the analysis really is Bob's -- so without
                # this the status list would show ibm-bob twice.
                usage["name"] = known
                usage["active"] = known == (saved_name or configured_provider_name())
                entries.append(usage)
            except Exception as exc:        # status must never raise
                entries.append({
                    "name": known,
                    "provider": known,
                    "configured": False,
                    "active": False,
                    "detail": f"could not construct: {exc}",
                })
    finally:
        globals()["_active"], globals()["_active_name"] = saved_provider, saved_name

    return {
        "active": configured_provider_name(),
        "default": DEFAULT_PROVIDER,
        "secrets_backend": get_secrets().describe(),
        "providers": entries,
    }


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip().lower()


def fallback_enabled() -> bool:
    return _env("AI_FALLBACK_ENABLED", "true") not in ("false", "0", "no")


def primary_name() -> str:
    """
    The engine that answers first.

    AI_PRIMARY_PROVIDER wins; otherwise the KUBEMEDIC_ name, for continuity
    with the existing configuration. `auto` is resolved to a concrete name so
    health output and audit records never say "auto" -- a reader needs to know
    which engine actually answered.
    """
    name = _env("AI_PRIMARY_PROVIDER") or configured_provider_name()
    return resolve_auto() if name == "auto" else name


def fallback_name() -> str:
    return _env("AI_FALLBACK_PROVIDER", "gemini")


def analyze_with_fallback(
    evidence: dict[str, Any],
    tickets: list[dict[str, Any]],
    feedback: list[str] | None = None,
) -> "ProviderResult":
    """
    Try the primary engine; on failure fall to the configured fallback.

    Two rules this deliberately follows.

    A failure is never swallowed. The reason the primary could not answer is
    logged and carried into the returned result, so an audit record shows that
    IBM was tried and why it did not answer -- not merely that Gemini spoke.

    And a failure is never retried in place. An invalid credential is invalid
    on the second attempt too; retrying it turns one clear 401 into a retry
    storm against someone else's service.
    """
    primary = get_provider(primary_name())
    result = primary.analyze(evidence, tickets, feedback)
    if result.ok:
        return result

    if not fallback_enabled():
        log.warning(
            "[PROVIDERS] %s unavailable and AI_FALLBACK_ENABLED is false", primary.id
        )
        return result

    secondary_name = fallback_name()
    if secondary_name in (primary.id, primary_name()):
        return result                       # nothing to fall back to

    try:
        secondary = get_provider(secondary_name)
    except SystemExit:
        log.error("[PROVIDERS] fallback %r is not a known provider", secondary_name)
        return result

    configured, why = secondary.is_configured()
    if not configured:
        log.warning(
            "[PROVIDERS] %s unavailable; fallback %s is not configured: %s",
            primary.id, secondary.id, why,
        )
        return result

    # Safe by construction: the message names the provider and the failure
    # class, never a credential -- `result.error` is built from status codes
    # and provider names, and `invocation` excludes the prompt and the key.
    log.warning(
        "[PROVIDERS] %s unavailable: %s. Falling back to %s because "
        "AI_FALLBACK_ENABLED=true.",
        primary.id, result.error, secondary.id,
    )
    fallback_result = secondary.analyze(evidence, tickets, feedback)
    fallback_result.invocation = [
        *fallback_result.invocation,
        f"fallback-from={primary.id}",
    ]
    return fallback_result


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
    "resolve_auto",
    "analyze_with_fallback",
    "fallback_enabled",
    "fallback_name",
    "primary_name",
    "unavailable_analysis",
]
