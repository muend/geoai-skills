"""Tests for the dev / held-out split and Gate C.

The split's value rests entirely on two properties, so both are measured here
rather than asserted in prose:

* a case that was read during quality work can never reach held-out, and a case
  written blind can never reach dev — otherwise the split launders the very
  contamination it exists to record;
* a benchmark cannot report held-out numbers without a disclosure that names the
  exact split it was made against.

The negative tests matter more than the positive ones. A gate that passes when
everything is fine but also passes when someone leaks the held-out set is worse
than no gate, because it manufactures confidence.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.build_split import (
    SEED,
    SplitError,
    assignment_sha256,
    build,
    load_cases,
    load_inputs,
    primary_type,
    serialise,
)
from tools.check_regression_gates import check_holdout_containment

ROOT = Path(__file__).resolve().parents[1]
SPLIT_PATH = ROOT / "evals" / "split.json"
INPUTS_PATH = ROOT / "evals" / "split-inputs.json"


@pytest.fixture(scope="module")
def committed() -> dict:
    return json.loads(SPLIT_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def rebuilt() -> dict:
    return build(load_cases(), *load_inputs())


# --- the split itself ----------------------------------------------------


def test_the_committed_split_matches_the_current_suite(committed: dict, rebuilt: dict) -> None:
    """Adding cases without regenerating leaves 'held-out' naming a stale set."""
    assert committed["assignment_sha256"] == rebuilt["assignment_sha256"]


def test_the_halves_are_disjoint_and_cover_everything(committed: dict) -> None:
    dev, holdout = set(committed["dev"]), set(committed["holdout"])
    cases = set(load_cases())

    assert dev.isdisjoint(holdout)
    assert dev | holdout == cases
    assert len(dev) + len(holdout) == committed["case_count"]


def test_rebuilding_is_byte_identical(rebuilt: dict) -> None:
    """A split that drifts between runs cannot be cited in a published result."""
    again = build(load_cases(), *load_inputs())

    assert serialise(again) == serialise(rebuilt)


def test_the_seed_is_pinned_in_the_committed_file(committed: dict) -> None:
    assert committed["seed"] == SEED


def test_every_analysed_case_is_in_dev(committed: dict) -> None:
    """The whole point: a case read during tuning cannot judge the tuning."""
    analysed, _blind = load_inputs()

    assert analysed <= set(committed["dev"])
    assert set(committed["forced_to_dev_because_analysed"]) == analysed


def test_every_blind_case_is_held_out(committed: dict) -> None:
    _analysed, blind = load_inputs()

    assert blind <= set(committed["holdout"])
    assert set(committed["forced_to_holdout_because_blind"]) == blind


def test_every_skill_keeps_a_held_out_case(committed: dict) -> None:
    """A skill with no held-out case is silently exempt from the discipline."""
    cases = load_cases()
    holdout = set(committed["holdout"])
    skills_with_holdout = {cases[c]["skill"] for c in holdout}

    assert skills_with_holdout == {meta["skill"] for meta in cases.values()}


def test_every_skill_has_at_least_one_blind_case(committed: dict) -> None:
    """Held out by choice is weaker than written blind; measure which we have.

    If this ever fails, the fix is to write a blind case for the named skill —
    not to relax the test. A skill whose only held-out cases were chosen by us
    has a check we could have gamed.
    """
    cases = load_cases()
    blind = set(committed["forced_to_holdout_because_blind"])
    covered = {cases[c]["skill"] for c in blind}

    uncovered = sorted({meta["skill"] for meta in cases.values()} - covered)
    assert not uncovered, f"no blind case for: {uncovered}"


def test_negative_cases_exist_in_both_halves(committed: dict) -> None:
    """False firing has to be measurable on the held-out side too."""
    cases = load_cases()
    dev, holdout = set(committed["dev"]), set(committed["holdout"])
    negatives = {c for c, m in cases.items() if "negative" in m["case_types"]}

    assert negatives & dev
    assert negatives & holdout


def test_the_assignment_hash_ignores_prose(committed: dict) -> None:
    """Editing the note must not invalidate a published disclosure."""
    edited = dict(committed, note="rewritten entirely")

    assert assignment_sha256(edited) == committed["assignment_sha256"]


# --- input validation ----------------------------------------------------


def test_a_case_cannot_be_both_analysed_and_blind(tmp_path: Path) -> None:
    path = tmp_path / "split-inputs.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "analysed_before_split": ["a/one"],
                "written_blind": ["a/one"],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(SplitError, match="self-contradictory"):
        load_inputs(path)


def test_an_input_naming_a_missing_case_is_refused() -> None:
    """Renaming a case would otherwise drop it from the split in silence."""
    cases = load_cases()

    with pytest.raises(SplitError, match="not in the suite"):
        build(cases, {"nonexistent-skill/ghost"}, set())


def test_a_skill_whose_every_case_was_analysed_is_an_error() -> None:
    """Better to demand a blind case than to promote a contaminated one."""
    cases = load_cases()
    one_skill = next(iter(cases.values()))["skill"]
    analysed = {c for c, m in cases.items() if m["skill"] == one_skill}

    with pytest.raises(SplitError, match="no independent check is possible"):
        build(cases, analysed, set())


def test_primary_type_prefers_the_most_informative_label() -> None:
    assert primary_type(["positive", "collision"]) == "collision"
    assert primary_type(["positive", "ambiguous"]) == "ambiguous"
    assert primary_type(["positive"]) == "positive"
    assert primary_type([]) == "unknown"


# --- Gate C --------------------------------------------------------------


def test_gate_c_passes_on_the_committed_tree() -> None:
    assert check_holdout_containment() == []


def _benchmark(tmp_path: Path, metrics: dict, readme: str | None = None) -> Path:
    directory = tmp_path / "benchmarks" / "run"
    directory.mkdir(parents=True)
    (directory / "metrics.json").write_text(
        json.dumps(metrics), encoding="utf-8", newline=""
    )
    if readme is not None:
        (directory / "README.md").write_text(readme, encoding="utf-8", newline="")
    return directory


@pytest.fixture
def gate_c(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, committed: dict):
    """Point Gate C at a scratch benchmarks directory, keeping the real split."""
    from tools import check_regression_gates as gates

    monkeypatch.setattr(gates, "BENCHMARKS_DIR", tmp_path / "benchmarks")
    _cases, suite_sha256, _skills = gates.load_suite()

    def run(metrics: dict, readme: str | None = None) -> list[str]:
        _benchmark(tmp_path, metrics, readme)
        return gates.check_holdout_containment()

    run.suite_sha256 = suite_sha256  # type: ignore[attr-defined]
    run.assignment = committed["assignment_sha256"]  # type: ignore[attr-defined]
    run.pop = gates.scope_populations(committed)  # type: ignore[attr-defined]
    return run


def test_a_benchmark_without_a_scope_is_refused(gate_c) -> None:
    failures = gate_c({"suite_sha256": gate_c.suite_sha256, "kind": "routing"})

    assert any("does not declare a `scope`" in f for f in failures)


def test_an_unknown_scope_is_refused(gate_c) -> None:
    failures = gate_c({"suite_sha256": gate_c.suite_sha256, "scope": "everything"})

    assert any("unknown scope" in f for f in failures)


def test_a_dev_scoped_run_reporting_the_full_suite_is_caught(gate_c) -> None:
    """The leak this gate exists for, expressed as arithmetic.

    A run that says 'dev' but reports every case has measured the held-out set
    and mislabelled it. No per-case rows are needed to see that.
    """
    failures = gate_c(
        {
            "suite_sha256": gate_c.suite_sha256,
            "scope": "dev",
            "kind": "all",
            "case_mix": {"total": gate_c.pop[("full", "all")]},
        }
    )

    assert any("the arithmetic does not permit both" in f for f in failures)


def test_a_correctly_counted_dev_run_passes(gate_c) -> None:
    failures = gate_c(
        {
            "suite_sha256": gate_c.suite_sha256,
            "scope": "dev",
            "kind": "all",
            "case_mix": {"total": gate_c.pop[("dev", "all")]},
        }
    )

    assert failures == []


def test_a_holdout_run_without_a_disclosure_is_refused(gate_c) -> None:
    failures = gate_c(
        {
            "suite_sha256": gate_c.suite_sha256,
            "scope": "holdout",
            "kind": "all",
            "case_mix": {"total": gate_c.pop[("holdout", "all")]},
        },
        readme="# Run\n\nNothing declared.\n",
    )

    assert any("must carry a line reading" in f for f in failures)


def test_a_holdout_run_with_the_right_disclosure_passes(gate_c) -> None:
    failures = gate_c(
        {
            "suite_sha256": gate_c.suite_sha256,
            "scope": "holdout",
            "kind": "all",
            "case_mix": {"total": gate_c.pop[("holdout", "all")]},
        },
        readme=f"# Run\n\n- Held-out disclosure: `{gate_c.assignment}`\n",
    )

    assert failures == []


def test_a_disclosure_for_a_different_split_is_refused(gate_c) -> None:
    """Otherwise one disclosure would license every future held-out run."""
    failures = gate_c(
        {
            "suite_sha256": gate_c.suite_sha256,
            "scope": "holdout",
            "kind": "all",
            "case_mix": {"total": gate_c.pop[("holdout", "all")]},
        },
        readme="# Run\n\n- Held-out disclosure: `" + "0" * 64 + "`\n",
    )

    assert any("made against a different split" in f for f in failures)


# --- Gate C: scope and kind cut the suite along different axes ------------


def test_a_routing_benchmark_is_measured_against_the_routing_population(
    gate_c,
) -> None:
    """The defect this pins.

    An earlier Gate C compared `case_mix.total` against the whole split half, so
    a routing-only run over the dev half — which covers neither 96 dev cases nor
    all 74 routing cases, but their intersection — was rejected for being
    honest. The first benchmark this project intends to publish is exactly that
    shape, and the gate would have blocked it.
    """
    passing = gate_c(
        {
            "suite_sha256": gate_c.suite_sha256,
            "scope": "dev",
            "kind": "routing",
            "case_mix": {"total": gate_c.pop[("dev", "routing")]},
        }
    )

    assert passing == []
    assert gate_c.pop[("dev", "routing")] < gate_c.pop[("dev", "all")]


def test_a_routing_run_claiming_the_whole_dev_half_is_still_caught(gate_c) -> None:
    """Widening the population must not turn the gate off."""
    failures = gate_c(
        {
            "suite_sha256": gate_c.suite_sha256,
            "scope": "dev",
            "kind": "routing",
            "case_mix": {"total": gate_c.pop[("dev", "all")]},
        }
    )

    assert any("the arithmetic does not permit both" in f for f in failures)


def test_a_behaviour_benchmark_is_measured_against_the_behaviour_population(
    gate_c,
) -> None:
    failures = gate_c(
        {
            "suite_sha256": gate_c.suite_sha256,
            "scope": "holdout",
            "kind": "behavior",
            "case_mix": {"total": gate_c.pop[("holdout", "behavior")]},
        },
        readme=f"# Run\n\n- Held-out disclosure: `{gate_c.assignment}`\n",
    )

    assert failures == []


def test_the_populations_partition_each_half(gate_c) -> None:
    """routing + behaviour must exhaust the half, or a class is unaccounted for."""
    for scope in ("dev", "holdout", "full"):
        routing = gate_c.pop[(scope, "routing")]
        behaviour = gate_c.pop[(scope, "behavior")]
        assert routing + behaviour == gate_c.pop[(scope, "all")], scope


def test_a_current_benchmark_without_a_kind_is_refused(gate_c) -> None:
    """Without a kind the expected population is undecidable, not merely unknown."""
    failures = gate_c(
        {
            "suite_sha256": gate_c.suite_sha256,
            "scope": "dev",
            "case_mix": {"total": gate_c.pop[("dev", "routing")]},
        }
    )

    assert any("no `kind`" in f for f in failures)


def test_an_unknown_kind_is_refused(gate_c) -> None:
    failures = gate_c(
        {
            "suite_sha256": gate_c.suite_sha256,
            "scope": "dev",
            "kind": "vibes",
            "case_mix": {"total": 1},
        }
    )

    assert any("unknown kind" in f for f in failures)


def test_pre_split_is_refused_on_a_current_suite(gate_c) -> None:
    """The escape hatch must not become the default."""
    failures = gate_c({"suite_sha256": gate_c.suite_sha256, "scope": "pre-split"})

    assert any("only honest for a run finished before" in f for f in failures)


def test_pre_split_is_accepted_on_a_superseded_suite(gate_c) -> None:
    failures = gate_c({"suite_sha256": "0" * 64, "scope": "pre-split"})

    assert failures == []


def test_a_superseded_run_is_not_held_to_the_current_case_counts(gate_c) -> None:
    """Its population no longer exists; only the label is checkable."""
    failures = gate_c(
        {"suite_sha256": "0" * 64, "scope": "dev", "case_mix": {"total": 7}}
    )

    assert failures == []


def test_a_missing_split_file_fails_loudly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tools import check_regression_gates as gates

    monkeypatch.setattr(gates, "SPLIT_PATH", tmp_path / "absent.json")

    failures = gates.check_holdout_containment()

    assert any("evals/split.json is missing" in f for f in failures)


def test_a_stale_split_file_fails_loudly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, committed: dict
) -> None:
    """A split generated before the last batch of cases is not a split."""
    from tools import check_regression_gates as gates

    stale = dict(committed, assignment_sha256="f" * 64)
    path = tmp_path / "split.json"
    path.write_text(json.dumps(stale), encoding="utf-8", newline="")
    monkeypatch.setattr(gates, "SPLIT_PATH", path)

    failures = gates.check_holdout_containment()

    assert any("is stale" in f for f in failures)


def test_the_inputs_file_lists_only_real_cases() -> None:
    """Committed inputs are reviewed by hand, so pin that they resolve."""
    analysed, blind = load_inputs(INPUTS_PATH)
    cases = set(load_cases())

    assert (analysed | blind) <= cases
