"""
IBM Bob provider -- the project's default reasoning engine.

TRANSPORT
---------
Bob 2.0 ships a headless CLI, Bob Shell (`bob run`), authenticated with an
Inference-scoped API key. That is the supported programmatic path, and it is
what this provider drives:

    bob run --mode kubemedic-reasoner --format json --max-turns N --max-cost C \\
            --disable-mcp --disable-subagents "<prompt>"

Bob's own inference gateway sits behind bot protection that refuses clients it
does not recognise, so this provider does not call it directly. It runs the
official client instead, with a fixed argument list (never a shell, and never
text composed by a model as anything but the prompt argument).

WHY THESE FLAGS
---------------
--mode kubemedic-reasoner  the tool-less custom mode in .bob/custom_modes.yaml.
--disable-mcp              the evidence is already in the prompt, collected by
                           our own read-only layer. Bob is asked to reason, not
                           to go and look.
--disable-subagents        one bounded call, not a tree of them.
--disable-tool-groups      every group: no file reads, edits, commands or skills
                           during analysis. Pure reasoning over the evidence.
--max-cost / --max-turns   Bob usage is metered. Both are always passed; an
                           unbounded run is not an option this provider offers.

NO RETRY
--------
A timeout raises RuntimeError, not TimeoutError, so the shared failure policy
does not retry it. A retry would re-spend metered usage on a call that may have
already completed.

The API key reaches the child process only through its environment. It is never
placed on the command line, logged, or written to disk.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from agent.providers.base import BaseProvider
from agent.secrets import get_secrets

# A workspace holding only the reasoner mode. See its custom_modes.yaml for why
# the repository root is not used.
WORKSPACE = Path(__file__).resolve().parent / "bob_workspace"

DEFAULT_MAX_COST = "2.0"
DEFAULT_MAX_TURNS = "3"

# Every Bob tool group. Analysis is pure reasoning over evidence already in the
# prompt: Bob must not read the workspace, edit it, run anything, or call other
# agents. Left enabled, Bob behaves as a coding agent and wanders the repository
# instead of answering.
ALL_TOOL_GROUPS = "read,edit,execute,mcp,skill,mode,subagent,subtask,todo"


def command_prefix(binary: str) -> list[str]:
    """
    How to start Bob Shell without a shell in between.

    On Windows `bob` is a `.cmd` shim, and cmd.exe cuts a multi-line argument
    off at its first newline -- the prompt arrived as a single line and Bob
    reported that no evidence had been provided. When a shim is found, run the
    Node entrypoint it wraps directly.
    """
    if os.name == "nt" and binary.lower().endswith((".cmd", ".bat")):
        entry = Path(binary).parent / "node_modules" / "bobshell" / "dist" / "bob.js"
        node = shutil.which("node")
        if node and entry.is_file():
            return [node, str(entry)]
    return [binary]


class IBMBobProvider(BaseProvider):
    id = "ibm-bob"
    display_name = "IBM Bob"

    def __init__(self) -> None:
        super().__init__()
        secrets = get_secrets()
        self.api_key = secrets.get("KUBEMEDIC_BOB_API_KEY") or secrets.get("BOB_API_KEY")
        self.binary = os.getenv("KUBEMEDIC_BOB_BIN") or shutil.which("bob")
        self.mode = os.getenv("KUBEMEDIC_BOB_MODE", "kubemedic-reasoner")
        self.timeout = int(os.getenv("KUBEMEDIC_BOB_TIMEOUT_SECONDS", "180"))
        self.max_cost = os.getenv("KUBEMEDIC_BOB_MAX_COST", DEFAULT_MAX_COST)
        self.max_turns = os.getenv("KUBEMEDIC_BOB_MAX_TURNS", DEFAULT_MAX_TURNS)
        self.team_id = os.getenv("KUBEMEDIC_BOB_TEAM_ID")

    def is_configured(self) -> tuple[bool, str]:
        if not self.api_key:
            return False, (
                "KUBEMEDIC_BOB_API_KEY is unset. Create an Inference-scoped key "
                "in the Bob web portal, or run Bob interactively in the "
                "workspace and use the host or manual provider."
            )
        if not self.binary:
            return False, (
                "Bob Shell (`bob`) was not found on PATH. Install it from "
                "https://bob.ibm.com/docs/shell, or set KUBEMEDIC_BOB_BIN."
            )
        return True, f"Bob Shell headless, mode {self.mode}, cost cap {self.max_cost}"

    def _invocation(self) -> list[str]:
        return [
            "bob-shell", "run", f"mode={self.mode}",
            f"max-cost={self.max_cost}", f"max-turns={self.max_turns}",
        ]

    def _argv(self, prompt: str) -> list[str]:
        argv = [
            *command_prefix(self.binary), "run",
            "--workspace", str(WORKSPACE),
            "--mode", self.mode,
            "--format", "json",
            "--max-turns", str(self.max_turns),
            "--max-cost", str(self.max_cost),
            "--disable-mcp",
            "--disable-subagents",
            "--disable-tool-groups", ALL_TOOL_GROUPS,
        ]
        if self.team_id:
            argv += ["--team-id", self.team_id]
        argv.append(prompt)
        return argv

    def _env(self) -> dict[str, str]:
        env = dict(os.environ)
        env.pop("BOBSHELL_API_KEY", None)        # Bob refuses two differing keys
        env["BOB_API_KEY"] = self.api_key or ""
        return env

    def _invoke(self, prompt: str) -> str:
        try:
            done = subprocess.run(
                self._argv(prompt),
                capture_output=True, text=True, encoding="utf-8",
                timeout=self.timeout, env=self._env(),
                stdin=subprocess.DEVNULL, shell=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"Bob Shell did not finish within {self.timeout}s; not retried "
                "because Bob usage is metered"
            ) from exc
        except OSError as exc:
            raise RuntimeError(f"could not start Bob Shell: {exc}") from exc

        return self._answer(done.returncode, done.stdout, done.stderr)

    @staticmethod
    def _answer(returncode: int, stdout: str, stderr: str) -> str:
        """The model's final message from Bob Shell's JSON result line."""
        result = None
        for line in reversed((stdout or "").strip().splitlines()):
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                parsed = json.loads(line)
            except ValueError:
                continue
            if parsed.get("type") == "result":
                result = parsed
                break

        if result is None:
            detail = (stderr or stdout or "").strip().replace("\n", " ")[:300]
            raise RuntimeError(
                f"Bob Shell returned no result (exit {returncode}): {detail}"
            )
        if result.get("status") != "success":
            raise RuntimeError(
                f"Bob Shell reported status {result.get('status')!r}: "
                f"{str(result.get('error') or result.get('last_message') or '')[:300]}"
            )
        message = result.get("last_message")
        if not message:
            raise RuntimeError("Bob Shell finished without a final message")
        return message
