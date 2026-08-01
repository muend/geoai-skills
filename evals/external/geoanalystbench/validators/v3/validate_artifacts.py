"""Validate v3 external artifacts against disclosed semantic contracts."""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import math
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

SUITE_ROOT = Path(__file__).resolve().parents[2]
CASE_BY_FIXTURE = {
    "coverage-network.json": "gab-08-facility-coverage",
    "hailstorm-scenes.json": "gab-36-vegetation-change",
    "network.json": "gab-38-travel-time",
    "spatial-regression.json": "gab-39-spatial-regression",
    "urban-heat.json": "gab-01-urban-heat",
}
NUMERIC_TOLERANCE = 1.1e-6


def load_module(path: Path, name: str) -> ModuleType:
    """Load one frozen case module without requiring package imports."""
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_json(path: Path, errors: list[str]) -> Any:
    """Read a UTF-8 JSON artifact and record parse failures."""
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"{path.name}: cannot read valid JSON: {exc}")
        return None


def compare_semantic(actual: Any, expected: Any, path: str, errors: list[str]) -> None:
    """Compare disclosed structures while tolerating insignificant float noise."""
    if isinstance(expected, bool) or expected is None or isinstance(expected, str):
        if actual != expected:
            errors.append(f"{path}: expected {expected!r}, found {actual!r}")
        return
    if isinstance(expected, int | float):
        if isinstance(actual, bool) or not isinstance(actual, int | float):
            errors.append(f"{path}: expected a numeric value")
            return
        if not math.isclose(
            float(actual), float(expected), rel_tol=0.0, abs_tol=NUMERIC_TOLERANCE
        ):
            errors.append(f"{path}: numeric value differs from the semantic oracle")
        return
    if isinstance(expected, list):
        if not isinstance(actual, list) or len(actual) != len(expected):
            errors.append(f"{path}: list shape differs from the disclosed contract")
            return
        for index, (actual_item, expected_item) in enumerate(
            zip(actual, expected, strict=True)
        ):
            compare_semantic(
                actual_item, expected_item, f"{path}[{index}]", errors
            )
        return
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            errors.append(f"{path}: expected an object")
            return
        if set(actual) != set(expected):
            errors.append(f"{path}: object keys differ from the disclosed contract")
            return
        for key in expected:
            compare_semantic(actual[key], expected[key], f"{path}.{key}", errors)
        return
    errors.append(f"{path}: unsupported semantic oracle type")


def validate_csv_summary(
    path: Path,
    expected_rows: list[dict[str, Any]],
    errors: list[str],
) -> None:
    """Validate GAB-01 census rows with a one-micro-unit numeric tolerance."""
    fields = [
        "census_id",
        "total_population",
        "elderly_population",
        "elderly_rate",
        "mean_temperature_c",
        "mean_uncertainty_c",
        "selection_status",
    ]
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            actual_rows = list(reader)
            if reader.fieldnames != fields:
                errors.append("census-summary.csv: columns differ from the contract")
                return
    except OSError as exc:
        errors.append(f"census-summary.csv: cannot read CSV: {exc}")
        return
    if len(actual_rows) != len(expected_rows):
        errors.append("census-summary.csv: row count differs from the contract")
        return
    numeric = {
        "total_population",
        "elderly_population",
        "elderly_rate",
        "mean_temperature_c",
        "mean_uncertainty_c",
    }
    for index, (actual, expected) in enumerate(
        zip(actual_rows, expected_rows, strict=True)
    ):
        for field in fields:
            if field in numeric:
                try:
                    value = float(actual[field])
                except (TypeError, ValueError):
                    errors.append(f"census-summary.csv[{index}].{field}: not numeric")
                    continue
                if not math.isclose(
                    value,
                    float(expected[field]),
                    rel_tol=0.0,
                    abs_tol=NUMERIC_TOLERANCE,
                ):
                    errors.append(
                        f"census-summary.csv[{index}].{field}: value differs"
                    )
            elif actual[field] != str(expected[field]):
                errors.append(f"census-summary.csv[{index}].{field}: value differs")


