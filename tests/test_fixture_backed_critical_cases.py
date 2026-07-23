from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "skills"
CRITICAL_CASES = {
    "cartography-geoviz": ("choropleth-request", "artifact-producing"),
    "mcda-suitability-analysis": ("inconsistent-ahp", "artifact-producing"),
    "network-accessibility-analysis": ("euclidean-catch", "fixture-backed"),
    "spatial-statistics": ("ols-on-spatial", "fixture-backed"),
    "swe-devops-standards": ("review-mode", "artifact-producing"),
    "terrain-hydrology": ("slope-4326-catch", "artifact-producing"),
}


def load_case(skill: str, case_id: str) -> dict[str, object]:
    eval_path = SKILLS / skill / "evals" / "evals.json"
    suite = json.loads(eval_path.read_text(encoding="utf-8"))
    return next(case for case in suite["evals"] if case["id"] == case_id)


def test_six_uncovered_skills_have_self_contained_critical_behavior() -> None:
    for skill, (case_id, behavior_class) in CRITICAL_CASES.items():
        case = load_case(skill, case_id)
        fixture_root = SKILLS / skill / "evals"

        assert case["critical"] is True
        assert case["behavior_class"] == behavior_class
        assert case["interaction_mode"] == "deliver"
        assert case["fixtures"]
        assert case["forbidden_behavior"]

        for fixture in case["fixtures"]:
            source = fixture_root / fixture["source"]
            assert source.is_file()
            assert fixture["workspace_path"] in case["prompt"]

        if behavior_class == "artifact-producing":
            assert case["tool_profile"] == "workspace-write"
            assert case["expected_artifacts"]
            for artifact in case["expected_artifacts"]:
                assert artifact["path"] in case["prompt"]
        else:
            assert case["tool_profile"] == "read-only"


def test_choropleth_fixture_requires_rate_and_nodata_handling() -> None:
    fixture = (
        SKILLS
        / "cartography-geoviz"
        / "evals"
        / "fixtures"
        / "choropleth-request"
        / "covid.csv"
    )
    with fixture.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    rates = {
        row["county_id"]: float(row["cases"]) / float(row["population"]) * 100_000
        for row in rows
        if row["population"]
    }
    assert rates == {"A": 1000.0, "B": 500.0, "C": 1500.0}
    assert [row["county_id"] for row in rows if not row["population"]] == ["D"]


def test_ahp_fixture_is_reciprocal_but_inconsistent() -> None:
    fixture = (
        SKILLS
        / "mcda-suitability-analysis"
        / "evals"
        / "fixtures"
        / "inconsistent-ahp"
        / "pairwise-matrix.csv"
    )
    with fixture.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle))
        matrix = np.array([[float(value) for value in row[1:]] for row in rows[1:]])

    np.testing.assert_allclose(matrix * matrix.T, np.ones_like(matrix), atol=1e-8)
    lambda_max = float(np.max(np.linalg.eigvals(matrix).real))
    consistency_ratio = ((lambda_max - 3) / 2) / 0.58
    assert consistency_ratio >= 0.10


def test_network_and_spatial_fixtures_force_the_intended_decisions() -> None:
    network = json.loads(
        (
            SKILLS
            / "network-accessibility-analysis"
            / "evals"
            / "fixtures"
            / "euclidean-catch"
            / "coverage-request.json"
        ).read_text(encoding="utf-8")
    )
    diagnostics = json.loads(
        (
            SKILLS
            / "spatial-statistics"
            / "evals"
            / "fixtures"
            / "ols-on-spatial"
            / "diagnostics.json"
        ).read_text(encoding="utf-8")
    )

    assert network["proposed_method"].startswith("five-kilometre Euclidean")
    assert network["response_threshold_minutes"] == 8
    assert diagnostics["ols"]["robust_lm_lag_p"] < 0.05
    assert diagnostics["ols"]["robust_lm_error_p"] > 0.05
    assert diagnostics["sar_candidate"]["residual_morans_p_permutation"] > 0.05
    assert diagnostics["sem_candidate"]["residual_morans_p_permutation"] < 0.05


def test_code_review_and_slope_fixtures_preserve_critical_traps() -> None:
    vulnerable_code = (
        SKILLS
        / "swe-devops-standards"
        / "evals"
        / "fixtures"
        / "review-mode"
        / "ingest_source.txt"
    ).read_text(encoding="utf-8")
    contract = json.loads(
        (
            SKILLS
            / "swe-devops-standards"
            / "evals"
            / "fixtures"
            / "review-mode"
            / "contract.json"
        ).read_text(encoding="utf-8")
    )
    dem = json.loads(
        (
            SKILLS
            / "terrain-hydrology"
            / "evals"
            / "fixtures"
            / "slope-4326-catch"
            / "dem-metadata.json"
        ).read_text(encoding="utf-8")
    )

    assert 'f"INSERT INTO {table_name}' in vulnerable_code
    assert "except:" in vulnerable_code
    assert contract["target_geometry_type"] == "MULTIPOLYGON"
    assert contract["target_srid"] == 3857
    assert dem["horizontal_crs"] == "EPSG:4326"
    assert dem["horizontal_units"] == "degrees"
    assert dem["vertical_units"] == "metres"
    assert dem["location_note"].endswith("UTM zone 33N.")
