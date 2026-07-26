"""Tests for provenance, comparability, privacy and parameter emission."""

from __future__ import annotations

from datetime import date, datetime, UTC

import pytest

from tools.verification import (
    ParameterLog,
    Scene,
    Source,
    build_manifest,
    check_disaggregation,  # noqa: F401  (import surface check)
    check_k_anonymity,
    check_parameters_emitted,
    check_shared_class_breaks,
    check_trip_ends_truncated,
    compare_scenes,
    diff_manifests,
    haversine_m,
    suppress_small_counts,
    truncate_trip_ends,
    verify_manifest,
)


def a_source(**overrides) -> Source:
    payload = {
        "name": "osm-buildings",
        "source": "Overpass API",
        "retrieved_at": date(2026, 7, 20),
        "query": 'way["building"](bbox);',
        "version": "overpass-0.7.62",
        "licence": "ODbL",
        "crs": "EPSG:4326",
    }
    payload.update(overrides)
    return Source(**payload)


# --- provenance -----------------------------------------------------------


def test_a_complete_manifest_verifies() -> None:
    manifest = build_manifest([a_source()], analysis="building density")

    assert verify_manifest(manifest).ok


def test_a_manifest_without_a_retrieval_date_fails() -> None:
    """'I downloaded it from OSM' is not reproducible; OSM changes hourly."""
    manifest = build_manifest([a_source(retrieved_at="")], analysis="x")

    result = verify_manifest(manifest)

    assert result.failed
    assert any("retrieved_at" in item for item in result.evidence)


def test_strict_mode_demands_the_recommended_fields() -> None:
    manifest = build_manifest([a_source(version=None)], analysis="x")

    assert verify_manifest(manifest).ok
    assert verify_manifest(manifest, strict=True).failed


def test_a_manifest_with_no_sources_is_refused_at_build_time() -> None:
    with pytest.raises(ValueError, match="records nothing"):
        build_manifest([], analysis="x")


def test_the_hash_ignores_the_production_timestamp() -> None:
    """Two runs on identical inputs must be recognisable as identical."""
    first = build_manifest(
        [a_source()], analysis="x", produced_at=datetime(2026, 1, 1, tzinfo=UTC)
    )
    second = build_manifest(
        [a_source()], analysis="x", produced_at=datetime(2026, 9, 9, tzinfo=UTC)
    )

    assert first["content_sha256"] == second["content_sha256"]


def test_the_hash_changes_when_a_parameter_changes() -> None:
    first = build_manifest([a_source()], analysis="x", parameters={"radius": 500})
    second = build_manifest([a_source()], analysis="x", parameters={"radius": 800})

    assert first["content_sha256"] != second["content_sha256"]


def test_diff_names_the_field_that_moved() -> None:
    first = build_manifest([a_source()], analysis="x", parameters={"radius": 500})
    second = build_manifest(
        [a_source(retrieved_at=date(2026, 7, 25))], analysis="x", parameters={"radius": 800}
    )

    differences = diff_manifests(first, second)

    assert any("retrieved_at" in d for d in differences)
    assert any("parameter radius" in d for d in differences)


def test_identical_manifests_diff_to_nothing() -> None:
    manifest = build_manifest([a_source()], analysis="x")

    assert diff_manifests(manifest, manifest) == []


def test_a_foreign_document_is_rejected() -> None:
    assert verify_manifest({"kind": "something-else"}).failed


# --- comparability --------------------------------------------------------


def test_differencing_across_processing_levels_fails() -> None:
    """L1C is top-of-atmosphere, L2A is surface: the difference is the correction."""
    result = compare_scenes(
        [
            Scene("2020", sensor="S2", processing_level="L1C", acquired_month=7),
            Scene("2024", sensor="S2", processing_level="L2A", acquired_month=7),
        ]
    )

    assert result.failed
    assert "atmospheric correction" in result.evidence[0]


