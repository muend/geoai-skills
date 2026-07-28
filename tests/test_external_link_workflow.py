"""Contract tests for the non-blocking external-link monitor."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "external-links.yml"
LYCHEE_ACTION = "lycheeverse/lychee-action@8646ba30535128ac92d33dfc9133794bfdd9b411"


def workflow() -> dict:
    data = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    # YAML 1.1 interprets GitHub's `on` key as boolean True. Restore the key
    # after safe parsing rather than weakening loader safety in the test.
    if True in data and "on" not in data:
        data["on"] = data.pop(True)
    return data


def lychee_step() -> dict:
    steps = workflow()["jobs"]["check"]["steps"]
    return next(step for step in steps if step.get("id") == "lychee")


def test_monitor_is_scheduled_manual_and_narrowly_event_driven() -> None:
    triggers = workflow()["on"]

    assert set(triggers) == {"workflow_dispatch", "schedule", "push", "pull_request"}
    assert triggers["schedule"] == [{"cron": "17 6 * * 1"}]
    assert triggers["push"] == {"branches": ["main"], "paths": ["**/*.md"]}
    assert triggers["pull_request"] == {
        "paths": [".github/workflows/external-links.yml"]
    }


def test_monitor_has_read_only_permissions_and_bounded_execution() -> None:
    data = workflow()
    job = data["jobs"]["check"]

    assert data["permissions"] == {"contents": "read"}
    assert job["runs-on"] == "ubuntu-latest"
    assert job["timeout-minutes"] == 15
    assert "issues" not in data["permissions"]
    assert "pull-requests" not in data["permissions"]


def test_lychee_action_and_cli_are_immutably_pinned() -> None:
    step = lychee_step()
    github_token_expression = "$" + "{{ secrets.GITHUB_TOKEN }}"

    assert step["uses"] == LYCHEE_ACTION
    assert step["with"]["lycheeVersion"] == "v0.24.2"
    assert step["with"]["token"] == github_token_expression


def test_link_failures_are_reported_without_becoming_a_merge_gate() -> None:
    settings = lychee_step()["with"]

    assert settings["fail"] is False
    assert settings["failIfEmpty"] is True
    assert settings["format"] == "markdown"
    assert settings["jobSummary"] is True
    assert settings["output"] == "lychee/out.md"


def test_network_scope_retries_and_concurrency_are_bounded() -> None:
    args = lychee_step()["with"]["args"]

    for expected in (
        "--exclude-all-private",
        "--require-https",
        "--no-progress",
        "--max-concurrency 8",
        "--host-concurrency 2",
        "--max-retries 2",
        "--retry-wait-time 2",
        "--timeout 30",
        "--scheme https",
        "'./**/*.md'",
    ):
        assert expected in args
