"""
The IBM Bob provider drives Bob Shell headless. No test here starts Bob or
spends usage: subprocess.run is faked.
"""
from __future__ import annotations

import json
import subprocess
from types import SimpleNamespace

import pytest

from agent.providers.ibm_bob import IBMBobProvider

KEY = "bob_test_key_not_real"


def _result(message="{}", status="success", **extra):
    return json.dumps({"type": "result", "status": status,
                       "last_message": message, **extra})


@pytest.fixture
def provider(monkeypatch):
    monkeypatch.setenv("KUBEMEDIC_BOB_API_KEY", KEY)
    monkeypatch.setenv("KUBEMEDIC_BOB_BIN", "/usr/bin/bob")
    monkeypatch.setenv("BOBSHELL_API_KEY", "some-other-value")
    return IBMBobProvider()


def _fake_run(monkeypatch, stdout="", stderr="", returncode=0, capture=None, raises=None):
    def run(argv, **kwargs):
        if capture is not None:
            capture.update(argv=argv, kwargs=kwargs)
        if raises:
            raise raises
        return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)

    monkeypatch.setattr("agent.providers.ibm_bob.subprocess.run", run)


class TestConfiguration:
    def test_needs_a_key(self, monkeypatch):
        monkeypatch.delenv("KUBEMEDIC_BOB_API_KEY", raising=False)
        monkeypatch.delenv("BOB_API_KEY", raising=False)
        monkeypatch.setenv("KUBEMEDIC_BOB_BIN", "/usr/bin/bob")
        ok, why = IBMBobProvider().is_configured()
        assert not ok and "KUBEMEDIC_BOB_API_KEY" in why

    def test_needs_the_binary(self, monkeypatch):
        monkeypatch.setenv("KUBEMEDIC_BOB_API_KEY", KEY)
        monkeypatch.delenv("KUBEMEDIC_BOB_BIN", raising=False)
        monkeypatch.setattr("agent.providers.ibm_bob.shutil.which", lambda _: None)
        ok, why = IBMBobProvider().is_configured()
        assert not ok and "Bob Shell" in why

    def test_configured(self, provider):
        assert provider.is_configured()[0] is True

    def test_no_default_rest_endpoint_remains(self):
        import agent.providers.ibm_bob as mod

        assert not hasattr(mod, "urllib")
        assert "manufact" not in open(mod.__file__, encoding="utf-8").read()


class TestInvocation:
    def test_argv_is_fixed_bounded_and_read_only(self, provider, monkeypatch):
        seen: dict = {}
        _fake_run(monkeypatch, _result("{}"), capture=seen)
        provider._invoke("PROMPT TEXT")

        argv = seen["argv"]
        assert argv[:2] == ["/usr/bin/bob", "run"]
        assert argv[-1] == "PROMPT TEXT"
        for flag in ("--max-cost", "--max-turns", "--disable-mcp",
                     "--disable-subagents", "--format"):
            assert flag in argv
        assert argv[argv.index("--mode") + 1] == "kubemedic-reasoner"
        assert seen["kwargs"]["shell"] is False

    def test_key_reaches_the_child_only_via_environment(self, provider, monkeypatch):
        seen: dict = {}
        _fake_run(monkeypatch, _result("{}"), capture=seen)
        provider._invoke("p")

        assert KEY not in " ".join(seen["argv"])
        env = seen["kwargs"]["env"]
        assert env["BOB_API_KEY"] == KEY
        assert "BOBSHELL_API_KEY" not in env

    def test_invocation_record_carries_neither_key_nor_prompt(self, provider):
        text = " ".join(provider._invocation())
        assert KEY not in text
        assert "cost" in text


class TestAnswerParsing:
    def test_returns_the_final_message(self, provider, monkeypatch):
        _fake_run(monkeypatch, "noise line\n" + _result('{"a": 1}'))
        assert provider._invoke("p") == '{"a": 1}'

    def test_non_success_status_is_a_failure(self, provider, monkeypatch):
        _fake_run(monkeypatch, _result("", status="max_cost_exceeded"))
        with pytest.raises(RuntimeError, match="max_cost_exceeded"):
            provider._invoke("p")

    def test_no_result_line_is_a_failure(self, provider, monkeypatch):
        _fake_run(monkeypatch, "Error: nope", stderr="boom", returncode=1)
        with pytest.raises(RuntimeError, match="no result"):
            provider._invoke("p")

    def test_empty_final_message_is_a_failure(self, provider, monkeypatch):
        _fake_run(monkeypatch, _result(""))
        with pytest.raises(RuntimeError, match="final message"):
            provider._invoke("p")


