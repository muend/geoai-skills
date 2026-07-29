"""Validate all output artifacts for external case GAB-36."""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path
from typing import Any

DAMAGED_CELLS = {
    (0, 0),
    (0, 1),
    (0, 2),
    (0, 3),
    (0, 4),
    (1, 0),
    (1, 1),
}
INVALID_CELLS = {(3, 2), (3, 3)}
EXPECTED_SUMMARY = {
    "-0.150": (9, 0.09),
    "-0.200": (7, 0.07),
    "-0.250": (3, 0.03),
}


def load_json(path: Path, errors: list[str]) -> Any:
    """Load JSON while turning failures into validation errors."""
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"{path.name}: cannot read valid JSON: {exc}")
        return None


def expected_savi(red_dn: int, nir_dn: int) -> float:
    """Compute the registered SAVI value from scaled reflectance."""
    red = red_dn * 0.0001
    nir = nir_dn * 0.0001
    return round(((nir - red) / (nir + red + 0.5)) * 1.5, 9)


def validate_change_grid(
    scenes: dict[str, Any] | None,
    output_dir: Path,
    errors: list[str],
) -> None:
    """Validate masks, scale factors, SAVI values, delta direction, and damage."""
    change = load_json(output_dir / "savi-change.json", errors)
    if not isinstance(change, dict) or not isinstance(scenes, dict):
        return
    if (
        change.get("schema_version") != 1
        or change.get("crs") != "EPSG:32636"
        or change.get("rows") != 4
        or change.get("columns") != 5
    ):
        errors.append("savi-change.json: grid identity or CRS is incorrect")
        return

    fields = (
        "pre_savi",
        "post_savi",
        "delta_savi",
        "valid_overlap",
        "damage_mask",
    )
    for field in fields:
        grid = change.get(field)
        if not isinstance(grid, list) or len(grid) != 4:
            errors.append(f"savi-change.json: {field} must have four rows")
            return
        if any(not isinstance(row, list) or len(row) != 5 for row in grid):
            errors.append(f"savi-change.json: {field} must have five columns")
            return

    for row in range(4):
        for column in range(5):
            cell = (row, column)
            valid = cell not in INVALID_CELLS
            if change["valid_overlap"][row][column] is not valid:
                errors.append(f"{cell}: valid-overlap mask is incorrect")
            values = [
                change[field][row][column]
                for field in ("pre_savi", "post_savi", "delta_savi", "damage_mask")
            ]
            if not valid:
                if any(value is not None for value in values):
                    errors.append(f"{cell}: invalid cell outputs must all be null")
                continue

            pre_expected = expected_savi(
                int(scenes["pre"]["red_dn"][row][column]),
                int(scenes["pre"]["nir_dn"][row][column]),
            )
            post_expected = expected_savi(
                int(scenes["post"]["red_dn"][row][column]),
                int(scenes["post"]["nir_dn"][row][column]),
            )
            delta_expected = round(post_expected - pre_expected, 9)
            for field, expected in (
                ("pre_savi", pre_expected),
                ("post_savi", post_expected),
                ("delta_savi", delta_expected),
            ):
                actual = change[field][row][column]
                if not isinstance(actual, (int, float)) or not math.isclose(
                    float(actual),
                    expected,
                    rel_tol=0.0,
                    abs_tol=1e-9,
                ):
                    errors.append(f"{cell}: {field} does not match scaled SAVI")
            expected_damage = cell in DAMAGED_CELLS
            if change["damage_mask"][row][column] is not expected_damage:
                errors.append(f"{cell}: damage mask is incorrect")


def pixel_polygon(row: int, column: int) -> list[list[float]]:
    """Return the registered polygon ring for one ten-metre cell."""
    left = 500000.0 + column * 10.0
    top = 4420040.0 - row * 10.0
    return [
        [left, top],
        [left + 10.0, top],
        [left + 10.0, top - 10.0],
        [left, top - 10.0],
        [left, top],
    ]


