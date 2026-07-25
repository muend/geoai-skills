"""The execution workspace must sit outside the repository.

Run `optionA-r2-20260725` exposed a contaminated control: six of eighteen
`skills-disabled` responses cited the repository, one reproducing a `SKILL.md`
almost verbatim. The cause was the workspace being created under `evals/runs/`
to dodge a Windows 8.3 short TEMP path. With the working directory inside the
repository, the `Read` tool granted to *both* conditions could open
`skills/*/SKILL.md`, so the disabled condition measured "skill not auto-invoked"
instead of "skill unavailable".

Disabling the `Skill` tool prevents invocation. It does not prevent reading the
skill off disk. These tests keep that distinction enforced at runtime.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from tools.adapters.claude_code import (
    ROOT,
    AdapterError,
    assert_outside_repository,
    expand_long_path,
)


def test_a_workspace_inside_the_repository_is_rejected() -> None:
    with pytest.raises(AdapterError, match="inside the repository root"):
        assert_outside_repository(ROOT / "evals" / "runs" / "some-workspace")


def test_the_old_leaking_location_is_specifically_rejected() -> None:
    """`evals/runs/.geoai-claude-adapter-*` is exactly where the leak lived."""
    with pytest.raises(AdapterError):
        assert_outside_repository(
            ROOT / "evals" / "runs" / ".geoai-claude-adapter-abc123" / "workspaces"
        )


def test_the_rejection_explains_why_rather_than_just_failing() -> None:
    with pytest.raises(AdapterError) as excinfo:
        assert_outside_repository(ROOT / "evals" / "runs" / "w")

    message = str(excinfo.value)
    assert "Read" in message
    assert "skills/*/SKILL.md" in message
    assert "measure skill availability" in message


def test_a_system_temp_workspace_is_accepted() -> None:
    with tempfile.TemporaryDirectory(prefix="geoai-claude-adapter-") as temporary:
        assert_outside_repository(expand_long_path(Path(temporary)))


def test_expand_long_path_is_a_noop_for_an_already_long_path() -> None:
    with tempfile.TemporaryDirectory(prefix="geoai-claude-adapter-") as temporary:
        path = Path(temporary)
        assert expand_long_path(path) == path.resolve()


def test_expand_long_path_returns_an_existing_directory() -> None:
    """The short-path expansion must not invent a path that does not exist."""
    with tempfile.TemporaryDirectory(prefix="geoai-claude-adapter-") as temporary:
        expanded = expand_long_path(Path(temporary))
        assert expanded.is_dir()


def test_the_adapter_no_longer_creates_workspaces_under_the_run_directory() -> None:
    """Guard the source itself: the old call signature must not come back."""
    source = (ROOT / "tools" / "adapters" / "claude_code.py").read_text(
        encoding="utf-8"
    )

    assert "dir=run_dir.parent" not in source, (
        "the execution workspace is being created inside evals/runs again; "
        "that is the contamination this module exists to prevent"
    )
    assert "assert_outside_repository(temporary_root)" in source
