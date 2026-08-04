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
import re
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


def test_benchmark_card_state_matches_the_suite_it_claims() -> None:
    """A card may say `current` only if it names the live suite hash.

    This replaces an earlier test that hard-coded `superseded`. That assertion
    was correct while the published card described a retired 120-case suite, but
    it could only ever check a string. Pinning the declared hash to the
    recomputed one is strictly stronger: a stale card cannot pass by editing a
    label, and a current card cannot pass by claiming a suite it did not run.
    """
    card = (ROOT / "BENCHMARK.md").read_text(encoding="utf-8")
    _cases, current_suite_sha256, _skills = gates.suite()

    assert "| Suite state | `current`" in card or "| Suite state | `superseded`" in card

    if "| Suite state | `current`" in card:
        assert current_suite_sha256 in card, (
            "The card declares itself current but does not contain the "
            f"recomputed suite hash {current_suite_sha256}."
        )
    else:
        assert "**This suite is superseded.**" in card
        assert current_suite_sha256 not in card


def test_benchmark_card_keeps_the_archived_result_separate() -> None:
    """The retired 120-case package stays reachable and explicitly un-poolable."""
    card = (ROOT / "BENCHMARK.md").read_text(encoding="utf-8")

    assert "d45ad2c82635" in card
    assert "Do not pool the two." in card


def test_benchmark_card_does_not_claim_behavior() -> None:
    """Routing evidence must never be presented as answer-quality evidence."""
    card = (ROOT / "BENCHMARK.md").read_text(encoding="utf-8")

    # Normalize wrapping: these sentences are line-wrapped in the card.
    flat = " ".join(card.split())

    assert "**Behavior quality is not evaluated in this release.**" in flat
    assert "These are routing results, not claims about answer quality." in flat


def test_readme_badges_match_the_published_benchmark() -> None:
    """README badges must not outlive the numbers they advertise.

    A badge is the most-read and least-contextual claim in the repository. It
    survives copy-paste into places the card never reaches, so a stale badge is
    a durable false claim. This pins each headline badge to the value published
    in `BENCHMARK.md`: publish a new pair without updating the badges and CI
    fails here.
    """
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    card = " ".join((ROOT / "BENCHMARK.md").read_text(encoding="utf-8").split())

    precision = re.search(r"routing_precision-([\d.]+)%25", readme)
    recall = re.search(r"routing_recall-([\d.]+)%25", readme)

    assert precision and recall, "headline routing badges are missing"
    assert f"**{precision.group(1)}%**" in card, (
        f"precision badge says {precision.group(1)}% but the card does not"
    )
    assert f"**{recall.group(1)}%**" in card, (
        f"recall badge says {recall.group(1)}% but the card does not"
    )


def test_readme_badges_carry_their_scope() -> None:
    """Context-free badges need the runtime/model qualifier next to them."""
    readme = " ".join((ROOT / "README.md").read_text(encoding="utf-8").split())
    _cases, current_suite_sha256, _skills = gates.suite()

    assert "behavior_quality-not_evaluated" in readme
    assert "one runtime/model pair" in readme
    assert current_suite_sha256[:12] in readme
    assert "not universal or model-independent claims" in readme


def test_demo_asset_matches_the_published_benchmark() -> None:
    """The demo animation must not outlive the numbers it displays.

    The GIF sits at the top of the README and is the most-viewed artefact in the
    repository, but nothing links it to the benchmark it quotes. Its first
    version claimed that `change-detection` and `remote-sensing-analysis`
    activate together on multi-date prompts — a routing behaviour the 2026-08-04
    run disproved, in the same repository that published the disproof.

    `assets/demo/asset-manifest.json` records what the frames assert. This test
    pins those assertions to `BENCHMARK.md` so a future benchmark run cannot
    leave a stale claim animating above it.
    """
    manifest = json.loads(
        (ROOT / "assets" / "demo" / "asset-manifest.json").read_text(encoding="utf-8")
    )
    card = " ".join((ROOT / "BENCHMARK.md").read_text(encoding="utf-8").split())
    accuracy = manifest["accuracy"]

    assert f"**{accuracy['routing_precision']}**" in card
    assert f"**{accuracy['routing_recall_exact']}**" in card
    assert accuracy["disabled_control_activations"] == 0
    assert "Answer quality is not claimed" in accuracy["qualifier"]

    assert manifest["frame4_activation_claim"] is False, (
        "The demo must not assert which skills activate; that claim is what the "
        "routing benchmark contradicted."
    )

    displayed = float(accuracy["routing_recall_display"].rstrip("%"))
    exact = float(accuracy["routing_recall_exact"].rstrip("%"))
    assert abs(displayed - exact) < 0.05, (
        f"Displayed recall {displayed}% rounds away from the measured {exact}%."
    )
