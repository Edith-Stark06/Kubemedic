"""
IBM Bob adapter — the only module in KubeMedic that knows how Bob is invoked.

Everything downstream (reasoning, correlation, plan, executor, verification)
depends on the BobAnalysis model, never on this file's internals. Swapping the
invocation mechanism means editing this file and nothing else.

INVOCATION — VERIFIED 2026-08-29
---------------------------------
IBM Bob on this machine is the Antigravity IDE (bobide.cmd / bobide-tunnel.exe)
installed at D:\\Documents\\BoB\\IBM Bob\\bin\\.

IBM Bob v1.126.0+bob2.0.3 has NO headless subprocess stdout mode:

  bobide.cmd chat -m <mode> "<prompt>"   → opens GUI, no stdout, exit 0
  bobide.cmd                             → opens GUI window
  bobide-tunnel.exe agent host           → starts local HTTP server BUT requires
                                          the IDE to be running as supervisor

The only programmatic API is the cloud RemoteAgent REST endpoint:
  POST https://cloud.manufact.com/api/v1/chats
  POST https://cloud.manufact.com/api/v1/chats/{id}/execute
  Header: x-api-key: <KUBEMEDIC_BOB_API_KEY>

_build_argv() is intentionally left returning [] to signal "no subprocess path".
The analyze() function checks BOB_API_KEY and uses the REST API when available,
otherwise returns bob_unavailable — it never fabricates a result.

FAILURE POLICY
--------------
If Bob is unavailable (key absent, network error, timeout) we return
status="bob_unavailable". We never synthesize an analysis and label it as
Bob's. The dashboard surfaces the outage, the incident does not advance, and
the audit record says so.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("kubemedic.bob")

BOB_MODE = os.getenv("KUBEMEDIC_BOB_MODE", "kubemedic-analyst")
BOB_TIMEOUT = int(os.getenv("KUBEMEDIC_BOB_TIMEOUT_SECONDS", "180"))
BOB_BINARY = os.getenv("KUBEMEDIC_BOB_BINARY", "bobide")
WORKSPACE = Path(os.getenv("KUBEMEDIC_WORKSPACE", ".")).resolve()

# Cloud REST API (set KUBEMEDIC_BOB_API_KEY to enable the RemoteAgent path).
# Get your key from https://cloud.manufact.com after logging in with IBM Bob.
BOB_API_KEY = os.getenv("KUBEMEDIC_BOB_API_KEY", "")
BOB_API_BASE = os.getenv("KUBEMEDIC_BOB_API_BASE", "https://cloud.manufact.com")
BOB_AGENT_ID = os.getenv("KUBEMEDIC_BOB_AGENT_ID", "")  # agent ID from cloud console


class BobUnavailable(RuntimeError):
    """Bob could not be reached, timed out, or returned unparseable output."""


@dataclass
class BobResult:
    ok: bool
    analysis: dict[str, Any] | None
    raw_stdout: str
    invocation: list[str]
    duration_ms: int
    error: str | None = None
    invoked_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def audit_entry(self) -> dict[str, Any]:
        """Structured record for the audit trail. Never a model-written summary."""
        return {
            "stage": "BOB",
            "invoked_at": self.invoked_at,
            "mode": BOB_MODE,
            "invocation": self.invocation,
            "duration_ms": self.duration_ms,
            "ok": self.ok,
            "error": self.error,
            "analysis_source": "ibm-bob" if self.ok else "unavailable",
        }


PROMPT_TEMPLATE = """\
Analyze this Kubernetes incident using the incident-correlation skill.

The evidence below was collected by the KubeMedic evidence MCP server. Treat it
as the complete set of observed facts. Do not assume anything not present here.

<evidence>
{evidence}
</evidence>

<open_tickets>
{tickets}
</open_tickets>

Allowlisted actions: rollback_deployment, restart_deployment, scale_workload.
No other action exists. If none fits, recommend null and say what a human
should do instead.

