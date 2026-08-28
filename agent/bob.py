"""
IBM Bob adapter — the only module in KubeMedic that knows how Bob is invoked.

Everything downstream (reasoning, correlation, plan, executor, verification)
depends on the BobAnalysis model, never on this file's internals. Swapping the
invocation mechanism means editing this file and nothing else.

INVOCATION
----------
Bob Shell runs headless. Two CLI generations exist; we probe for both:

    Shell v2:  bob run --mode <slug> --output-format json "<prompt>"
    Shell v1:  bob -p "<prompt>"

>>> VERIFY THE EXACT FLAGS AGAINST `bob run --help` ON YOUR MACHINE AND FIX
>>> `_build_argv` BELOW. Everything else in this file is invocation-agnostic.

The analyst mode is read-only by construction (see .bob/custom_modes.yaml),
so a Bob invocation cannot mutate the cluster no matter what it returns.

FAILURE POLICY
--------------
If Bob is unavailable we return status="bob_unavailable". We never synthesize
an analysis and label it as Bob's. The dashboard surfaces the outage, the
incident does not advance, and the audit record says so.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("kubemedic.bob")

BOB_MODE = os.getenv("KUBEMEDIC_BOB_MODE", "kubemedic-analyst")
BOB_TIMEOUT = int(os.getenv("KUBEMEDIC_BOB_TIMEOUT_SECONDS", "180"))
BOB_BINARY = os.getenv("KUBEMEDIC_BOB_BINARY", "bob")
WORKSPACE = Path(os.getenv("KUBEMEDIC_WORKSPACE", ".")).resolve()


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
    >>> ADJUST HERE after checking `bob run --help` / `bob --help`.
    Probe order: Shell v2 `bob run`, then Shell v1 `bob -p`.
    """
    if _supports_subcommand("run"):
        return [
            BOB_BINARY, "run",
            "--mode", BOB_MODE,
            "--output-format", "json",
            prompt,
        ]
    return [BOB_BINARY, "-p", prompt]


def _supports_subcommand(name: str) -> bool:
    try:
        out = subprocess.run(
            [BOB_BINARY, "--help"],
            capture_output=True, text=True, timeout=15,
        )
        return name in (out.stdout + out.stderr)
    except Exception:
        return False


def analyze(evidence: dict[str, Any], tickets: list[dict[str, Any]]) -> BobResult:
    """Send structured evidence to IBM Bob. Return its structured analysis."""
    started = datetime.now(timezone.utc)

    if shutil.which(BOB_BINARY) is None:
        return _fail(
            f"IBM Bob CLI '{BOB_BINARY}' not found on PATH", [], started
        )

    prompt = PROMPT_TEMPLATE.format(
        evidence=json.dumps(evidence, indent=2, default=str),
        tickets=json.dumps(tickets, indent=2, default=str),
    )
    argv = _build_argv(prompt)
    log.info("[BOB] invoking mode=%s timeout=%ss", BOB_MODE, BOB_TIMEOUT)

    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=BOB_TIMEOUT,
            cwd=WORKSPACE,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return _fail(f"IBM Bob timed out after {BOB_TIMEOUT}s", argv, started)
    except OSError as exc:
        return _fail(f"IBM Bob invocation failed: {exc}", argv, started)

    elapsed = _ms(started)

    if proc.returncode != 0:
        return _fail(
            f"IBM Bob exited {proc.returncode}: {proc.stderr[:400]}",
            argv, started, raw=proc.stdout,
        )

    try:
        analysis = _extract_json(proc.stdout)
    except ValueError as exc:
        return _fail(
            f"IBM Bob returned unparseable output: {exc}",
            argv, started, raw=proc.stdout,
        )

    analysis.setdefault("analysis_source", "ibm-bob")
    log.info("[BOB] ok in %dms", elapsed)
    return BobResult(
        ok=True, analysis=analysis, raw_stdout=proc.stdout,
        invocation=_redact(argv), duration_ms=elapsed,
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
