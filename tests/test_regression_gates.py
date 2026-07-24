"""Tests for the no-model-call CI regression gates.

The gates exist because behaviour and routing quality can only be measured by
paid model runs, so CI cannot re-measure them per pull request. What CI *can*
block is the two ways quality silently degrades between runs: deleting the
criterion that was failing, and leaving a stale benchmark presenting itself as
current.

These tests prove the gates actually catch those two moves. A guard that only
ever passes is worse than no guard, because it manufactures confidence.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools import check_regression_gates as gates

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def baseline() -> dict:
    return json.loads(gates.BASELINE_PATH.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# The gates must pass on the committed tree
# ---------------------------------------------------------------------------


def test_baseline_exists_and_pins_the_whole_suite(baseline: dict) -> None:
    current = gates.current_rubric()

    assert baseline["cases"], "baseline pins no cases"
    assert set(baseline["cases"]) == set(current), (
        "baseline and live suite disagree on which cases exist; "
        "refresh with --write-baseline and review the diff"
    )


def test_both_gates_pass_on_the_committed_tree(baseline: dict) -> None:
    assert gates.check_rubric_not_weakened(baseline) == []
    assert gates.check_benchmark_currency() == []


# ---------------------------------------------------------------------------
# Gate A must reject silent weakening
# ---------------------------------------------------------------------------


def test_gate_a_rejects_a_silently_deleted_expected_criterion(baseline: dict) -> None:
    case_id, pinned = next(
        (cid, c) for cid, c in baseline["cases"].items() if c["expected_behavior"]
    )
    tampered = json.loads(json.dumps(baseline))
    tampered["cases"][case_id]["expected_behavior"].append(
        "A requirement that the live suite does not contain"
    )

    failures = gates.check_rubric_not_weakened(tampered)

    assert any("disappeared without a declared decomposition" in f for f in failures)
    assert any(case_id in f for f in failures)
    assert pinned["expected_behavior"]  # sanity: the fixture case was non-trivial


def test_gate_a_rejects_a_silently_deleted_forbidden_criterion(baseline: dict) -> None:
    case_id = next(
        cid for cid, c in baseline["cases"].items() if c["forbidden_behavior"]
    )
    tampered = json.loads(json.dumps(baseline))
    tampered["cases"][case_id]["forbidden_behavior"].append(
        "Must not do something the live suite never prohibited"
    )

    failures = gates.check_rubric_not_weakened(tampered)

    assert any("Prohibitions are never decomposed away" in f for f in failures)


def test_gate_a_rejects_a_removed_case(baseline: dict) -> None:
    tampered = json.loads(json.dumps(baseline))
    tampered["cases"]["nonexistent-skill/nonexistent-case"] = {
        "expected_behavior": ["anything"],
        "forbidden_behavior": [],
    }

    failures = gates.check_rubric_not_weakened(tampered)

    assert any("case was removed from the suite" in f for f in failures)


# ---------------------------------------------------------------------------
# Gate A must allow declared decomposition — the legitimate path
# ---------------------------------------------------------------------------


def test_gate_a_allows_a_fully_declared_decomposition(baseline: dict) -> None:
    case_id = "geo-data-engineering/crs-loss-audit"
    live = gates.current_rubric()[case_id]["expected_behavior"]
    replacements = [c for c in live if "accounting" in c]
    assert len(replacements) >= 2, "expected the accounting row to be split already"

    tampered = json.loads(json.dumps(baseline))
    old = "Adds row, null-geometry, validity, and extent accounting to the pipeline"
    tampered["cases"][case_id]["expected_behavior"].append(old)
    tampered["decompositions"][case_id] = [{"replaced": old, "with": replacements}]

    assert gates.check_rubric_not_weakened(tampered) == []


def test_gate_a_rejects_an_incomplete_decomposition(baseline: dict) -> None:
    case_id = "geo-data-engineering/crs-loss-audit"
    tampered = json.loads(json.dumps(baseline))
    old = "Adds row, null-geometry, validity, and extent accounting to the pipeline"
    tampered["cases"][case_id]["expected_behavior"].append(old)
    tampered["decompositions"][case_id] = [
        {
            "replaced": old,
            "with": [
                gates.current_rubric()[case_id]["expected_behavior"][0],
                "A replacement criterion that was never actually added",
            ],
        }
    ]

    failures = gates.check_rubric_not_weakened(tampered)

    assert any("decomposition of" in f and "incomplete" in f for f in failures)


def test_gate_a_rejects_a_one_to_one_relabel_dressed_as_decomposition(
    baseline: dict,
) -> None:
    """A 'decomposition' into a single criterion is a rewording, not a split."""
    tampered = json.loads(json.dumps(baseline))
    tampered["decompositions"]["some-skill/some-case"] = [
        {"replaced": "old wording", "with": ["new wording"]}
    ]

    with pytest.raises(gates.GateFailure, match="at least two"):
        gates.check_rubric_not_weakened(tampered)


# ---------------------------------------------------------------------------
# Gate B must reject a stale benchmark claiming currency
# ---------------------------------------------------------------------------


def test_gate_b_rejects_a_superseded_benchmark_declared_current(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = tmp_path / "fake-benchmark"
    directory.mkdir()
    (directory / "metrics.json").write_text(
        json.dumps({"suite_sha256": "0" * 64, "skills": 1}), encoding="utf-8"
    )
    (directory / "README.md").write_text(
        "# Fake\n\n- Suite state: `current`\n", encoding="utf-8"
    )
    monkeypatch.setattr(gates, "BENCHMARKS_DIR", tmp_path)

    failures = gates.check_benchmark_currency()

    assert len(failures) == 1
    assert "declares 'Suite state: current'" in failures[0]
    assert "computed state is 'superseded'" in failures[0]


def test_gate_b_rejects_an_undeclared_benchmark(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = tmp_path / "fake-benchmark"
    directory.mkdir()
    (directory / "metrics.json").write_text(
        json.dumps({"suite_sha256": "0" * 64, "skills": 1}), encoding="utf-8"
    )
    (directory / "README.md").write_text(
        "# Fake\n\nNo declaration.\n", encoding="utf-8"
    )
    monkeypatch.setattr(gates, "BENCHMARKS_DIR", tmp_path)

    failures = gates.check_benchmark_currency()

    assert len(failures) == 1
    assert "does not declare a suite state" in failures[0]


def test_gate_b_accepts_a_correctly_declared_superseded_benchmark(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = tmp_path / "fake-benchmark"
    directory.mkdir()
    (directory / "metrics.json").write_text(
        json.dumps({"suite_sha256": "0" * 64, "skills": 1}), encoding="utf-8"
    )
    (directory / "README.md").write_text(
        "# Fake\n\n- Suite state: `superseded`\n", encoding="utf-8"
    )
    monkeypatch.setattr(gates, "BENCHMARKS_DIR", tmp_path)

    assert gates.check_benchmark_currency() == []


def test_gate_b_accepts_a_genuinely_current_benchmark(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _cases, current_suite, _skills = gates.load_suite()
    directory = tmp_path / "fake-benchmark"
    directory.mkdir()
    (directory / "metrics.json").write_text(
        json.dumps({"suite_sha256": current_suite, "skills": 18}), encoding="utf-8"
    )
    (directory / "README.md").write_text(
        "# Fake\n\n- Suite state: `current`\n", encoding="utf-8"
    )
    monkeypatch.setattr(gates, "BENCHMARKS_DIR", tmp_path)

    assert gates.check_benchmark_currency() == []


# ---------------------------------------------------------------------------
# The shipped benchmark must be honest about being superseded
# ---------------------------------------------------------------------------


def test_published_benchmark_declares_itself_superseded() -> None:
    readme = (
        ROOT
        / "benchmarks"
        / "claude-code-2.1.214--claude-sonnet-5--d45ad2c82635"
        / "README.md"
    ).read_text(encoding="utf-8")

    assert "Suite state: `superseded`" in readme
    assert "must not be cited as if they" in readme


def test_benchmark_card_discloses_supersession_and_names_the_revised_skills() -> None:
    card = (ROOT / "BENCHMARK.md").read_text(encoding="utf-8")

    assert "| Suite state | `superseded`" in card
    assert "**This suite is superseded.**" in card
    for skill in (
        "geoai-orchestrator",
        "point-cloud-lidar",
        "geo-deep-learning",
        "movement-trajectory",
        "postgis-spatial-sql",
        "google-earth-engine",
    ):
        assert skill in card
