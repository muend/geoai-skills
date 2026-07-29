"""Validate artifacts for external GeoAnalystBench-derived case GAB-01."""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path
from typing import Any

import reference as oracle


def read_json(path: Path, errors: list[str]) -> Any:
    """Read one JSON artifact and append readable failures."""
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        errors.append(f"missing artifact: {path.name}")
    except json.JSONDecodeError as exc:
        errors.append(f"{path.name} is not valid JSON: {exc}")
    return None


def validate_surface(
    actual: Any,
    expected: dict[str, Any],
    filename: str,
    errors: list[str],
) -> None:
    """Validate one projected regular-grid artifact exactly."""
    if not isinstance(actual, dict):
        errors.append(f"{filename} must contain a JSON object")
        return
    if actual.get("crs") != "EPSG:32636":
        errors.append(f"{filename}: interpolation CRS must remain projected EPSG:32636")
    if actual.get("cell_size_m") != 50.0:
        errors.append(f"{filename}: cell_size_m must equal 50.0")
    values = actual.get("values")
    if (
        not isinstance(values, list)
        or len(values) != 9
        or any(not isinstance(row, list) or len(row) != 12 for row in values)
    ):
        errors.append(f"{filename}: values must be a complete 9-by-12 grid")
    elif any(
        not isinstance(value, (int, float)) or not math.isfinite(float(value))
        for row in values
        for value in row
    ):
        errors.append(f"{filename}: every grid value must be finite")
    if actual != expected:
        errors.append(f"{filename}: grid or metadata differs from the reference")


def read_summary(path: Path, errors: list[str]) -> list[dict[str, str]]:
    """Read the census summary CSV."""
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))
    except FileNotFoundError:
        errors.append("missing artifact: census-summary.csv")
        return []