def validate_damage_features(output_dir: Path, errors: list[str]) -> None:
    """Validate exact damaged-cell polygons and projected pixel areas."""
    damage = load_json(output_dir / "damage-pixels.geojson", errors)
    if not isinstance(damage, dict):
        return
    crs_name = damage.get("crs", {}).get("properties", {}).get("name")
    if damage.get("type") != "FeatureCollection" or crs_name != "EPSG:32636":
        errors.append("damage-pixels.geojson: FeatureCollection in EPSG:32636 required")
        return
    features = damage.get("features")
    if not isinstance(features, list):
        errors.append("damage-pixels.geojson: features must be an array")
        return
    by_cell = {
        (
            feature.get("properties", {}).get("row"),
            feature.get("properties", {}).get("column"),
        ): feature
        for feature in features
        if isinstance(feature, dict)
    }
    if len(features) != 7 or set(by_cell) != DAMAGED_CELLS:
        errors.append("damage-pixels.geojson: must contain exactly seven damaged cells")
        return
    for cell, feature in by_cell.items():
        properties = feature.get("properties", {})
        geometry = feature.get("geometry", {})
        if properties.get("pixel_area_m2") != 100.0:
            errors.append(f"{cell}: pixel area must equal 100 square metres")
        if geometry.get("type") != "Polygon":
            errors.append(f"{cell}: damage geometry must be Polygon")
            continue
        if geometry.get("coordinates") != [pixel_polygon(*cell)]:
            errors.append(f"{cell}: projected pixel polygon is incorrect")


def validate_summary(output_dir: Path, errors: list[str]) -> None:
    """Validate threshold sensitivity, area conversion, and valid overlap."""
    path = output_dir / "change-summary.csv"
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
    except OSError as exc:
        errors.append(f"{path.name}: cannot read CSV: {exc}")
        return
    fields = [
        "threshold",
        "damaged_pixels",
        "damaged_area_hectares",
        "valid_pixels",
        "valid_overlap_percent",
    ]
    if not rows or list(rows[0]) != fields:
        errors.append("change-summary.csv: unexpected or missing columns")
        return
    by_threshold = {row["threshold"]: row for row in rows}
    if len(rows) != 3 or set(by_threshold) != set(EXPECTED_SUMMARY):
        errors.append("change-summary.csv: all three registered thresholds are required")
        return
    for threshold, (pixels, area) in EXPECTED_SUMMARY.items():
        row = by_threshold[threshold]
        if row["damaged_pixels"] != str(pixels):
            errors.append(f"{threshold}: damaged pixel count must equal {pixels}")
        try:
            actual_area = float(row["damaged_area_hectares"])
        except ValueError:
            errors.append(f"{threshold}: damaged area is not numeric")
        else:
            if not math.isclose(actual_area, area, rel_tol=0.0, abs_tol=1e-12):
                errors.append(f"{threshold}: damaged area must equal {area} hectares")
        if row["valid_pixels"] != "18" or row["valid_overlap_percent"] != "90.0":
            errors.append(f"{threshold}: valid overlap must equal 18 pixels and 90.0%")


def validate_provenance(output_dir: Path, errors: list[str]) -> None:
    """Validate comparability, processing, scale, registration, and mask evidence."""
    provenance = load_json(output_dir / "provenance.json", errors)
    if not isinstance(provenance, dict):
        return
    expected = {
        "schema_version": 1,
        "sensor": "SYNTHETIC-S2-L2A-LIKE",
        "product_level": "surface_reflectance",
        "pre_acquired": "2025-06-10",
        "post_acquired": "2025-06-20",
        "phenology": "matched",
        "co_registration_rmse_pixels": 0.1,
        "crs": "EPSG:32636",
        "pixel_width_m": 10.0,
        "pixel_height_m": 10.0,
        "reflectance_scale_factor": 0.0001,
        "savi_l": 0.5,
        "damage_threshold": -0.2,
        "valid_pixels": 18,
        "total_pixels": 20,
        "valid_overlap_percent": 90.0,
    }
    for field, expected_value in expected.items():
        if provenance.get(field) != expected_value:
            errors.append(f"provenance.json: {field} must equal {expected_value!r}")


def validate(input_path: Path, output_dir: Path) -> list[str]:
    """Return every artifact-contract violation."""
    errors: list[str] = []
    scenes = load_json(input_path, errors)
    validate_change_grid(scenes if isinstance(scenes, dict) else None, output_dir, errors)
    validate_damage_features(output_dir, errors)
    validate_summary(output_dir, errors)
    validate_provenance(output_dir, errors)
    return errors


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    """Validate artifacts and return a process-friendly status."""
    args = parse_args()
    errors = validate(args.input, args.output_dir)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("gab-36-vegetation-change artifacts: pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
