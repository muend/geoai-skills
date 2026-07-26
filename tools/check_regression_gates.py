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

Gate C — held-out containment.
    A held-out case is worthless the moment someone tunes against it. The suite
    is public, so nothing can stop a person reading one; what can be stopped is
    a benchmark quietly reporting held-out numbers as if they were routine. This
    gate requires every benchmark to declare which population it measured, checks
    that declaration against the arithmetic of the committed split, and makes
    publishing held-out results a deliberate, reviewable act rather than a
    default.

None of the three gates asserts that quality is good. They assert that a change
cannot quietly remove a requirement, leave a stale number presenting itself as
current, or spend the held-out set without saying so.

Usage:
    python tools/check_regression_gates.py
    python tools/check_regression_gates.py --write-baseline   # seed/refresh Gate A
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.build_split import SplitError, build, load_cases, load_inputs
from tools.eval_runner import EvalRunnerError, load_suite, select_cases, sha256_json

ROOT = Path(__file__).resolve().parent.parent
BASELINE_PATH = ROOT / "evals" / "rubric-baseline.json"
SPLIT_PATH = ROOT / "evals" / "split.json"
BENCHMARKS_DIR = ROOT / "benchmarks"

SUITE_STATE_PATTERN = re.compile(
    r"^-?\s*Suite state:\s*`?(current|superseded)`?", re.IGNORECASE | re.MULTILINE
)
DISCLOSURE_PATTERN = re.compile(
    r"^-?\s*Held-out disclosure:\s*`?([a-f0-9]{64})`?", re.IGNORECASE | re.MULTILINE
)

VALID_SCOPES = ("dev", "holdout", "full", "pre-split")

# A benchmark covers a case *class* as well as a split half, and the two are
# independent: a routing-scoped run over the dev half covers neither 96 cases
# (the dev half) nor 74 (all routing cases) but their intersection.
#
# The field that says which cases ran is `evaluation_scope`, copied from the run
# manifest — NOT `kind`. `kind` says which metrics are reported, and the two come
# apart: the first published benchmark here has `kind: "routing"` and a
# `case_mix.total` of 120, the whole suite of its era, because routing metrics
# were computed from a full-suite run. Keying the population on `kind` would
# reject that shape, which is the more common one.
VALID_EVAL_SCOPES = ("routing", "behavior", "all")


class GateFailure(Exception):
    """Raised when a regression gate rejects the working tree."""


# ---------------------------------------------------------------------------
# Gate A — rubric non-weakening
# ---------------------------------------------------------------------------


def current_rubric() -> dict[str, dict[str, list[str]]]:
    cases, _suite_sha256, _skills = suite()
    return {
        case["case_id"]: {
            "expected_behavior": list(case["expected_behavior"]),
            "forbidden_behavior": list(case["forbidden_behavior"]),
        }
        for case in cases
    }


def build_baseline() -> dict[str, Any]:
    _cases, suite_sha256, skills = suite()
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


def expected_population_sha256(metrics: dict[str, Any], fallback: str) -> str:
    """The hash a benchmark's declared population should have today.

    Measured problem this solves: a narrow run records the hash of the cases it
    covered, not of the whole suite — `--scope behavior` is documented as
    producing its own suite hash. Comparing every benchmark against the
    full-suite hash therefore forced a freshly computed behaviour benchmark to
    declare `superseded`, which is false in the other direction: the 84-case
    behaviour population still exists, and the numbers do describe the current
    skills. The label was wrong either way, so the comparison has to know which
    population was run.

    Falls back to the full-suite hash when the benchmark declares no scope, which
    is the pre-split shape.
    """
    scope = metrics.get("scope")
    evaluated = metrics.get("evaluation_scope", "all")
    if scope not in SPLIT_FOR_SCOPE or evaluated not in VALID_EVAL_SCOPES:
        return fallback
    try:
        return population_sha256(scope, evaluated)
    except (EvalRunnerError, KeyError):
        # An unbuildable population is Gate C's business to report; currency
        # falls back rather than raising twice for one cause.
        return fallback


def check_benchmark_currency() -> list[str]:
    if not BENCHMARKS_DIR.exists():
        return []

    _cases, current_suite_sha256, skills = suite()
    failures: list[str] = []

    for metrics_path in sorted(BENCHMARKS_DIR.glob("*/metrics.json")):
        directory = metrics_path.parent
        metrics = json.loads(metrics_path.read_text(encoding="utf-8-sig"))
        published = metrics.get("suite_sha256")
        expected = expected_population_sha256(metrics, current_suite_sha256)
        is_current = published == expected
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
            scope_note = (
                f"scope '{metrics.get('scope')}' / evaluation_scope "
                f"'{metrics.get('evaluation_scope', 'all')}'"
            )
            detail = (
                f"published suite {str(published)[:12]}… vs the {scope_note} "
                f"population's current hash {expected[:12]}… ({len(skills)} skills)"
            )
            failures.append(
                f"{directory.name}: README.md declares 'Suite state: {declared}' but "
                f"the computed state is '{truth}' ({detail}). A benchmark may not "
                f"present numbers from one suite as describing another."
            )

    return failures


