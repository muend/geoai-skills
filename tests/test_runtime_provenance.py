"""The recorded runtime must be the runtime that produced the responses.

Every response row carries a `runtime` field, and `execute_one` copies that
field verbatim out of `manifest.json`. Nothing checked the manifest against the
CLI actually on PATH. So an auto-updated Claude Code — 2.1.214 becoming 2.1.219
between two tranches of the same run — would stamp its output with the version
named when the run directory was prepared, in a directory whose own name
asserts the older version.

That corruption is unrecoverable after the fact: the mis-stamped rows are
byte-indistinguishable from genuine ones, so no later audit can separate them.
The operating rule "verify `claude --version` before any run" was manual and
had no enforcement behind it. These tests are the enforcement.
"""

from __future__ import annotations

import subprocess

import pytest

from tools.adapters.claude_code import (
    AdapterError,
    assert_runtime_matches_cli,
    detect_cli_version,
)


def _version_process(
    stdout: str, *, returncode: int = 0, stderr: str = ""
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["claude", "--version"],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


def _patch_version(
    monkeypatch: pytest.MonkeyPatch, process: subprocess.CompletedProcess[str]
) -> None:
    monkeypatch.setattr(
        "tools.adapters.claude_code.subprocess.run",
        lambda *args, **kwargs: process,
    )


def test_the_version_is_read_from_the_cli_banner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`claude --version` prints `2.1.214 (Claude Code)`, not a bare semver."""
    _patch_version(monkeypatch, _version_process("2.1.214 (Claude Code)\n"))

    assert detect_cli_version("claude") == "2.1.214"


def test_a_matching_runtime_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_version(monkeypatch, _version_process("2.1.214 (Claude Code)\n"))

    assert assert_runtime_matches_cli("claude", "claude-code-2.1.214") == "2.1.214"


def test_an_updated_cli_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """The exact failure this guard exists for: a silent patch-level update."""
    _patch_version(monkeypatch, _version_process("2.1.219 (Claude Code)\n"))

    with pytest.raises(AdapterError, match="did not produce them"):
        assert_runtime_matches_cli("claude", "claude-code-2.1.214")


def test_the_refusal_names_both_versions(monkeypatch: pytest.MonkeyPatch) -> None:
    """An operator must be able to act on the message without reading code."""
    _patch_version(monkeypatch, _version_process("2.1.219 (Claude Code)\n"))

    with pytest.raises(AdapterError) as failure:
        assert_runtime_matches_cli("claude", "claude-code-2.1.214")

    message = str(failure.value)
    assert "claude-code-2.1.214" in message
    assert "2.1.219" in message


def test_a_versionless_manifest_runtime_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`--runtime` is free text; an unversioned label cannot be attributed."""
    _patch_version(monkeypatch, _version_process("2.1.214 (Claude Code)\n"))

    with pytest.raises(AdapterError, match="names no version"):
        assert_runtime_matches_cli("claude", "claude-code")


def test_unparseable_version_output_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_version(monkeypatch, _version_process("Claude Code (unknown build)\n"))

    with pytest.raises(AdapterError, match="Could not read a version"):
        detect_cli_version("claude")


def test_a_failing_version_call_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing or broken CLI must stop the run, not fall through to guessing."""
    _patch_version(
        monkeypatch,
        _version_process("", returncode=127, stderr="claude: not found"),
    )

    with pytest.raises(AdapterError, match="claude: not found"):
        detect_cli_version("claude")


def test_the_gate_runs_before_any_case_executes() -> None:
    """Ordering is the whole point: refuse before spending, not after.

    `execute_run` must call the guard before it reads the checkpoint or opens a
    workspace, so a mismatched CLI costs nothing and writes nothing.
    """
    import inspect

    from tools.adapters.claude_code import execute_run

    source = inspect.getsource(execute_run)
    gate = source.index("assert_runtime_matches_cli")
    checkpoint = source.index("read_partial_rows")
    workspace = source.index("TemporaryDirectory")

    assert gate < checkpoint
    assert gate < workspace
