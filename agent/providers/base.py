"""
The reasoning provider contract, and the failure policy every provider shares.

WHY THE FAILURE POLICY LIVES HERE
---------------------------------
Every failure mode -- no credentials, authentication rejected, timeout,
unreachable endpoint, unparseable output, schema violation -- must converge on
one outcome: analysis_source "unavailable", no plan built, incident stops.

That is the most valuable property in the system. It is what lets the project
claim it reports an outage instead of inventing a diagnosis. Re-implementing it
per provider guarantees the third or fourth one gets a branch subtly wrong, and
the failure would be silent: a fabricated analysis looks exactly like a real
one until someone acts on it.

So providers implement `_invoke()` -- the transport, and only the transport --
and `analyze()` here wraps it. A provider cannot accidentally return success on
an error path because it does not own the success path.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable

from agent.providers.parsing import extract_json
from agent.providers.prompt import build_prompt

log = logging.getLogger("kubemedic.providers")


@dataclass
class ProviderResult:
    """
    One reasoning attempt. `ok` is the only thing callers should branch on.

    Structurally compatible with the original BobResult so the reasoning bridge
    and the existing tests keep working unchanged.
    """
    ok: bool
    analysis: dict[str, Any] | None
    raw_stdout: str = ""
    invocation: list[str] = field(default_factory=list)
    duration_ms: int = 0
    error: str | None = None
    provider_id: str = "unknown"
    invoked_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def audit_entry(self) -> dict[str, Any]:
        """
        Structured record for the audit trail. Never a model-written summary,
        and never the prompt -- it carries cluster detail.
        """
        return {
            "stage": "REASONING",
            "provider": self.provider_id,
            "invoked_at": self.invoked_at,
            "invocation": self.invocation,
            "duration_ms": self.duration_ms,
            "ok": self.ok,
            "error": self.error,
            "analysis_source": self.provider_id if self.ok else "unavailable",
        }


# Backwards compatibility: agent/bob.py and several tests import BobResult.
BobResult = ProviderResult


@runtime_checkable
class ReasoningProvider(Protocol):
    id: str
    display_name: str

    def is_configured(self) -> tuple[bool, str]: ...
    def analyze(
        self,
        evidence: dict[str, Any],
        tickets: list[dict[str, Any]],
        feedback: list[str] | None = None,
    ) -> ProviderResult: ...


class BaseProvider:
    """
    Shared machinery. Subclasses implement `_invoke(prompt) -> str` and
    `is_configured()`; everything else is inherited so behaviour is identical
    across providers.
    """

    id: str = "unknown"
    display_name: str = "Unknown provider"

    def __init__(self) -> None:
        # Usage counters. In-process and non-durable, like the incident store.
        # Enough to answer "is this provider working, and what is it costing"
        # without introducing a datastore.
        self.calls = 0
        self.successes = 0
        self.failures: dict[str, int] = {}
        self.total_ms = 0
        self.last_error: str | None = None
        self.last_invoked_at: str | None = None

    # -- transport, implemented per provider ------------------------------

    def _invoke(self, prompt: str) -> str:
        raise NotImplementedError

    def is_configured(self) -> tuple[bool, str]:
        raise NotImplementedError

    # -- the one success path ---------------------------------------------

    def analyze(
        self,
        evidence: dict[str, Any],
        tickets: list[dict[str, Any]],
        feedback: list[str] | None = None,
    ) -> ProviderResult:
        started = time.monotonic()
        self.calls += 1
        self.last_invoked_at = datetime.now(timezone.utc).isoformat()

        configured, reason = self.is_configured()
        if not configured:
            return self._fail("not_configured", reason, started)

        prompt = build_prompt(evidence, tickets, feedback)

        try:
            raw = self._invoke(prompt)
        except TimeoutError as exc:
            return self._fail(
                "timeout", f"{self.display_name} timed out: {exc}", started
            )
        except Exception as exc:
            return self._fail(
                "transport", f"{self.display_name} call failed: {exc}", started
            )

        try:
            analysis = extract_json(raw)
        except ValueError as exc:
            return self._fail(
                "unparseable",
                f"{self.display_name} returned unparseable output: {exc}",
                started, raw=raw,
            )

        # Stamp provenance rather than trusting the model to report it.
        analysis["analysis_source"] = self.id

        elapsed = self._ms(started)
        self.successes += 1
        self.total_ms += elapsed
        log.info("[%s] ok in %dms", self.id, elapsed)
        return ProviderResult(
            ok=True, analysis=analysis, raw_stdout=raw,
            invocation=self._invocation(), duration_ms=elapsed,
            provider_id=self.id,
        )

    # -- failure, one place ------------------------------------------------

    def _fail(
        self, kind: str, message: str, started: float, raw: str = ""
    ) -> ProviderResult:
        elapsed = self._ms(started)
        self.failures[kind] = self.failures.get(kind, 0) + 1
        self.total_ms += elapsed
        self.last_error = message
        log.error("[%s] %s: %s", self.id, kind, message)
        return ProviderResult(
            ok=False, analysis=None, raw_stdout=raw,
            invocation=self._invocation(), duration_ms=elapsed,
            error=message, provider_id=self.id,
        )

    def _invocation(self) -> list[str]:
        """Never includes the prompt (cluster detail) or any secret."""
        return [self.id]

    @staticmethod
    def _ms(started: float) -> int:
        return int((time.monotonic() - started) * 1000)

    # -- health and usage ---------------------------------------------------

    def usage(self) -> dict[str, Any]:
        configured, reason = self.is_configured()
        return {
            "provider": self.id,
            "display_name": self.display_name,
            "configured": configured,
            "detail": reason,
            "calls": self.calls,
            "successes": self.successes,
            "failures": dict(self.failures),
            "failure_total": sum(self.failures.values()),
            "avg_ms": round(self.total_ms / self.calls) if self.calls else 0,
            "last_invoked_at": self.last_invoked_at,
            "last_error": self.last_error,
        }


def unavailable_analysis(reason: str) -> dict[str, Any]:
    """
    The shape reasoning.py substitutes when no provider could answer.

    analysis_source is 'unavailable', never a provider id -- the dashboard
    renders this as an outage and the incident does not advance to a plan.
    """
    return {
        "schema_version": "1.0",
        "analysis_source": "unavailable",
        "status": "provider_unavailable",
        "reason": reason,
        "hypotheses": [],
        "recommended_action": None,
        "requires_human_approval": True,
    }
