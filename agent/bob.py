"""
Compatibility shim.

The IBM Bob invocation moved to agent/providers/ibm_bob.py when the reasoning
layer became pluggable. This module stays so existing imports keep working and
so there is still one obvious file to open when asking "how is Bob called".

New code should import from agent.providers.

    from agent.providers import get_provider
    result = get_provider().analyze(evidence, tickets, feedback)

The failure policy every caller depends on -- no credentials, auth rejected,
timeout, unparseable output, schema violation all converging on
analysis_source "unavailable" with no plan built -- now lives in
agent/providers/base.py and is shared by every provider rather than
reimplemented per engine.
"""
from __future__ import annotations

from typing import Any

from agent.providers import get_provider, unavailable_analysis
from agent.providers.base import BobResult, ProviderResult
from agent.providers.parsing import extract_json as _extract_json
from agent.providers.parsing import last_object as _last_object
from agent.providers.prompt import FEEDBACK_BLOCK, PROMPT_TEMPLATE, build_prompt


def analyze(
    evidence: dict[str, Any],
    tickets: list[dict[str, Any]],
    feedback: list[str] | None = None,
) -> ProviderResult:
    """Send structured evidence to the active reasoning provider."""
    return get_provider().analyze(evidence, tickets, feedback=feedback)


__all__ = [
    "BobResult",
    "FEEDBACK_BLOCK",
    "PROMPT_TEMPLATE",
    "ProviderResult",
    "analyze",
    "build_prompt",
    "unavailable_analysis",
    "_extract_json",
    "_last_object",
]