# ---------------------------------------------------------------------------
# Gate C — held-out containment
# ---------------------------------------------------------------------------


SPLIT_FOR_SCOPE = {"dev": "dev", "holdout": "holdout", "full": "all"}


@lru_cache(maxsize=1)
def _suite() -> tuple[tuple[dict[str, Any], ...], str, tuple[str, ...]]:
    """Parse and validate the suite once per process.

    All three gates need it, and each was re-reading and re-validating eighteen
    eval files. Safe to cache because this is a short-lived CLI; a caller that
    edits eval files mid-process would need to clear it, which nothing does.
    """
    cases, suite_sha256, skills = load_suite()
    return tuple(cases), suite_sha256, tuple(skills)


def suite() -> tuple[list[dict[str, Any]], str, list[str]]:
    cases, suite_sha256, skills = _suite()
    return [dict(case) for case in cases], suite_sha256, list(skills)


def population(scope: str, evaluation_scope: str) -> list[dict[str, Any]]:
    """The cases a run declaring (scope, evaluation_scope) should have covered.

    Delegates to `select_cases`, the same function `prepare` uses to build a
    manifest. That shared definition is the point: if the gates carried their own
    copy of the filtering rules, a benchmark's declared population and the
    population the harness actually ran could drift apart silently, and the gates
    would keep passing while the numbers described something else.
    """
    cases, _suite_sha256, _skills = suite()
    return select_cases(
        cases,
        evaluation_scope=evaluation_scope,
        split=SPLIT_FOR_SCOPE[scope],
        split_path=SPLIT_PATH,
    )


def population_sha256(scope: str, evaluation_scope: str) -> str:
    return sha256_json(population(scope, evaluation_scope))


def scope_populations(committed: dict[str, Any]) -> dict[tuple[str, str], int]:
    """(scope, evaluation_scope) -> how many cases that combination should cover.

    Keyed on both because they cut the suite along different axes: `scope` picks
    a split half, `evaluation_scope` picks which case classes ran. `routing` and
    `all` coincide — a routing run keeps every case, because activation is
    observable on a behaviour case too — and only `behavior` narrows. The
    `routing-only-cases` entry counts the cases that are *not* behaviour-judged;
    it exists for reporting and for the test that the two classes partition each
    half, not for the arithmetic check.
    """
    cases = load_cases()
    routing_only = {
        case_id
        for case_id, meta in cases.items()
        if meta["behavior_class"] == "routing-only"
    }
    halves = {
        "dev": set(committed.get("dev", [])),
        "holdout": set(committed.get("holdout", [])),
    }
    halves["full"] = halves["dev"] | halves["holdout"]

    sizes: dict[tuple[str, str], int] = {}
    for scope, members in halves.items():
        sizes[(scope, "routing")] = len(members)
        sizes[(scope, "all")] = len(members)
        sizes[(scope, "behavior")] = len(members - routing_only)
        sizes[(scope, "routing-only-cases")] = len(members & routing_only)
    return sizes