def validate_urban_heat(input_path: Path, output_dir: Path) -> list[str]:
    """Validate GAB-01 numerics exactly enough without requiring reference SVG bytes."""
    errors: list[str] = []
    case_dir = SUITE_ROOT / "cases" / "gab-01-urban-heat"
    oracle = load_module(case_dir / "reference.py", "gab01_reference_v3")
    fixture = oracle.load_fixture(input_path)
    temperature, uncertainty = oracle.interpolate_surfaces(fixture)
    summaries = oracle.summarize_zones(fixture, temperature, uncertainty)
    expected_json = {
        "temperature-surface.json": temperature,
        "uncertainty-surface.json": uncertainty,
        "validation-report.json": oracle.validation_report(fixture),
        "provenance.json": oracle.provenance(fixture),
    }
    for filename, expected in expected_json.items():
        actual = read_json(output_dir / filename, errors)
        if actual is not None:
            compare_semantic(actual, expected, filename, errors)
    validate_csv_summary(output_dir / "census-summary.csv", summaries, errors)

    try:
        svg = (output_dir / "urban-heat-map.svg").read_text(encoding="utf-8-sig")
    except OSError as exc:
        errors.append(f"urban-heat-map.svg: cannot read SVG: {exc}")
        return errors
    required_markers = [
        '<svg',
        'role="img"',
        'aria-labelledby="map-title map-desc"',
        '<title id="map-title">',
        '<desc id="map-desc">',
        "Mean temperature (°C)",
        "Excluded: uncertainty",
        "Projection: EPSG:32636",
        "manual fixed temperature classes",
        "</svg>",
    ]
    for marker in required_markers:
        if marker not in svg:
            errors.append(f"urban-heat-map.svg: missing semantic marker {marker}")
    expected_ids = [str(zone["census_id"]) for zone in fixture["census_zones"]]
    for census_id in expected_ids:
        if svg.count(f'data-census-id="{census_id}"') != 1:
            errors.append(
                f"urban-heat-map.svg: census zone {census_id} must appear once"
            )
    return errors


def validate_spatial_regression(input_path: Path, output_dir: Path) -> list[str]:
    """Validate GAB-39 disclosed JSON/GeoJSON structures semantically."""
    errors: list[str] = []
    case_dir = SUITE_ROOT / "cases" / "gab-39-spatial-regression"
    oracle = load_module(case_dir / "reference.py", "gab39_reference_v3")
    fixture = oracle.load_fixture(input_path)
    expected = oracle.build_outputs(fixture)
    for filename, expected_payload in expected.items():
        actual = read_json(output_dir / filename, errors)
        if actual is not None:
            compare_semantic(actual, expected_payload, filename, errors)
    return errors


def validate(input_path: Path, output_dir: Path) -> list[str]:
    """Dispatch one fixture to its immutable v3 semantic validator."""
    case_id = CASE_BY_FIXTURE.get(input_path.name)
    if case_id is None:
        return [f"unsupported fixture filename: {input_path.name}"]
    if case_id == "gab-01-urban-heat":
        return validate_urban_heat(input_path, output_dir)
    if case_id == "gab-39-spatial-regression":
        return validate_spatial_regression(input_path, output_dir)
    case_dir = SUITE_ROOT / "cases" / case_id
    legacy = load_module(case_dir / "validate_artifacts.py", f"{case_id}_validator_v3")
    return list(legacy.validate(input_path, output_dir))


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    """Run validation and return a process-friendly status."""
    args = parse_args()
    try:
        errors = validate(args.input, args.output_dir)
    except (KeyError, OSError, RuntimeError, TypeError, ValueError) as exc:
        print(f"ERROR: v3 validator failed: {exc}", file=sys.stderr)
        return 1
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"PASS: {args.input.name} satisfies artifact contract v3")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
