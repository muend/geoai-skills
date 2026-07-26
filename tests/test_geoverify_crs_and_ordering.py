"""Tests for the unit and ordering checks.

Both modules exist because the failure they catch is silent: a wrong-unit
buffer and a reversed pipeline both produce output that renders.
"""

from __future__ import annotations

import pytest

from tools.verification import (
    axis_unit,
    check_pipeline_order,
    check_planar_operation,
    check_vertical_horizontal_units,
    explain,
    parse_epsg,
)


# --- EPSG parsing ---------------------------------------------------------


@pytest.mark.parametrize(
    "value,expected",
    [
        ("EPSG:4326", 4326),
        ("epsg 32633", 32633),
        ("4326", 4326),
        (3857, 3857),
        (None, None),
        ("no code here", None),
    ],
)
def test_epsg_is_parsed_from_the_forms_people_actually_write(value, expected):
    assert parse_epsg(value) == expected


def test_axis_units_are_classified() -> None:
    assert axis_unit("EPSG:4326") == "degree"
    assert axis_unit("EPSG:32633") == "metre"
    assert axis_unit("EPSG:2263") == "foot"
    assert axis_unit("EPSG:99999999") is None


# --- planar operations ----------------------------------------------------


def test_buffering_in_4326_fails() -> None:
    """The canonical silent error: 5000 'metres' that are 5000 degrees."""
    result = check_planar_operation("buffer", "EPSG:4326", value=5000)

    assert result.failed
    assert "degrees" in result.reason
    assert any("5000 degrees" in item for item in result.evidence)


def test_slope_on_a_geographic_dem_fails() -> None:
    assert check_planar_operation("slope", 4326).failed


def test_buffering_in_utm_passes() -> None:
    result = check_planar_operation("buffer", "EPSG:32633", value=5000)

    assert result.ok
    assert result.detail["unit"] == "metre"


def test_a_foot_based_crs_fails_rather_than_passing_quietly() -> None:
    """Feet are metric enough to look right and wrong enough to matter."""
    result = check_planar_operation("area", "EPSG:2263")

    assert result.failed
    assert "feet" in result.reason


def test_an_unknown_crs_abstains_rather_than_guessing() -> None:
    assert check_planar_operation("buffer", "EPSG:99999999").abstained


def test_a_missing_crs_abstains() -> None:
    assert check_planar_operation("buffer", None).abstained


def test_a_non_metric_operation_abstains() -> None:
    assert check_planar_operation("reproject", "EPSG:4326").abstained


def test_abstain_is_not_ok() -> None:
    """The property the whole result vocabulary rests on."""
    result = check_planar_operation("buffer", None)

    assert result.abstained
    assert not result.ok
    assert not result.failed


# --- vertical vs horizontal ----------------------------------------------


def test_metres_over_degrees_fails() -> None:
    result = check_vertical_horizontal_units("EPSG:4326", "metres")

    assert result.failed
    assert "slope and aspect" in result.reason


def test_metres_over_feet_fails() -> None:
    assert check_vertical_horizontal_units("EPSG:2263", "m").failed


def test_matching_units_pass() -> None:
    assert check_vertical_horizontal_units("EPSG:32633", "meters").ok


def test_unit_aliases_are_normalised() -> None:
    for spelling in ("m", "metre", "metres", "meter", "Meters"):
        assert check_vertical_horizontal_units("EPSG:32633", spelling).ok


def test_undeclared_vertical_unit_abstains() -> None:
    assert check_vertical_horizontal_units("EPSG:32633", None).abstained


# --- pipeline ordering ----------------------------------------------------


def test_mapping_before_correction_fails() -> None:
    result = check_pipeline_order(["local_statistic", "cluster_map", "multiplicity_correction"])

    assert result.failed
    assert "cluster_map" in result.evidence[0]


def test_correction_before_mapping_passes() -> None:
    assert check_pipeline_order(
        ["local_statistic", "multiplicity_correction", "cluster_map"]
    ).ok


def test_preprocessing_fitted_before_the_split_fails() -> None:
    """The leakage that makes every reported score optimistic."""
    result = check_pipeline_order(["fit_preprocessing", "spatial_split", "train"])

    assert result.failed
    assert "leaks" in result.evidence[0]


def test_compositing_before_masking_fails() -> None:
    assert check_pipeline_order(["composite", "cloud_mask"]).failed


def test_measuring_before_reprojecting_fails() -> None:
    assert check_pipeline_order(["measure", "reproject"]).failed


def test_multiple_violations_are_all_reported() -> None:
    result = check_pipeline_order(
        ["composite", "cloud_mask", "measure", "reproject"]
    )

    assert result.failed
    assert result.detail["n_violations"] == 2


def test_steps_with_no_registered_rule_abstain() -> None:
    """Absence of a rule is not evidence of correctness."""
    assert check_pipeline_order(["load", "plot", "save"]).abstained


def test_a_rule_needs_both_steps_present_to_apply() -> None:
    """Missing a step is a coverage question, not an ordering violation."""
    result = check_pipeline_order(["cluster_map", "render"])

    assert result.abstained


def test_case_and_whitespace_are_normalised() -> None:
    assert check_pipeline_order([" Cloud_Mask ", "COMPOSITE"]).ok


def test_explain_lists_both_directions() -> None:
    lines = explain("spatial_split")

    assert any("BEFORE fit_preprocessing" in line for line in lines)
    assert any("BEFORE hyperparameter_search" in line for line in lines)
