"""Tests for the result vocabulary itself.

These are the load-bearing tests. Every check in the toolkit reports through
this type, so if abstention can leak into a pass here, it can leak everywhere.
"""

from __future__ import annotations

import json

from tools.verification import Outcome, Report, abstained, failed, passed


def test_pass_is_ok_and_nothing_else() -> None:
    result = passed("c", "fine")

    assert result.ok
    assert not result.failed
    assert not result.abstained


def test_fail_is_not_ok() -> None:
    result = failed("c", "broken", ["line 3"])

    assert result.failed
    assert not result.ok
    assert not result.abstained


def test_abstain_is_neither_ok_nor_failed() -> None:
    """The distinction the whole toolkit rests on."""
    result = abstained("c", "cannot see the input")

    assert result.abstained
    assert not result.ok
    assert not result.failed


def test_a_result_is_immutable() -> None:
    result = passed("c", "fine")

    try:
        result.outcome = Outcome.FAIL  # type: ignore[misc]
    except Exception:
        return
    raise AssertionError("Result should be frozen")


def test_evidence_is_copied_not_aliased() -> None:
    """A caller mutating its list must not rewrite history."""
    evidence = ["first"]
    result = failed("c", "r", evidence)
    evidence.append("second")

    assert result.to_dict()["evidence"] == ["first"]


def test_render_includes_every_evidence_line() -> None:
    rendered = failed("c", "r", ["one", "two"]).render()

    assert "one" in rendered and "two" in rendered
    assert "FAIL" in rendered


# --- Report ---------------------------------------------------------------


def test_an_empty_report_is_verified() -> None:
    assert Report().exit_code == 0


def test_a_failure_gives_exit_code_one() -> None:
    report = Report()
    report.add(passed("a", "ok"))
    report.add(failed("b", "bad"))

    assert report.exit_code == 1
    assert "FAILED" in report.summary()


def test_an_abstention_gives_exit_code_two() -> None:
    """'Not verified' must be distinguishable from 'verified and fine'."""
    report = Report()
    report.add(passed("a", "ok"))
    report.add(abstained("b", "no input"))

    assert report.exit_code == 2
    assert "NOT VERIFIED" in report.summary()


def test_a_failure_outranks_an_abstention() -> None:
    report = Report()
    report.add(abstained("a", "no input"))
    report.add(failed("b", "bad"))

    assert report.exit_code == 1


def test_all_passes_give_exit_code_zero() -> None:
    report = Report()
    report.add(passed("a", "ok"))
    report.add(passed("b", "ok"))

    assert report.exit_code == 0
    assert "verified" in report.summary()


def test_the_summary_counts_never_overlap() -> None:
    report = Report()
    for result in (passed("a", "x"), failed("b", "y"), abstained("c", "z")):
        report.add(result)

    summary = report.summary()

    assert "1 pass" in summary and "1 fail" in summary and "1 abstain" in summary


def test_json_output_is_machine_readable() -> None:
    report = Report()
    report.add(failed("check.name", "reason", ["evidence line"], extra=1))

    payload = json.loads(report.to_json())

    assert payload["exit_code"] == 1
    assert payload["results"][0]["check"] == "check.name"
    assert payload["results"][0]["detail"]["extra"] == 1


def test_add_returns_the_result_for_chaining() -> None:
    report = Report()
    result = report.add(passed("a", "ok"))

    assert result.ok
    assert report.results == [result]


def test_an_outcome_formats_as_its_value_not_its_member_name() -> None:
    """These strings leave the process, so how they render is an interface.

    `Outcome` was `(str, Enum)`, where f-string interpolation yields
    `Outcome.PASS` on Python 3.11+ unless `__str__` is overridden — while
    `.value` yields `pass`. Two callers writing the obvious thing would emit
    different strings, and whichever one a skill contract or a downstream parser
    happened to use would decide whether it worked. `StrEnum` removes the
    choice; this test is what keeps it removed.
    """
    assert str(Outcome.PASS) == "pass"
    assert f"{Outcome.FAIL}" == "fail"
    assert f"{Outcome.ABSTAIN}" == Outcome.ABSTAIN.value
    assert Outcome.PASS == "pass"  # noqa: S105 - an outcome name, not a credential
    assert json.dumps({"outcome": Outcome.ABSTAIN}) == '{"outcome": "abstain"}'
