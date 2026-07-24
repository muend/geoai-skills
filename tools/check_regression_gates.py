#!/usr/bin/env python3
"""Regression gates that run without spending model budget.

Behaviour and routing quality can only be *measured* by paid model runs, so CI
cannot re-measure them on every pull request. It can, however, block the two
ways quality silently degrades between runs:

Gate A — rubric non-weakening.
    The cheapest way to make a score improve is to delete the criterion that was
    failing. This gate pins every expected and forbidden criterion against a
    committed baseline. A criterion may be added freely, and may be decomposed
    into finer criteria when the decomposition is declared in the baseline, but
    it may never simply disappear or be reworded away.

Gate B — benchmark currency.
    Published benchmark artefacts are computed against one immutable suite hash.
    When a skill or eval changes, that hash changes and the published numbers
    stop describing the current repository. This gate recomputes the suite hash
    and requires every benchmark directory to state, in its README, whether it
    is `current` or `superseded` — and fails when that statement disagrees with
    the computed truth.

Neither gate asserts that quality is good. They assert that a change cannot
quietly remove a requirement or leave a stale number presenting itself as
current.

Usage:
    python tools/check_regression_gates.py
    python tools/check_regression_gates.py --write-baseline   # seed/refresh Gate A
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.eval_runner import load_suite

ROOT = Path(__file__).resolve().parent.parent
BASELINE_PATH = ROOT / "evals" / "rubric-baseline.json"
BENCHMARKS_DIR = ROOT / "benchmarks"

SUITE_STATE_PATTERN = re.compile(
    r"^-?\s*Suite state:\s*`?(current|superseded)`?", re.IGNORECASE | re.MULTILINE
)


class GateFailure(Exception):
    """Raised when a regression gate rejects the working tree."""


# ---------------------------------------------------------------------------
# Gate A — rubric non-weakening
# ---------------------------------------------------------------------------


def current_rubric() -> dict[str, dict[str, list[str]]]:
    cases, _suite_sha256, _skills = load_suite()
    return {
        case["case_id"]: {
            "expected_behavior": list(case["expected_behavior"]),
            "forbidden_behavior": list(case["forbidden_behavior"]),
        }
        for case in cases
    }


def build_baseline() -> dict[str, Any]:
    _cases, suite_sha256, skills = load_suite()
    return {
        "note": (
            "Pinned expected and forbidden criteria. A criterion may be added, or "
            "decomposed into finer criteria when the decomposition is declared "
            "below, but it may never be silently removed or reworded away. This "
            "baseline is forward-looking: it constrains changes made after it was "
            "seeded, and makes no claim about the history before that point."
        ),
        "seeded_from_suite_sha256": suite_sha256,
        "seeded_skill_count": len(skills),
        "decompositions": {},
        "cases": current_rubric(),
    }


def _decomposition_map(baseline: dict[str, Any]) -> dict[tuple[str, str], list[str]]:
    """(case_id, replaced criterion) -> declared replacement criteria."""
    mapping: dict[tuple[str, str], list[str]] = {}
    for case_id, entries in baseline.get("decompositions", {}).items():
        for entry in entries:
            replacements = list(entry["with"])
            if len(replacements) < 2:
                raise GateFailure(
                    f"{case_id}: a declared decomposition must name at least two "
                    f"replacement criteria; got {len(replacements)}"
                )
            mapping[(case_id, entry["replaced"])] = replacements
    return mapping


def check_rubric_not_weakened(baseline: dict[str, Any]) -> list[str]:
    current = current_rubric()
    decompositions = _decomposition_map(baseline)
    failures: list[str] = []

    for case_id, pinned in baseline["cases"].items():
        live = current.get(case_id)
        if live is None:
            failures.append(
                f"{case_id}: case was removed from the suite. Removing a pinned case "
                f"is never silent — declare it explicitly if it is intended."
            )
            continue

        for criterion in pinned["expected_behavior"]:
            if criterion in live["expected_behavior"]:
                continue
            replacements = decompositions.get((case_id, criterion))
            if replacements is None:
                failures.append(
                    f"{case_id}: expected criterion disappeared without a declared "
                    f"decomposition:\n      {criterion!r}"
                )
                continue
            missing = [r for r in replacements if r not in live["expected_behavior"]]
            if missing:
                failures.append(
                    f"{case_id}: declared decomposition of\n      {criterion!r}\n"
                    f"    is incomplete; these replacements are absent:\n      "
                    + "\n      ".join(repr(m) for m in missing)
                )

        for criterion in pinned["forbidden_behavior"]:
            if criterion not in live["forbidden_behavior"]:
                failures.append(
                    f"{case_id}: forbidden criterion disappeared. Prohibitions are "
                    f"never decomposed away:\n      {criterion!r}"
                )

    return failures


# ---------------------------------------------------------------------------
# Gate B — benchmark currency
# ---------------------------------------------------------------------------


def check_benchmark_currency() -> list[str]:
    if not BENCHMARKS_DIR.exists():
        return []

    _cases, current_suite_sha256, skills = load_suite()
    failures: list[str] = []

    for metrics_path in sorted(BENCHMARKS_DIR.glob("*/metrics.json")):
        directory = metrics_path.parent
        metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
        published = metrics.get("suite_sha256")
        is_current = published == current_suite_sha256
        truth = "current" if is_current else "superseded"

        readme = directory / "README.md"
        if not readme.exists():
            failures.append(
                f"{directory.name}: no README.md, so its suite state is undeclared. "
                f"Add a 'Suite state: {truth}' line."
            )
            continue

        match = SUITE_STATE_PATTERN.search(readme.read_text(encoding="utf-8"))
        if match is None:
            failures.append(
                f"{directory.name}: README.md does not declare a suite state. "
                f"Add a line reading 'Suite state: {truth}'."
            )
            continue

        declared = match.group(1).lower()
        if declared != truth:
            detail = (
                f"published suite {published[:12]}… vs current "
                f"{current_suite_sha256[:12]}… ({len(skills)} skills)"
            )
            failures.append(
                f"{directory.name}: README.md declares 'Suite state: {declared}' but "
                f"the computed state is '{truth}' ({detail}). A benchmark may not "
                f"present numbers from one suite as describing another."
            )

    return failures


# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write-baseline",
        action="store_true",
        help="Seed or refresh the rubric baseline from the current suite.",
    )
    args = parser.parse_args(argv)

    if args.write_baseline:
        existing = (
            json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
            if BASELINE_PATH.exists()
            else {}
        )
        baseline = build_baseline()
        # Declared decompositions are hand-written; never discard them.
        baseline["decompositions"] = existing.get("decompositions", {})
        BASELINE_PATH.write_text(
            json.dumps(baseline, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"Wrote {BASELINE_PATH.relative_to(ROOT)}")
        print(f"  pinned cases: {len(baseline['cases'])}")
        print(f"  suite: {baseline['seeded_from_suite_sha256']}")
        return 0

    if not BASELINE_PATH.exists():
        print(
            f"error: {BASELINE_PATH.relative_to(ROOT)} is missing. "
            f"Seed it with --write-baseline.",
            file=sys.stderr,
        )
        return 1

    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))

    try:
        rubric_failures = check_rubric_not_weakened(baseline)
    except GateFailure as error:
        print(f"Gate A — rubric non-weakening: FAIL\n  {error}", file=sys.stderr)
        return 1
    benchmark_failures = check_benchmark_currency()

    for title, failures in (
        ("Gate A — rubric non-weakening", rubric_failures),
        ("Gate B — benchmark currency", benchmark_failures),
    ):
        if failures:
            print(f"{title}: FAIL", file=sys.stderr)
            for failure in failures:
                print(f"  - {failure}", file=sys.stderr)
        else:
            print(f"{title}: pass")

    if rubric_failures or benchmark_failures:
        print(
            "\nThese gates do not measure quality; they prevent a requirement from "
            "being removed and a stale benchmark from presenting itself as current.",
            file=sys.stderr,
        )
        return 1

    print(f"\n{len(baseline['cases'])} pinned cases checked; no regression detected.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
