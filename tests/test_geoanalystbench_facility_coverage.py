"""Executable contracts for GeoAnalystBench-derived case GAB-08."""

from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CASE = (
    ROOT
    / "evals"
    / "external"
    / "geoanalystbench"
    / "cases"
    / "gab-08-facility-coverage"
)
GENERATOR = CASE / "generate_fixture.py"
REFERENCE = CASE / "reference.py"
VALIDATOR = CASE / "validate_artifacts.py"


def run_script(script: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    """Run a repository script with deterministic UTF-8 capture."""
    return subprocess.run(  # noqa: S603 - interpreter and scripts are repo constants
        [sys.executable, str(script), *arguments],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        timeout=30,
    )


def build_case(tmp_path: Path) -> tuple[Path, Path]:
    """Generate fixtures and reference outputs for one isolated test."""
    fixture_dir = tmp_path / "fixtures"
    output_dir = tmp_path / "outputs"
    generated = run_script(GENERATOR, "--output-dir", str(fixture_dir))
    assert generated.returncode == 0, generated.stderr
    input_path = fixture_dir / "coverage-network.json"
    reference = run_script(
        REFERENCE,
        "--input",
        str(input_path),
        "--output-dir",
        str(output_dir),
    )
    assert reference.returncode == 0, reference.stderr
    return input_path, output_dir


def validate_case(input_path: Path, output_dir: Path) -> subprocess.CompletedProcess[str]:
    """Run the artifact validator."""
    return run_script(
        VALIDATOR,
        "--input",
        str(input_path),
        "--output-dir",
        str(output_dir),
    )


def test_fixture_generation_is_byte_deterministic(tmp_path: Path) -> None:
    """Repeated generation must produce identical fixture bytes."""
    first = tmp_path / "first"
    second = tmp_path / "second"
    assert run_script(GENERATOR, "--output-dir", str(first)).returncode == 0
    assert run_script(GENERATOR, "--output-dir", str(second)).returncode == 0
    assert (first / "coverage-network.json").read_bytes() == (
        second / "coverage-network.json"
    ).read_bytes()


def test_reference_outputs_pass_artifact_validation(tmp_path: Path) -> None:
    """The independent reference must satisfy every coverage invariant."""
    input_path, output_dir = build_case(tmp_path)
    result = validate_case(input_path, output_dir)
    assert result.returncode == 0, result.stderr
    assert "artifacts: pass" in result.stdout


def test_validator_rejects_euclidean_substitution(tmp_path: Path) -> None:
    """Spatial proximity must not override the eight-minute network cost for D6."""
    input_path, output_dir = build_case(tmp_path)
    csv_path = output_dir / "demand-coverage.csv"
    with csv_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    d6 = next(row for row in rows if row["demand_id"] == "D6")
    d6["covered"] = "true"
    d6["travel_time_minutes"] = "0.500"
    d6["facilities_within_cutoff"] = "F1"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    result = validate_case(input_path, output_dir)
    assert result.returncode == 1
    assert "D6: covered must equal 'false'" in result.stderr
    assert "expected 8.0 minutes" in result.stderr


def test_validator_rejects_overlap_population_double_count(tmp_path: Path) -> None:
    """Population covered by two facilities must contribute only once."""
    input_path, output_dir = build_case(tmp_path)
    summary_path = output_dir / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["covered_population"] = 1020
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    result = validate_case(input_path, output_dir)
    assert result.returncode == 1
    assert "covered_population must equal 570" in result.stderr


def test_validator_rejects_silently_dropped_unreachable_demand(
    tmp_path: Path,
) -> None:
    """Disconnected demand must remain explicit in the result table."""
    input_path, output_dir = build_case(tmp_path)
    csv_path = output_dir / "demand-coverage.csv"
    with csv_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(row for row in rows if row["demand_id"] != "D7")

    result = validate_case(input_path, output_dir)
    assert result.returncode == 1
    assert "every demand exactly once" in result.stderr


def test_validator_rejects_missing_service_gap(tmp_path: Path) -> None:
    """The map artifact must expose the barrier-affected D6 demand."""
    input_path, output_dir = build_case(tmp_path)
    gaps_path = output_dir / "service-gaps.geojson"
    gaps = json.loads(gaps_path.read_text(encoding="utf-8"))
    gaps["features"] = [
        feature
        for feature in gaps["features"]
        if feature["properties"]["demand_id"] != "D6"
    ]
    gaps_path.write_text(
        json.dumps(gaps, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    result = validate_case(input_path, output_dir)
    assert result.returncode == 1
    assert "must contain exactly D5, D6, and D7" in result.stderr
