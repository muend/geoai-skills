"""Shared result type for every verification utility.

One vocabulary across the whole toolkit, so a skill contract can say "run the
check and stop on FAIL" without the author needing to learn seven different
return conventions.

Three outcomes, and the distinction between the last two is the point:

* ``PASS``    — the check ran and found nothing disqualifying.
* ``FAIL``    — the check ran and found a specific, quotable violation.
* ``ABSTAIN`` — the check could not run: input missing, unparseable, or outside
  the check's competence.

``ABSTAIN`` must never be silently treated as ``PASS``. A tool that cannot see
the evidence has not verified anything, and an analysis that proceeds on an
abstention is proceeding unverified. Every caller in this toolkit is written so
that abstention is visible in the output rather than absorbed.

``PASS`` is also narrower than it looks: it means "no disqualifying evidence
was found by this check", not "the work is correct".
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class Outcome(StrEnum):
    """The three outcomes, in the only vocabulary this toolkit accepts.

    `StrEnum` rather than `(str, Enum)` so that formatting an outcome yields
    `pass` and not `Outcome.PASS`. That matters because these values cross
    process boundaries — into `--json` output and into whatever reads a skill's
    verification step — and a caller who interpolates the member directly must
    not silently emit a different string than one who writes `.value`.
    """

    PASS = "pass"  # noqa: S105 - an outcome name, not a credential
    FAIL = "fail"
    ABSTAIN = "abstain"


@dataclass(frozen=True)
class Result:
    outcome: Outcome
    check: str
    reason: str
    evidence: list[str] = field(default_factory=list)
    detail: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Copy the mutable arguments.

        Storing the caller's list by reference let a later `evidence.append(...)`
        rewrite an already-recorded result. An audit trail that the caller can
        edit after the fact is not an audit trail, and this project's first
        operating rule is that evidence is never lost or altered.
        """
        object.__setattr__(self, "evidence", list(self.evidence))
        object.__setattr__(self, "detail", dict(self.detail))

    @property
    def failed(self) -> bool:
        return self.outcome is Outcome.FAIL

    @property
    def abstained(self) -> bool:
        return self.outcome is Outcome.ABSTAIN

    @property
    def ok(self) -> bool:
        """True only for PASS. Abstention is deliberately not ok."""
        return self.outcome is Outcome.PASS

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome.value,
            "check": self.check,
            "reason": self.reason,
            "evidence": list(self.evidence),
            "detail": dict(self.detail),
        }

    def render(self) -> str:
        head = f"[{self.outcome.value.upper():7s}] {self.check}: {self.reason}"
        lines = [head]
        for item in self.evidence:
            lines.append(f"          - {item}")
        return "\n".join(lines)


def passed(check: str, reason: str, **detail: Any) -> Result:
    return Result(Outcome.PASS, check, reason, detail=detail)


def failed(check: str, reason: str, evidence: list[str] | None = None, **detail: Any) -> Result:
    return Result(Outcome.FAIL, check, reason, evidence or [], detail)


def abstained(check: str, reason: str, **detail: Any) -> Result:
    return Result(Outcome.ABSTAIN, check, reason, detail=detail)


@dataclass
class Report:
    """A collection of results with an honest summary.

    The summary never collapses abstentions into passes. ``exit_code`` is 1 on
    any failure and 2 on abstention-without-failure, so a pipeline can tell
    "verified and wrong" apart from "not verified".
    """

    results: list[Result] = field(default_factory=list)

    def add(self, result: Result) -> Result:
        self.results.append(result)
        return result

    @property
    def failures(self) -> list[Result]:
        return [r for r in self.results if r.failed]

    @property
    def abstentions(self) -> list[Result]:
        return [r for r in self.results if r.abstained]

    @property
    def exit_code(self) -> int:
        if self.failures:
            return 1
        if self.abstentions:
            return 2
        return 0

    def summary(self) -> str:
        total = len(self.results)
        n_fail = len(self.failures)
        n_abstain = len(self.abstentions)
        n_pass = total - n_fail - n_abstain
        verdict = {
            0: "verified",
            1: "FAILED",
            2: "NOT VERIFIED (abstained)",
        }[self.exit_code]
        return (
            f"{total} check(s): {n_pass} pass, {n_fail} fail, "
            f"{n_abstain} abstain -> {verdict}"
        )

    def render(self) -> str:
        return "\n".join([r.render() for r in self.results] + ["", self.summary()])

    def to_json(self) -> str:
        return json.dumps(
            {
                "results": [r.to_dict() for r in self.results],
                "exit_code": self.exit_code,
                "summary": self.summary(),
            },
            indent=2,
            ensure_ascii=False,
        )