def test_cross_season_differencing_fails() -> None:
    result = compare_scenes(
        [
            Scene("winter", sensor="S2", processing_level="L2A", acquired_month=1),
            Scene("summer", sensor="S2", processing_level="L2A", acquired_month=7),
        ]
    )

    assert result.failed
    assert "phenology" in result.evidence[0]


def test_cross_season_can_be_declared_deliberate() -> None:
    result = compare_scenes(
        [
            Scene("winter", sensor="S2", processing_level="L2A", acquired_month=1),
            Scene("summer", sensor="S2", processing_level="L2A", acquired_month=7),
        ],
        allow_cross_season=True,
    )

    assert result.ok


def test_resolution_mismatch_fails() -> None:
    result = compare_scenes(
        [
            Scene("a", sensor="S2", processing_level="L2A", acquired_month=7, resolution_m=10),
            Scene("b", sensor="S2", processing_level="L2A", acquired_month=7, resolution_m=30),
        ]
    )

    assert result.failed
    assert "resolution differs" in result.evidence[0]


def test_comparable_scenes_pass() -> None:
    shared = {
        "sensor": "S2",
        "processing_level": "L2A",
        "acquired_month": 7,
        "resolution_m": 10,
        "crs": "EPSG:32633",
    }
    scenes = [Scene("a", **shared), Scene("b", **shared)]

    assert compare_scenes(scenes).ok


def test_undeclared_axes_abstain_rather_than_pass() -> None:
    """Agreement on nothing is not agreement."""
    result = compare_scenes([Scene("a"), Scene("b")])

    assert result.abstained


def test_one_scene_abstains() -> None:
    assert compare_scenes([Scene("only")]).abstained


def test_per_date_class_breaks_fail() -> None:
    result = check_shared_class_breaks(
        {"2020": [0, 10, 20, 40], "2024": [0, 12, 26, 51]}
    )

    assert result.failed
    assert "cannot be read as change" in result.reason


def test_shared_class_breaks_pass() -> None:
    edges = [0, 10, 20, 40]

    assert check_shared_class_breaks({"2020": edges, "2024": list(edges)}).ok


def test_a_different_class_count_fails() -> None:
    result = check_shared_class_breaks({"2020": [0, 10, 20], "2024": [0, 10, 20, 30]})

    assert result.failed
    assert "classes vs" in result.evidence[0]


# --- privacy --------------------------------------------------------------


def test_small_cells_are_suppressed() -> None:
    suppression = suppress_small_counts({"a": 1, "b": 3, "c": 12}, k=5)

    assert suppression.cells["a"] is None
    assert suppression.cells["b"] is None
    assert suppression.cells["c"] == 12


def test_a_lone_suppression_triggers_a_secondary_one() -> None:
    """One blank in a published row is recoverable by subtraction."""
    counts = {("r1", "c1"): 2, ("r1", "c2"): 40, ("r1", "c3"): 50}

    suppression = suppress_small_counts(counts, k=5, row_of=lambda key: key[0])

    assert suppression.suppressed == [("r1", "c1")]
    assert suppression.secondary == [("r1", "c2")]
    assert suppression.cells[("r1", "c2")] is None


def test_two_primary_suppressions_need_no_secondary() -> None:
    counts = {("r1", "c1"): 2, ("r1", "c2"): 3, ("r1", "c3"): 50}

    suppression = suppress_small_counts(counts, k=5, row_of=lambda key: key[0])

    assert suppression.secondary == []


def test_k_below_two_is_refused() -> None:
    with pytest.raises(ValueError, match="suppresses nothing"):
        suppress_small_counts({"a": 1}, k=1)


def test_releasing_a_small_cell_fails_the_check() -> None:
    result = check_k_anonymity({"a": 1, "b": 30}, k=5)

    assert result.failed
    assert "re-identifiable" in result.reason