def check_holdout_containment() -> list[str]:
    """Two questions: is the split current, and does any benchmark spend it?

    The second cannot be answered from case ids, because `metrics.json` publishes
    aggregates, not per-case rows. So it is answered from arithmetic instead: a
    benchmark that says it measured the dev half must report the dev half's case
    count. A number that does not add up is evidence; a promise is not.
    """
    failures: list[str] = []

    if not SPLIT_PATH.exists():
        return [
            "evals/split.json is missing, so no benchmark can state which "
            "population it measured. Generate it with "
            "`python tools/build_split.py --write`."
        ]

    committed = json.loads(SPLIT_PATH.read_text(encoding="utf-8-sig"))

    try:
        expected = build(load_cases(), *load_inputs())
    except SplitError as error:
        return [f"the split cannot be rebuilt, so it cannot be trusted: {error}"]

    if committed.get("assignment_sha256") != expected["assignment_sha256"]:
        failures.append(
            "evals/split.json is stale: the current suite and inputs produce a "
            f"different assignment ({expected['assignment_sha256'][:12]}… vs the "
            f"committed {str(committed.get('assignment_sha256'))[:12]}…). Cases "
            "were probably added without re-running "
            "`python tools/build_split.py --write`. Until it is regenerated, "
            "'held-out' does not name a definite set of cases."
        )
        # Keep going: the per-benchmark declarations are still worth checking,
        # and reporting only the first problem hides the rest.

    population = scope_populations(committed)
    assignment = committed.get("assignment_sha256")

    if not BENCHMARKS_DIR.exists():
        return failures

    _cases, current_suite_sha256, _skills = suite()

    for metrics_path in sorted(BENCHMARKS_DIR.glob("*/metrics.json")):
        directory = metrics_path.parent
        name = directory.name
        metrics = json.loads(metrics_path.read_text(encoding="utf-8-sig"))
        scope = metrics.get("scope")
        # Currency is judged against the population the run declares, matching
        # Gate B. Using the full-suite hash here would treat every narrow-scope
        # benchmark as superseded and quietly skip the count check below —
        # turning the gate off for exactly the runs it most needs to bound.
        suite_is_current = metrics.get("suite_sha256") == expected_population_sha256(
            metrics, current_suite_sha256
        )

        if scope is None:
            failures.append(
                f"{name}: metrics.json does not declare a `scope`. Add one of "
                f"{list(VALID_SCOPES)} — a benchmark that does not say which "
                f"population it measured cannot be read honestly."
            )
            continue
        if scope not in VALID_SCOPES:
            failures.append(
                f"{name}: unknown scope {scope!r}; expected one of {list(VALID_SCOPES)}."
            )
            continue

        if scope == "pre-split":
            if suite_is_current:
                failures.append(
                    f"{name}: scope is 'pre-split' but its suite hash is the "
                    f"current one, so the split does apply to it. 'pre-split' is "
                    f"only honest for a run finished before the split existed."
                )
            continue

        reported = metrics.get("case_mix", {}).get("total")
        if suite_is_current and reported is not None:
            evaluated = metrics.get("evaluation_scope")
            if evaluated is None:
                failures.append(
                    f"{name}: declares scope '{scope}' but no `evaluation_scope`, "
                    f"so which cases it ran — and therefore the population it "
                    f"should cover — is undecidable. Copy the field from the run "
                    f"manifest; one of {list(VALID_EVAL_SCOPES)}."
                )
            elif evaluated not in VALID_EVAL_SCOPES:
                failures.append(
                    f"{name}: unknown evaluation_scope {evaluated!r}; expected one "
                    f"of {list(VALID_EVAL_SCOPES)}."
                )
            elif reported != population[(scope, evaluated)]:
                failures.append(
                    f"{name}: declares split scope '{scope}' and evaluation_scope "
                    f"'{evaluated}' but reports {reported} cases, and that "
                    f"population holds {population[(scope, evaluated)]}. Either a "
                    f"label or the run is wrong; the arithmetic does not permit "
                    f"both."
                )

        if scope in ("holdout", "full"):
            readme = directory / "README.md"
            text = readme.read_text(encoding="utf-8") if readme.exists() else ""
            match = DISCLOSURE_PATTERN.search(text)
            if match is None:
                failures.append(
                    f"{name}: scope '{scope}' includes held-out cases, so its "
                    f"README.md must carry a line reading\n"
                    f"      Held-out disclosure: {assignment}\n"
                    f"    Spending the held-out set is allowed once and has to be "
                    f"visible in the diff that does it."
                )
            elif match.group(1).lower() != assignment:
                failures.append(
                    f"{name}: the held-out disclosure names assignment "
                    f"{match.group(1)[:12]}… but the committed split is "
                    f"{str(assignment)[:12]}…. The disclosure was made against a "
                    f"different split, so it does not cover these cases."
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
            json.loads(BASELINE_PATH.read_text(encoding="utf-8-sig"))
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

    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8-sig"))

    try:
        rubric_failures = check_rubric_not_weakened(baseline)
    except GateFailure as error:
        print(f"Gate A — rubric non-weakening: FAIL\n  {error}", file=sys.stderr)
        return 1
    benchmark_failures = check_benchmark_currency()
    holdout_failures = check_holdout_containment()

    for title, failures in (
        ("Gate A — rubric non-weakening", rubric_failures),
        ("Gate B — benchmark currency", benchmark_failures),
        ("Gate C — held-out containment", holdout_failures),
    ):
        if failures:
            print(f"{title}: FAIL", file=sys.stderr)
            for failure in failures:
                print(f"  - {failure}", file=sys.stderr)
        else:
            print(f"{title}: pass")

    if rubric_failures or benchmark_failures or holdout_failures:
        print(
            "\nThese gates do not measure quality. They prevent a requirement from "
            "being removed, a stale benchmark from presenting itself as current, "
            "and the held-out set from being spent without saying so.",
            file=sys.stderr,
        )
        return 1

    split = json.loads(SPLIT_PATH.read_text(encoding="utf-8-sig"))
    print(
        f"\n{len(baseline['cases'])} pinned cases checked; no regression detected.\n"
        f"Split: dev {len(split['dev'])} / held-out {len(split['holdout'])}, "
        f"assignment {split['assignment_sha256'][:12]}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
