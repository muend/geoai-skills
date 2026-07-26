"""Tests for multiplicity correction and equity disaggregation.

The BH/BY implementations are checked against hand-computable values rather
than another library, so the tests stay honest if the implementation is ever
swapped for scipy.
"""

from __future__ import annotations

import pytest

from tools.verification import (
    adjust,
    benjamini_hochberg,
    benjamini_yekutieli,
    check_correction_applied,
    check_disaggregation,
    disparity_ratio,
    summarise_by_group,
)


# --- Benjamini-Hochberg ---------------------------------------------------


def test_bh_matches_a_hand_computed_example() -> None:
    """p = [0.01, 0.02, 0.03, 0.04, 0.05], n = 5.

    Adjusted = p * n / rank, then enforced monotone from the largest down:
      rank 5: 0.05 * 5/5 = 0.05
      rank 4: 0.04 * 5/4 = 0.05
      rank 3: 0.03 * 5/3 = 0.05
      rank 2: 0.02 * 5/2 = 0.05
      rank 1: 0.01 * 5/1 = 0.05
    """
    adjusted = benjamini_hochberg([0.01, 0.02, 0.03, 0.04, 0.05])

    assert all(abs(value - 0.05) < 1e-12 for value in adjusted)


def test_bh_preserves_input_order() -> None:
    adjusted = benjamini_hochberg([0.9, 0.001, 0.5])

    assert adjusted[1] < adjusted[2] < adjusted[0]


def test_bh_is_monotone() -> None:
    p_values = [0.001, 0.008, 0.02, 0.2, 0.7, 0.9]
    adjusted = benjamini_hochberg(p_values)
    pairs = sorted(zip(p_values, adjusted, strict=True))

    assert all(pairs[i][1] <= pairs[i + 1][1] + 1e-12 for i in range(len(pairs) - 1))


def test_bh_never_exceeds_one() -> None:
    assert all(value <= 1.0 for value in benjamini_hochberg([0.9, 0.95, 0.99]))


def test_by_is_strictly_more_conservative_than_bh() -> None:
    p_values = [0.001, 0.01, 0.02, 0.04]
    bh = benjamini_hochberg(p_values)
    by = benjamini_yekutieli(p_values)

    assert all(b >= h - 1e-12 for b, h in zip(by, bh, strict=True))
    assert any(b > h for b, h in zip(by, bh, strict=True))


# --- method selection -----------------------------------------------------


def test_auto_selects_by_when_tests_are_dependent() -> None:
    """Local statistics on contiguous units are dependent by construction."""
    outcome = adjust([0.01, 0.02, 0.03], method="auto", dependent=True)

    assert outcome["method"] == "benjamini-yekutieli"
    assert "dependent" in outcome["rationale"]


def test_auto_selects_bh_when_independence_is_declared() -> None:
    outcome = adjust([0.01, 0.02, 0.03], method="auto", dependent=False)

    assert outcome["method"] == "benjamini-hochberg"


def test_the_rationale_is_always_recorded() -> None:
    """A silently chosen method is a method nobody can audit."""
    assert adjust([0.01, 0.5], method="bh")["rationale"]


def test_unknown_method_raises() -> None:
    with pytest.raises(ValueError, match="unknown method"):
        adjust([0.01], method="bonferroni-ish")


@pytest.mark.parametrize("bad", [[-0.1], [1.5], [float("nan")], []])
def test_invalid_p_values_raise(bad) -> None:
    with pytest.raises(ValueError):
        adjust(bad)


def test_invalid_alpha_raises() -> None:
    with pytest.raises(ValueError, match="alpha"):
        adjust([0.01], alpha=1.5)


# --- the reported-count check --------------------------------------------


def test_reporting_the_uncorrected_count_fails() -> None:
    """800 tracts at alpha 0.05: about 40 light up by chance."""
    p_values = [0.001] * 10 + [0.04] * 30 + [0.5] * 760
    naive = sum(1 for p in p_values if p <= 0.05)

    result = check_correction_applied(naive, p_values, alpha=0.05)

    assert result.failed
    assert "uncorrected count" in result.reason


def test_reporting_the_corrected_count_passes() -> None:
    p_values = [0.001] * 10 + [0.04] * 30 + [0.5] * 760
    outcome = adjust(p_values, alpha=0.05)

    result = check_correction_applied(outcome["n_rejected"], p_values, alpha=0.05)

    assert result.ok


def test_over_reporting_fails_even_if_it_is_not_the_naive_count() -> None:
    p_values = [0.001, 0.002, 0.6, 0.7, 0.8]
    outcome = adjust(p_values)

    result = check_correction_applied(outcome["n_rejected"] + 1, p_values)

    assert result.failed
    assert "survive" in result.reason


def test_the_avoided_false_positives_are_quantified() -> None:
    p_values = [0.04] * 100
    outcome = adjust(p_values, alpha=0.05)

    assert outcome["n_rejected_uncorrected"] == 100
    assert outcome["n_false_positives_avoided"] > 0


def test_malformed_p_values_abstain_rather_than_raise_in_the_check() -> None:
    """The check is a gate in a pipeline; it reports, it does not explode."""
    assert check_correction_applied(3, [0.1, 2.0]).abstained


# --- equity ---------------------------------------------------------------


def test_a_large_disparity_fails_despite_a_reasonable_mean() -> None:
    """Mean 18 minutes, and one district at 40."""
    values = {
        "north": [10, 11, 12, 10],
        "centre": [8, 9, 9, 10],
        "south": [38, 41, 44, 39],
    }

    result = check_disaggregation(values, threshold=30)

    assert result.failed
    assert "disparity ratio" in result.reason
    assert any("south" in item for item in result.evidence)


def test_parity_passes() -> None:
    values = {"a": [10, 11, 12], "b": [11, 10, 12], "c": [10, 12, 11]}

    assert check_disaggregation(values).ok


def test_an_unreported_group_fails_before_any_statistic() -> None:
    values = {"a": [10, 11], "b": [40, 42]}

    result = check_disaggregation(values, reported_groups=["a"])

    assert result.failed
    assert "absent from the report" in result.reason


def test_one_group_abstains() -> None:
    assert check_disaggregation({"only": [1, 2, 3]}).abstained


def test_no_groups_abstains() -> None:
    assert check_disaggregation({}).abstained


def test_share_beyond_threshold_is_computed() -> None:
    summaries = summarise_by_group({"a": [10, 20, 30, 40]}, threshold=25)

    assert summaries[0].share_beyond_threshold == pytest.approx(0.5)


def test_percentiles_are_interpolated() -> None:
    summaries = summarise_by_group({"a": [0, 10, 20, 30, 40, 50, 60, 70, 80, 90]})

    assert summaries[0].p90 == pytest.approx(81.0)


def test_disparity_ratio_needs_two_groups() -> None:
    assert disparity_ratio(summarise_by_group({"a": [1, 2]})) is None
