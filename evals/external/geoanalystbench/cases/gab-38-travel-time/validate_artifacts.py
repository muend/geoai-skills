"""Validate all output artifacts for external case GAB-38."""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path
from typing import Any

EXPECTED: dict[str, tuple[float, list[str]] | None] = {
    "B": (2.0, ["A", "B"]),
    "C": (4.0, ["A", "B", "C"]),
    "D": (3.0, ["A", "D"]),
    "E": (5.0, ["A", "D", "E"]),
    "F": (6.0, ["A", "B", "C", "F"]),
    "G": None,
}


def load_json(path: Path, errors: list[str]) -> Any:
    """Load JSON while turning failures into validation errors."""
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"{path.name}: cannot read valid JSON: {exc}")
        return None


def validate_csv(output_dir: Path, errors: list[str]) -> None:
    """Validate destination coverage, exact costs, and exact paths."""
    path = output_dir / "travel-times.csv"
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
    except OSError as exc:
        errors.append(f"{path.name}: cannot read CSV: {exc}")
        return

    expected_fields = [
        "destination_id",
        "reachable",
        "travel_time_minutes",
        "path",
    ]
    if not rows:
        errors.append("travel-times.csv: no destination rows")
        return
    if list(rows[0]) != expected_fields:
        errors.append("travel-times.csv: unexpected columns or column order")
        return

    by_destination = {row["destination_id"]: row for row in rows}
    if len(rows) != len(EXPECTED) or set(by_destination) != set(EXPECTED):
        errors.append("travel-times.csv: must contain every destination exactly once")
        return

    for destination, expected in EXPECTED.items():
        row = by_destination[destination]
        if expected is None:
            if row["reachable"] != "false":
                errors.append(f"{destination}: unreachable destination marked reachable")
            if row["travel_time_minutes"] or row["path"]:
                errors.append(
                    f"{destination}: unreachable destination must have blank cost and path"
                )
            continue
        expected_cost, expected_path = expected
        if row["reachable"] != "true":
            errors.append(f"{destination}: reachable destination marked unreachable")
            continue
        try:
            actual_cost = float(row["travel_time_minutes"])
        except ValueError:
            errors.append(f"{destination}: travel time is not numeric")
            continue
        if not math.isclose(actual_cost, expected_cost, rel_tol=0.0, abs_tol=1e-9):
            errors.append(
                f"{destination}: expected {expected_cost} minutes, got {actual_cost}"
            )
        if row["path"].split(">") != expected_path:
            errors.append(f"{destination}: path does not match the expected directed route")


def validate_routes(
    network: dict[str, Any] | None,
    output_dir: Path,
    errors: list[str],
) -> None:
    """Validate route feature properties and ordered coordinates."""
    routes = load_json(output_dir / "routes.geojson", errors)
    if not isinstance(routes, dict) or not isinstance(network, dict):
        return
    if routes.get("type") != "FeatureCollection":
        errors.append("routes.geojson: type must be FeatureCollection")
        return
    crs_name = (
        routes.get("crs", {})
        .get("properties", {})
        .get("name")
    )
    if crs_name != "EPSG:32636":
        errors.append("routes.geojson: projected EPSG:32636 CRS is required")

    nodes = {
        node["id"]: [float(node["x"]), float(node["y"])]
        for node in network.get("nodes", [])
        if isinstance(node, dict) and "id" in node and "x" in node and "y" in node
    }
    features = routes.get("features")
    if not isinstance(features, list):
        errors.append("routes.geojson: features must be an array")
        return
    by_destination = {
        feature.get("properties", {}).get("destination_id"): feature
        for feature in features
        if isinstance(feature, dict)
    }
    reachable = {key for key, value in EXPECTED.items() if value is not None}
    if len(features) != len(reachable) or set(by_destination) != reachable:
        errors.append("routes.geojson: must contain exactly one route per reachable destination")
        return

    for destination in sorted(reachable):
        expected = EXPECTED[destination]
        if expected is None:
            errors.append(f"{destination}: internal reachable-route contract is invalid")
            continue
        expected_cost, expected_path = expected
        feature = by_destination[destination]
        properties = feature.get("properties", {})
        geometry = feature.get("geometry", {})
        if properties.get("path") != expected_path:
            errors.append(f"{destination}: GeoJSON path property is incorrect")
        if properties.get("travel_time_minutes") != expected_cost:
            errors.append(f"{destination}: GeoJSON travel time is incorrect")
        if geometry.get("type") != "LineString":
            errors.append(f"{destination}: route geometry must be a LineString")
            continue
        expected_coordinates = [nodes[node_id] for node_id in expected_path]
        if geometry.get("coordinates") != expected_coordinates:
            errors.append(f"{destination}: route coordinates do not match its node path")


def validate_summary(output_dir: Path, errors: list[str]) -> None:
    """Validate summary counts, units, directionality, and CRS."""
    summary = load_json(output_dir / "summary.json", errors)
    if not isinstance(summary, dict):
        return
    expected_fields = {
        "schema_version": 1,
        "origin": "A",
        "destination_count": 6,
        "reachable_count": 5,
        "unreachable_count": 1,
        "directed": True,
        "crs": "EPSG:32636",
        "cost_field": "time_minutes",
        "cost_units": "minutes",
    }
    for field, expected in expected_fields.items():
        if summary.get(field) != expected:
            errors.append(f"summary.json: {field} must equal {expected!r}")


def validate(input_path: Path, output_dir: Path) -> list[str]:
    """Return every artifact-contract violation."""
    errors: list[str] = []
    network = load_json(input_path, errors)
    validate_csv(output_dir, errors)
    validate_routes(network if isinstance(network, dict) else None, output_dir, errors)
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
    print("gab-38-travel-time artifacts: pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
