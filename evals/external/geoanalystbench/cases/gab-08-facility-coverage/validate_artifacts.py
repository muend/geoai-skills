"""Validate all output artifacts for external case GAB-08."""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path
from typing import Any


EXPECTED: dict[str, dict[str, Any]] = {
    "D1": {
        "population": 100,
        "reachable": True,
        "covered": True,
        "assigned_facility": "F1",
        "travel_time_minutes": 2.0,
        "facilities_within_cutoff": ["F1", "F2"],
        "path": ["A", "B"],
    },
    "D2": {
        "population": 200,
        "reachable": True,
        "covered": True,
        "assigned_facility": "F2",
        "travel_time_minutes": 2.0,
        "facilities_within_cutoff": ["F1", "F2"],
        "path": ["E", "C"],
    },
    "D3": {
        "population": 150,
        "reachable": True,
        "covered": True,
        "assigned_facility": "F1",
        "travel_time_minutes": 4.0,
        "facilities_within_cutoff": ["F1", "F2"],
        "path": ["A", "D"],
    },
    "D4": {
        "population": 120,
        "reachable": True,
        "covered": True,
        "assigned_facility": "F2",
        "travel_time_minutes": 3.0,
        "facilities_within_cutoff": ["F2"],
        "path": ["E", "F"],
    },
    "D5": {
        "population": 80,
        "reachable": True,
        "covered": False,
        "assigned_facility": "F2",
        "travel_time_minutes": 6.0,
        "facilities_within_cutoff": [],
        "path": ["E", "F", "G"],
    },
    "D6": {
        "population": 90,
        "reachable": True,
        "covered": False,
        "assigned_facility": "F1",
        "travel_time_minutes": 8.0,
        "facilities_within_cutoff": [],
        "path": ["A", "H"],
    },
    "D7": {
        "population": 60,
        "reachable": False,
        "covered": False,
        "assigned_facility": "",
        "travel_time_minutes": None,
        "facilities_within_cutoff": [],
        "path": [],
    },
}


def load_json(path: Path, errors: list[str]) -> Any:
    """Load JSON while turning failures into validation errors."""
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"{path.name}: cannot read valid JSON: {exc}")
        return None


def validate_csv(output_dir: Path, errors: list[str]) -> None:
    """Validate exact assignments, network costs, overlap, and demand coverage."""
    path = output_dir / "demand-coverage.csv"
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
    except OSError as exc:
        errors.append(f"{path.name}: cannot read CSV: {exc}")
        return

    expected_fields = [
        "demand_id",
        "population",
        "reachable",
        "covered",
        "assigned_facility",
        "travel_time_minutes",
        "facilities_within_cutoff",
        "path",
    ]
    if not rows:
        errors.append("demand-coverage.csv: no demand rows")
        return
    if list(rows[0]) != expected_fields:
        errors.append("demand-coverage.csv: unexpected columns or column order")
        return
    by_demand = {row["demand_id"]: row for row in rows}
    if len(rows) != len(EXPECTED) or set(by_demand) != set(EXPECTED):
        errors.append("demand-coverage.csv: must contain every demand exactly once")
        return

    for demand_id, expected in EXPECTED.items():
        row = by_demand[demand_id]
        scalar_expectations = {
            "population": str(expected["population"]),
            "reachable": str(expected["reachable"]).lower(),
            "covered": str(expected["covered"]).lower(),
            "assigned_facility": expected["assigned_facility"],
            "facilities_within_cutoff": "|".join(
                expected["facilities_within_cutoff"]
            ),
            "path": ">".join(expected["path"]),
        }
        for field, value in scalar_expectations.items():
            if row[field] != value:
                errors.append(f"{demand_id}: {field} must equal {value!r}")

        expected_time = expected["travel_time_minutes"]
        if expected_time is None:
            if row["travel_time_minutes"]:
                errors.append(f"{demand_id}: unreachable demand must have blank time")
            continue
        try:
            actual_time = float(row["travel_time_minutes"])
        except ValueError:
            errors.append(f"{demand_id}: travel time is not numeric")
            continue
        if not math.isclose(actual_time, expected_time, rel_tol=0.0, abs_tol=1e-9):
            errors.append(
                f"{demand_id}: expected {expected_time} minutes, got {actual_time}"
            )