def test_the_check_respects_what_was_actually_released() -> None:
    result = check_k_anonymity({"a": 1, "b": 30}, k=5, released_keys=["b"])

    assert result.ok


def test_zero_counts_are_not_a_privacy_breach() -> None:
    """An empty cell reveals nobody."""
    assert check_k_anonymity({"a": 0, "b": 30}, k=5).ok


def test_trip_ends_are_truncated() -> None:
    points = [
        (28.9784, 41.0082),
        (28.9800, 41.0090),
        (29.0100, 41.0300),
        (29.0400, 41.0500),
        (29.0420, 41.0510),
    ]

    released = truncate_trip_ends(points, radius_m=300)

    assert released
    assert released[0] != points[0]
    assert released[-1] != points[-1]
    assert check_trip_ends_truncated(points, released, radius_m=300).ok


def test_an_untruncated_release_fails() -> None:
    points = [(28.9784, 41.0082), (29.0100, 41.0300), (29.0400, 41.0500)]

    result = check_trip_ends_truncated(points, points, radius_m=300)

    assert result.failed
    assert len(result.evidence) == 2


def test_a_short_trajectory_is_fully_suppressed() -> None:
    assert truncate_trip_ends([(0.0, 0.0), (0.0, 0.001)], radius_m=300) == []


def test_full_suppression_passes_the_check() -> None:
    points = [(0.0, 0.0), (0.0, 0.0005), (0.0, 0.001)]

    assert check_trip_ends_truncated(points, [], radius_m=300).ok


def test_haversine_is_sane() -> None:
    """One degree of latitude is about 111 km."""
    assert 110_000 < haversine_m((0.0, 0.0), (0.0, 1.0)) < 112_000


def test_a_negative_radius_is_refused() -> None:
    with pytest.raises(ValueError, match="positive"):
        truncate_trip_ends([(0.0, 0.0), (1.0, 1.0), (2.0, 2.0)], radius_m=-1)


# --- parameter emission ---------------------------------------------------


def test_a_complete_parameter_log_passes() -> None:
    log = (
        ParameterLog("choropleth")
        .record("classification_method", "quantile", because="skewed rate distribution")
        .record("class_edges", [0, 25, 50, 100, 250], unit="per 100k")
        .record("n_classes", 5)
        .record("colour_scheme", "YlOrRd")
    )

    assert log.missing() == []
    assert check_parameters_emitted("choropleth", log.as_metadata()).ok


def test_a_missing_parameter_fails_and_is_named() -> None:
    log = ParameterLog("viewshed").record("observer_height", 1.7, unit="m")

    result = check_parameters_emitted("viewshed", log.as_metadata())

    assert result.failed
    assert "target_height" in result.detail["missing"]


def test_absent_metadata_fails_rather_than_abstains() -> None:
    """A registered operation that emitted nothing definitely failed."""
    result = check_parameters_emitted("kriging", None)

    assert result.failed
    assert "no metadata" in result.reason


def test_an_unregistered_operation_abstains() -> None:
    assert check_parameters_emitted("some_new_thing", {"parameters": {}}).abstained


def test_rationale_can_be_demanded() -> None:
    log = (
        ParameterLog("buffer")
        .record("distance", 500, unit="m")
        .record("distance_unit", "m")
        .record("dissolve", False)
    )

    assert check_parameters_emitted("buffer", log.as_metadata()).ok
    assert check_parameters_emitted(
        "buffer", log.as_metadata(), require_rationale=True
    ).failed


def test_unjustified_parameters_are_listable() -> None:
    log = ParameterLog("slope").record("algorithm", "horn").record("z_factor", 1.0)

    assert log.unjustified() == ["algorithm", "z_factor"]


def test_nested_metadata_keys_are_found() -> None:
    metadata = {
        "operation": "buffer",
        "nested": {"deeper": {"distance": 500, "distance_unit": "m", "dissolve": True}},
    }

    assert check_parameters_emitted("buffer", metadata).ok