Return exactly one JSON object matching
.bob/skills/incident-correlation/references/evidence-schema.md.
No prose, no markdown fences.
"""


def _build_argv(prompt: str) -> list[str]:
    """
    IBM Bob v1.126.0 (Antigravity IDE / bobide) has no headless stdout mode.
    bobide.cmd chat opens the GUI with zero stdout. There is no subprocess path.
    Returns [] to signal "no subprocess invocation available" to analyze().
    The REST API path in analyze() is used instead when BOB_API_KEY is set.
    """
    return []


def _find_binary() -> str | None:
    """Return the resolved path to the bobide binary, or None."""
    # Honour the env override first
    binary = BOB_BINARY
    resolved = shutil.which(binary)
    if resolved:
        return resolved
    # Common install location on Windows when PATH is stale
    win_path = r"D:\Documents\BoB\IBM Bob\bin\bobide.cmd"
    if os.path.isfile(win_path):
        return win_path
    return None


def _rest_analyze(
    prompt: str,
    started: datetime,
) -> BobResult:
    """
    Use the IBM Bob cloud RemoteAgent REST API when BOB_API_KEY is set.

    Protocol (from extension.js RemoteAgent class):
      1. POST {base}/api/v1/chats  body={title, agent_id, type}  → {id}
      2. POST {base}/api/v1/chats/{id}/execute  body={query, max_steps} → result

    Requires KUBEMEDIC_BOB_API_KEY and KUBEMEDIC_BOB_AGENT_ID.
    """
    if not BOB_API_KEY:
        return _fail(
            "IBM Bob REST API not configured: set KUBEMEDIC_BOB_API_KEY and "
            "KUBEMEDIC_BOB_AGENT_ID in the environment to enable the cloud path",
            ["rest-api", BOB_API_BASE],
            started,
        )
    if not BOB_AGENT_ID:
        return _fail(
            "IBM Bob REST API not configured: KUBEMEDIC_BOB_AGENT_ID is unset. "
            "Find your agent ID in the IBM Bob cloud console.",
            ["rest-api", BOB_API_BASE],
            started,
        )

    headers = {
        "Content-Type": "application/json",
        "x-api-key": BOB_API_KEY,
    }
    invocation = [f"REST:{BOB_API_BASE}/api/v1/chats", f"agent_id={BOB_AGENT_ID}"]

    # Step 1: create chat session
    chat_url = f"{BOB_API_BASE}/api/v1/chats"
    chat_body = json.dumps({
        "title": f"KubeMedic incident analysis — mode:{BOB_MODE}",
        "agent_id": BOB_AGENT_ID,
        "type": "agent_execution",
    }).encode()
    try:
        req = urllib.request.Request(chat_url, data=chat_body, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=30) as resp:
            chat_id = json.loads(resp.read().decode()).get("id")
        if not chat_id:
            return _fail("IBM Bob REST: chat creation returned no id", invocation, started)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")[:400]
        return _fail(f"IBM Bob REST chat create {exc.code}: {body}", invocation, started)
    except Exception as exc:
        return _fail(f"IBM Bob REST chat create failed: {exc}", invocation, started)

    # Step 2: execute in the chat
    run_url = f"{BOB_API_BASE}/api/v1/chats/{chat_id}/execute"
    run_body = json.dumps({"query": prompt, "max_steps": 20}).encode()
    try:
        req = urllib.request.Request(run_url, data=run_body, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=BOB_TIMEOUT) as resp:
            raw = resp.read().decode()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")[:400]
        if exc.code == 401:
            return _fail("IBM Bob REST: authentication failed — check KUBEMEDIC_BOB_API_KEY", invocation, started)
        return _fail(f"IBM Bob REST execute {exc.code}: {body}", invocation, started)
    except Exception as exc:
        return _fail(f"IBM Bob REST execute failed: {exc}", invocation, started)

    elapsed = _ms(started)
    try:
        result_data = json.loads(raw)
    except json.JSONDecodeError:
        result_data = raw  # will be handled by _extract_json on the raw string

    # The execute endpoint returns the final result directly (not wrapped in raw)
    try:
        if isinstance(result_data, dict):
            # Unwrap {"result": ...} envelope if present
            if "result" in result_data:
                inner = result_data["result"]
                if isinstance(inner, dict):
                    analysis = inner
                elif isinstance(inner, str):
                    analysis = _extract_json(inner)
                else:
                    analysis = _extract_json(raw)
            elif "hypotheses" in result_data or "status" in result_data:
                analysis = result_data
            else:
                analysis = _extract_json(raw)
        else:
            analysis = _extract_json(str(result_data))
    except ValueError as exc:
        return _fail(
            f"IBM Bob REST returned unparseable output: {exc}",
            invocation, started, raw=raw,
        )

    analysis.setdefault("analysis_source", "ibm-bob")
    log.info("[BOB] REST ok in %dms", elapsed)
    return BobResult(
        ok=True, analysis=analysis, raw_stdout=raw,
        invocation=invocation, duration_ms=elapsed,
    )


def analyze(evidence: dict[str, Any], tickets: list[dict[str, Any]]) -> BobResult:
    """Send structured evidence to IBM Bob. Return its structured analysis.

    Invocation order:
      1. If BOB_API_KEY is set → use IBM Bob cloud REST API (RemoteAgent).
      2. Otherwise → bob_unavailable (no fabrication, ever).

    IBM Bob v1.126.0 (bobide) is a GUI IDE with no headless subprocess mode.
    The subprocess path (_build_argv) returns [] for documentation purposes.
    """
    started = datetime.now(timezone.utc)

    prompt = PROMPT_TEMPLATE.format(
        evidence=json.dumps(evidence, indent=2, default=str),
        tickets=json.dumps(tickets, indent=2, default=str),
    )

    # REST path: use when API key is configured
    if BOB_API_KEY:
        log.info("[BOB] invoking via REST API mode=%s timeout=%ss", BOB_MODE, BOB_TIMEOUT)
        return _rest_analyze(prompt, started)

    # No subprocess path exists for this IBM Bob version.
    # Log the binary search so the error is actionable.
    binary_path = _find_binary()
    binary_note = (
        f"found at {binary_path} but has no headless stdout mode"
        if binary_path
        else f"'{BOB_BINARY}' not found on PATH"
    )
    return _fail(
        f"IBM Bob unavailable: {binary_note}. "
        "Set KUBEMEDIC_BOB_API_KEY + KUBEMEDIC_BOB_AGENT_ID to enable the REST path.",
        [],
        started,
    )


def _extract_json(stdout: str) -> dict[str, Any]:
    """
    Headless output may wrap the answer in an envelope or include reasoning
    steps. Try, in order: the whole payload; a known envelope field; the last
    balanced JSON object in the text.
    """
    text = stdout.strip()
    if not text:
        raise ValueError("empty stdout")

    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            for key in ("result", "response", "output", "content", "text"):
                inner = parsed.get(key)
                if isinstance(inner, str):
                    try:
                        return json.loads(inner.strip().strip("`"))
                    except json.JSONDecodeError:
                        return _last_object(inner)
                if isinstance(inner, dict) and "hypotheses" in inner:
                    return inner
            if "hypotheses" in parsed or "status" in parsed:
                return parsed
    except json.JSONDecodeError:
        pass

    return _last_object(text)


def _last_object(text: str) -> dict[str, Any]:
    """Scan for the last balanced top-level JSON object, ignoring braces in strings."""
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
                    cand = json.loads(text[start:i + 1])
                    if isinstance(cand, dict) and (
                        "hypotheses" in cand or "status" in cand
                    ):
                        best = cand
                except json.JSONDecodeError:
                    pass
    if best is None:
        raise ValueError("no schema-shaped JSON object found in output")
    return best


def _ms(started: datetime) -> int:
    return int((datetime.now(timezone.utc) - started).total_seconds() * 1000)


def _redact(argv: list[str]) -> list[str]:
    """Never log the full prompt (it carries cluster detail) or any secret."""
    return [a if len(a) < 120 else f"<prompt {len(a)} chars>" for a in argv]


def _fail(msg: str, argv: list[str], started: datetime, raw: str = "") -> BobResult:
    log.error("[BOB] %s", msg)
    return BobResult(
        ok=False, analysis=None, raw_stdout=raw,
        invocation=_redact(argv), duration_ms=_ms(started), error=msg,
    )


def unavailable_analysis(reason: str) -> dict[str, Any]:
    """
    The shape reasoning.py substitutes when Bob is down. Note
    analysis_source is 'unavailable', never 'ibm-bob' — the dashboard renders
    this as "IBM Bob unavailable" and the incident does not advance to a plan.
    """
    return {
        "schema_version": "1.0",
        "analysis_source": "unavailable",
        "status": "bob_unavailable",
        "reason": reason,
        "hypotheses": [],
        "recommended_action": None,
        "requires_human_approval": True,
    }