class TestFailurePolicy:
    def test_timeout_is_not_retried(self, provider, monkeypatch):
        calls = []

        def run(argv, **kw):
            calls.append(1)
            raise subprocess.TimeoutExpired(argv, 1)

        monkeypatch.setattr("agent.providers.ibm_bob.subprocess.run", run)
        result = provider.analyze({}, [])
        assert result.ok is False
        assert len(calls) == 1
        assert "metered" in result.error

    def test_success_is_stamped_ibm_bob(self, provider, monkeypatch):
        analysis = {"hypotheses": [], "recommended_action": None}
        _fake_run(monkeypatch, _result(json.dumps(analysis)))
        result = provider.analyze({}, [])
        assert result.ok and result.analysis["analysis_source"] == "ibm-bob"

    def test_missing_binary_is_unavailable_not_a_crash(self, provider, monkeypatch):
        _fake_run(monkeypatch, raises=FileNotFoundError("no bob"))
        result = provider.analyze({}, [])
        assert result.ok is False
        assert "could not start Bob Shell" in result.error


class TestLaunching:
    def test_runs_in_the_dedicated_workspace_not_the_repository(self, provider):
        from agent.providers.ibm_bob import WORKSPACE

        argv = provider._argv("p")
        assert argv[argv.index("--workspace") + 1] == str(WORKSPACE)
        assert (WORKSPACE / ".bob" / "custom_modes.yaml").is_file()

    def test_all_tool_groups_are_disabled(self, provider):
        argv = provider._argv("p")
        groups = argv[argv.index("--disable-tool-groups") + 1].split(",")
        for group in ("read", "edit", "execute", "mcp", "skill", "subagent"):
            assert group in groups

    def test_windows_shim_is_bypassed_so_multiline_prompts_survive(self, monkeypatch):
        # Deliberately not exercised against a real filesystem: the shim path
        # is a Windows one, and a real Path for a foreign OS refuses to be
        # instantiated (pathlib.UnsupportedOperation) on whatever host runs
        # this suite. `exists` is injected instead of relying on one.
        from pathlib import PureWindowsPath

        from agent.providers import ibm_bob

        shim = r"C:\Program Files\bobshell\bob.cmd"
        monkeypatch.setattr(ibm_bob.os, "name", "nt")
        monkeypatch.setattr(ibm_bob.shutil, "which", lambda _: "/usr/bin/node")

        assert ibm_bob._bob_js_entry(shim) == (
            PureWindowsPath(shim).parent / "node_modules" / "bobshell" / "dist" / "bob.js"
        )
        assert ibm_bob.command_prefix(shim, exists=lambda p: True) == [
            "/usr/bin/node", str(ibm_bob._bob_js_entry(shim)),
        ]

    def test_windows_shim_falls_back_when_the_entrypoint_is_missing(self, monkeypatch):
        from agent.providers import ibm_bob

        shim = r"C:\Program Files\bobshell\bob.cmd"
        monkeypatch.setattr(ibm_bob.os, "name", "nt")
        monkeypatch.setattr(ibm_bob.shutil, "which", lambda _: "/usr/bin/node")

        assert ibm_bob.command_prefix(shim, exists=lambda p: False) == [shim]

    def test_no_node_falls_back_to_the_shim(self, monkeypatch):
        from agent.providers import ibm_bob

        shim = r"C:\Program Files\bobshell\bob.cmd"
        monkeypatch.setattr(ibm_bob.os, "name", "nt")
        monkeypatch.setattr(ibm_bob.shutil, "which", lambda _: None)

        assert ibm_bob.command_prefix(shim, exists=lambda p: True) == [shim]

    def test_non_windows_ignores_the_shim_logic_entirely(self, monkeypatch):
        from agent.providers import ibm_bob

        monkeypatch.setattr(ibm_bob.os, "name", "posix")
        assert ibm_bob.command_prefix("/usr/local/bin/bob.cmd") == ["/usr/local/bin/bob.cmd"]

    def test_plain_binary_is_used_as_is(self):
        from agent.providers import ibm_bob

        assert ibm_bob.command_prefix("/usr/local/bin/bob") == ["/usr/local/bin/bob"]
