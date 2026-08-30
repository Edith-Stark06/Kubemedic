"""
Defensive JSON extraction, shared by every provider.

Models wrap structured output: markdown fences, an envelope key, a sentence of
preamble, or a summary after the object. Each provider family does it slightly
differently, so this is written once and reused rather than rediscovered per
provider.

Nothing here is lenient about *content*. It finds the object; BobAnalysis
decides whether the object is acceptable.
"""
from __future__ import annotations

import json
from typing import Any

ENVELOPE_KEYS = ("result", "response", "output", "content", "text", "generated_text")
SHAPE_KEYS = ("hypotheses", "status", "recommended_action", "root_cause")


def extract_json(text: str) -> dict[str, Any]:
    """
    Recover the analysis object from a model response.

    Order: the whole payload as JSON; a known envelope field; then the last
    balanced top-level object that looks like our schema.
    """
    text = (text or "").strip()
    if not text:
        raise ValueError("empty response")

    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            for key in ENVELOPE_KEYS:
                inner = parsed.get(key)
                if isinstance(inner, str):
                    try:
                        return json.loads(inner.strip().strip("`"))
                    except json.JSONDecodeError:
                        return last_object(inner)
                if isinstance(inner, dict) and _looks_like_analysis(inner):
                    return inner
            if _looks_like_analysis(parsed):
                return parsed
    except json.JSONDecodeError:
        pass

    return last_object(text)


def _looks_like_analysis(candidate: dict[str, Any]) -> bool:
    return any(key in candidate for key in SHAPE_KEYS)


def last_object(text: str) -> dict[str, Any]:
    """
    Scan for the last balanced top-level JSON object that looks like our
    schema, ignoring braces inside strings.

    The *last* one, not the first: a model that explains itself before
    answering leaves example fragments earlier in the text.
    """
    best: dict[str, Any] | None = None
    depth = 0
    start = -1
    in_str = False
    esc = False

    for i, ch in enumerate(text):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start >= 0:
                try:
                    candidate = json.loads(text[start:i + 1])
                    if isinstance(candidate, dict) and _looks_like_analysis(candidate):
                        best = candidate
                except json.JSONDecodeError:
                    pass

    if best is None:
        raise ValueError("no schema-shaped JSON object found in output")
    return best
