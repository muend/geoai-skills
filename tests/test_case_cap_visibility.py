"""The per-case cap must be omittable, because the model reads it.

`--max-budget-usd` is visible to the model, which treats it as a constraint the
user imposed rather than a harness ceiling. It does not reason about absolute
headroom; it reports the remaining *fraction*. In run `optionA-r2-20260725` the
case `mcda-suitability-analysis/single-map-pushback` spent $0.0978 under a $0.50
cap and told the user:

    "this session's budget is nearly exhausted ($0.43 of $0.50 left), so a full
    pairwise-AHP + sensitivity workflow may not fit"

The AHP and sensitivity workflow is exactly what that case measures. Raising the
cap cannot fix this — $0.50 was already 3.5x the measured per-case cost, and any
finite number can be read as scarcity. Only omitting the flag removes the
surface; `--max-total-cost-usd` still bounds the run.
"""

from __future__ import annotations

import argparse

import pytest

from tools.adapters.claude_code import (
    AdapterError,
    base_claude_command,
    execution_command,
    validate_args,
)


def _execution(case_budget_usd: float | None) -> list[str]:
    return execution_command(
        claude_command="claude",
        model="claude-sonnet-5",
        condition="skills-disabled",
        plugin_dir=None,
        case_budget_usd=case_budget_usd,
        max_turns=8,
        tool_profile="read-only",
    )


def test_omitting_the_cap_removes_the_flag_entirely() -> None:
    """Not a zero, not a sentinel — the argument must not appear at all."""
    command = base_claude_command(
        claude_command="claude",
        model="claude-sonnet-5",
        case_budget_usd=None,
        max_turns=8,
    )

    assert "--max-budget-usd" not in command
    assert not any("budget" in part for part in command)


def test_supplying_the_cap_still_passes_it() -> None:
    command = base_claude_command(
        claude_command="claude",
        model="claude-sonnet-5",
        case_budget_usd=0.5,
        max_turns=8,
    )

    assert command[command.index("--max-budget-usd") + 1] == "0.5"


def test_the_execution_command_honours_omission() -> None:
    assert "--max-budget-usd" not in _execution(None)
    assert "--max-budget-usd" in _execution(0.5)


def test_omission_does_not_disturb_the_rest_of_the_command() -> None:
    """Dropping the cap must not shift any other flag's meaning."""
    capped = _execution(0.5)
    uncapped = _execution(None)

    assert [part for part in capped if part not in {"--max-budget-usd", "0.5"}] == (
        uncapped
    )


def _args(case_cap: float | None, total_cap: float) -> argparse.Namespace:
    return argparse.Namespace(
        max_case_cost_usd=case_cap,
        max_total_cost_usd=total_cap,
        timeout_seconds=300,
    )


def test_an_absent_cap_validates() -> None:
    validate_args(_args(None, 6.0))


def test_the_total_cap_is_still_mandatory_and_positive() -> None:
    """Removing the per-case ceiling must not remove the only remaining bound."""
    with pytest.raises(AdapterError, match="must be positive"):
        validate_args(_args(None, 0.0))


def test_a_supplied_cap_is_still_checked_against_the_total() -> None:
    with pytest.raises(AdapterError, match="cannot exceed total"):
        validate_args(_args(9.0, 6.0))


def test_a_supplied_cap_must_still_be_positive() -> None:
    with pytest.raises(AdapterError, match="must be positive"):
        validate_args(_args(0.0, 6.0))