def expected_csv_rows(expected: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Serialize expected summary rows using the reference CSV contract."""
    rows = []
    for row in expected:
        rows.append(
            {
                "census_id": str(row["census_id"]),
                "total_population": str(row["total_population"]),
                "elderly_population": str(row["elderly_population"]),
                "elderly_rate": f"{row['elderly_rate']:.6f}",
                "mean_temperature_c": f"{row['mean_temperature_c']:.6f}",
                "mean_uncertainty_c": f"{row['mean_uncertainty_c']:.6f}",
                "selection_status": str(row["selection_status"]),
            }
        )
    return rows


def validate_summary(
    actual: list[dict[str, str]],
    expected: list[dict[str, Any]],
    errors: list[str],
) -> None:
    """Validate rate semantics, uncertainty gating, and exact zone summaries."""
    expected_rows = expected_csv_rows(expected)
    if len(actual) != 12 or {row.get("census_id") for row in actual} != {
        row["census_id"] for row in expected_rows
    }:
        errors.append("census-summary.csv must report all twelve census zones exactly once")
        return
    expected_by_id = {row["census_id"]: row for row in expected_rows}
    for row in actual:
        census_id = row["census_id"]
        expected_row = expected_by_id[census_id]
        try:
            total = int(row["total_population"])
            elderly = int(row["elderly_population"])
            rate = float(row["elderly_rate"])
        except (KeyError, TypeError, ValueError):
            errors.append(f"{census_id}: population and elderly_rate fields must be numeric")
            continue
        correct_rate = elderly / total
        if not math.isclose(rate, correct_rate, abs_tol=5e-7):
            errors.append(
                f"{census_id}: elderly_rate must equal elderly_population / "
                "total_population, not a raw count"
            )
        if row.get("selection_status") != expected_row["selection_status"]:
            errors.append(
                f"{census_id}: selection_status must apply the temperature, "
                "elderly-rate, and uncertainty gates"
            )
        for field in (
            "total_population",
            "elderly_population",
            "elderly_rate",
            "mean_temperature_c",
            "mean_uncertainty_c",
        ):
            if row.get(field) != expected_row[field]:
                errors.append(f"{census_id}: {field} differs from the reference")


def validate_report(
    actual: Any,
    expected: dict[str, Any],
    errors: list[str],
) -> None:
    """Validate empirical variogram and spatial-block evidence."""
    if not isinstance(actual, dict):
        errors.append("validation-report.json must contain a JSON object")
        return
    empirical = actual.get("empirical_variogram")
    if not isinstance(empirical, list) or not empirical:
        errors.append("validation-report.json must include empirical variogram diagnostics")
    elif any(
        not isinstance(bin_result, dict)
        or int(bin_result.get("pair_count", 0)) < 30
        for bin_result in empirical
    ):
        errors.append(
            "validation-report.json: every empirical variogram bin needs "
            "at least 30 point pairs"
        )
    if actual.get("validation_method") != "four-fold spatial block cross-validation":
        errors.append("validation-report.json must use four-fold spatial block validation")
    if actual.get("random_only_validation") is not False:
        errors.append("validation-report.json must reject random-only validation")
    block_cv = actual.get("spatial_block_cv")
    if (
        not isinstance(block_cv, dict)
        or not isinstance(block_cv.get("folds"), list)
        or len(block_cv["folds"]) != 4
    ):
        errors.append("validation-report.json must report all four spatial folds")
    if actual != expected:
        errors.append("validation-report.json differs from the reference diagnostics")


def validate_map(actual: str | None, expected: str, errors: list[str]) -> None:
    """Validate accessible SVG structure and exact cartographic rendering."""
    if actual is None:
        errors.append("missing artifact: urban-heat-map.svg")
        return
    required = [
        'role="img"',
        'aria-labelledby="map-title map-desc"',
        '<title id="map-title">',
        '<desc id="map-desc">',
        "Mean temperature (°C)",
        "Excluded: uncertainty",
        "Projection: EPSG:32636",
        "manual fixed temperature classes",
    ]
    for marker in required:
        if marker not in actual:
            errors.append(f"urban-heat-map.svg: missing accessibility marker {marker}")
    if actual.count('data-census-id="') != 12:
        errors.append("urban-heat-map.svg must render exactly twelve census zones")
    if actual != expected:
        errors.append("urban-heat-map.svg differs from the reference map")


def validate(input_path: Path, output_dir: Path) -> list[str]:
    """Validate the complete GAB-01 artifact contract."""
    errors: list[str] = []
    try:
        fixture = oracle.load_fixture(input_path)
        expected_temperature, expected_uncertainty = oracle.interpolate_surfaces(
            fixture
        )
        expected_summaries = oracle.summarize_zones(
            fixture,
            expected_temperature,
            expected_uncertainty,
        )
        expected_report = oracle.validation_report(fixture)
        expected_provenance = oracle.provenance(fixture)
        expected_map = oracle.render_svg(fixture, expected_summaries)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [f"input fixture is invalid: {exc}"]

    temperature = read_json(output_dir / "temperature-surface.json", errors)
    uncertainty = read_json(output_dir / "uncertainty-surface.json", errors)
    report = read_json(output_dir / "validation-report.json", errors)
    provenance = read_json(output_dir / "provenance.json", errors)
    validate_surface(
        temperature,
        expected_temperature,
        "temperature-surface.json",
        errors,
    )
    validate_surface(
        uncertainty,
        expected_uncertainty,
        "uncertainty-surface.json",
        errors,
    )
    validate_summary(
        read_summary(output_dir / "census-summary.csv", errors),
        expected_summaries,
        errors,
    )
    validate_report(report, expected_report, errors)
    if provenance != expected_provenance:
        errors.append("provenance.json must preserve CRS, model, grid, and risk rules")
    try:
        map_svg = (output_dir / "urban-heat-map.svg").read_text(encoding="utf-8")
    except FileNotFoundError:
        map_svg = None
    validate_map(map_svg, expected_map, errors)
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
    print("gab-01-urban-heat artifacts: pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
