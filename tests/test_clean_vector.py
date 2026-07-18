from __future__ import annotations

import importlib.util
from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import Point


SCRIPT = (
    Path(__file__).parents[1]
    / "skills"
    / "geo-data-engineering"
    / "scripts"
    / "clean_vector.py"
)
SPEC = importlib.util.spec_from_file_location("clean_vector_script", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
clean_vector = MODULE.clean_vector


def test_requires_defined_input_crs() -> None:
    frame = gpd.GeoDataFrame({"name": ["a"]}, geometry=[Point(0, 0)])

    with pytest.raises(ValueError, match="CRS undefined"):
        clean_vector(frame, 32631)


def test_requires_projected_target_crs() -> None:
    frame = gpd.GeoDataFrame(
        {"name": ["a"]}, geometry=[Point(0, 0)], crs="EPSG:4326"
    )

    with pytest.raises(ValueError, match="not projected"):
        clean_vector(frame, 4326)


def test_preserves_distinct_geometries_with_identical_attributes() -> None:
    frame = gpd.GeoDataFrame(
        {"name": ["same", "same"]},
        geometry=[Point(3.0, 40.0), Point(3.1, 40.1)],
        crs="EPSG:4326",
    )

    result = clean_vector(frame, 32631)

    assert len(result) == 2
    assert result.crs.to_epsg() == 32631


def test_removes_only_exact_duplicate_features() -> None:
    frame = gpd.GeoDataFrame(
        {"name": ["same", "same", "same"]},
        geometry=[Point(3.0, 40.0), Point(3.0, 40.0), Point(3.1, 40.1)],
        crs="EPSG:4326",
    )

    result = clean_vector(frame, 32631)

    assert len(result) == 2


def test_removes_null_and_empty_geometry() -> None:
    frame = gpd.GeoDataFrame(
        {"name": ["valid", "missing", "empty"]},
        geometry=[Point(3.0, 40.0), None, Point()],
        crs="EPSG:4326",
    )

    result = clean_vector(frame, 32631)

    assert result["name"].tolist() == ["valid"]