def validate_gaps(
    network: dict[str, Any] | None,
    output_dir: Path,
    errors: list[str],
) -> None:
    """Validate uncovered-demand point artifacts and reasons."""
    gaps = load_json(output_dir / "service-gaps.geojson", errors)
    if not isinstance(gaps, dict) or not isinstance(network, dict):
        return
    crs_name = gaps.get("crs", {}).get("properties", {}).get("name")
    if gaps.get("type") != "FeatureCollection" or crs_name != "EPSG:32636":
        errors.append("service-gaps.geojson: FeatureCollection in EPSG:32636 required")
        return
    nodes = {
        node["id"]: [float(node["x"]), float(node["y"])]
        for node in network.get("nodes", [])
        if isinstance(node, dict) and {"id", "x", "y"} <= set(node)
    }
    demand_nodes = {
        demand["demand_id"]: demand["node_id"]
        for demand in network.get("demands", [])
        if isinstance(demand, dict)
    }
    features = gaps.get("features")
    if not isinstance(features, list):
        errors.append("service-gaps.geojson: features must be an array")
        return
    by_demand = {
        feature.get("properties", {}).get("demand_id"): feature
        for feature in features
        if isinstance(feature, dict)
    }
    if len(features) != 3 or set(by_demand) != {"D5", "D6", "D7"}:
        errors.append("service-gaps.geojson: must contain exactly D5, D6, and D7")
        return

    expected_reasons = {"D5": "beyond_cutoff", "D6": "beyond_cutoff", "D7": "unreachable"}
    for demand_id, reason in expected_reasons.items():
        feature = by_demand[demand_id]
        properties = feature.get("properties", {})
        geometry = feature.get("geometry", {})
        if properties.get("reason") != reason:
            errors.append(f"{demand_id}: incorrect service-gap reason")
        if geometry.get("type") != "Point":
            errors.append(f"{demand_id}: service gap must use Point geometry")
            continue
        expected_coordinates = nodes[demand_nodes[demand_id]]
        if geometry.get("coordinates") != expected_coordinates:
            errors.append(f"{demand_id}: service-gap coordinates are incorrect")


def validate_summary(output_dir: Path, errors: list[str]) -> None:
    """Validate deduplicated population totals and analysis assumptions."""
    summary = load_json(output_dir / "summary.json", errors)
    if not isinstance(summary, dict):
        return
    expected_fields = {
        "schema_version": 1,
        "crs": "EPSG:32636",
        "mode": "driving",
        "cost_field": "time_minutes",
        "cost_units": "minutes",
        "coverage_cutoff_minutes": 5.0,
        "facility_count": 2,
        "demand_count": 7,
        "covered_demand_count": 4,
        "uncovered_demand_count": 3,
        "unreachable_demand_count": 1,
        "overlap_demand_count": 3,
        "overlap_population": 450,
        "total_population": 800,
        "covered_population": 570,
        "uncovered_population": 230,
        "coverage_share": 0.7125,
    }
    for field, expected in expected_fields.items():
        actual = summary.get(field)
        if isinstance(expected, float) and isinstance(actual, (int, float)):
            if math.isclose(float(actual), expected, rel_tol=0.0, abs_tol=1e-12):
                continue
        elif actual == expected:
            continue
        errors.append(f"summary.json: {field} must equal {expected!r}")


def validate(input_path: Path, output_dir: Path) -> list[str]:
    """Return every artifact-contract violation."""
    errors: list[str] = []
    network = load_json(input_path, errors)
    validate_csv(output_dir, errors)
    validate_gaps(network if isinstance(network, dict) else None, output_dir, errors)
    validate_summary(output_dir, errors)
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
    print("gab-08-facility-coverage artifacts: pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
