"""Executable contracts for GeoAnalystBench-derived case GAB-01."""

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
    / "gab-01-urban-heat"
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
    input_path = fixture_dir / "urban-heat.json"
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
    assert (first / "urban-heat.json").read_bytes() == (
        second / "urban-heat.json"
    ).read_bytes()


def test_reference_outputs_pass_artifact_validation(tmp_path: Path) -> None:
    """The reference must satisfy interpolation, validation, and map contracts."""
    input_path, output_dir = build_case(tmp_path)
    result = validate_case(input_path, output_dir)
    assert result.returncode == 0, result.stderr
    assert "artifacts: pass" in result.stdout


def test_validator_rejects_interpolation_in_degrees(tmp_path: Path) -> None:
    """A geographic CRS must fail the projected-distance contract."""
    input_path, output_dir = build_case(tmp_path)
    surface_path = output_dir / "temperature-surface.json"
    surface = json.loads(surface_path.read_text(encoding="utf-8"))
    surface["crs"] = "EPSG:4326"
    surface_path.write_text(
        json.dumps(surface, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    result = validate_case(input_path, output_dir)
    assert result.returncode == 1
    assert "interpolation CRS must remain projected EPSG:32636" in result.stderr


def test_validator_rejects_missing_variogram_diagnostics(tmp_path: Path) -> None:
    """A fitted surface without empirical variogram evidence must fail."""
    input_path, output_dir = build_case(tmp_path)
    report_path = output_dir / "validation-report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report.pop("empirical_variogram")
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    result = validate_case(input_path, output_dir)
    assert result.returncode == 1
    assert "empirical variogram diagnostics" in result.stderr


def test_validator_rejects_random_only_validation(tmp_path: Path) -> None:
    """Random folds may not replace spatial block validation."""
    input_path, output_dir = build_case(tmp_path)
    report_path = output_dir / "validation-report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["validation_method"] = "random four-fold cross-validation"
    report["random_only_validation"] = True
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    result = validate_case(input_path, output_dir)
    assert result.returncode == 1
    assert "four-fold spatial block validation" in result.stderr
    assert "random-only validation" in result.stderr


def test_validator_rejects_population_count_as_rate(tmp_path: Path) -> None:
    """Vulnerability must use elderly share rather than the elderly count."""
    input_path, output_dir = build_case(tmp_path)
    summary_path = output_dir / "census-summary.csv"
    with summary_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    rows[3]["elderly_rate"] = rows[3]["elderly_population"]
    with summary_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    result = validate_case(input_path, output_dir)
    assert result.returncode == 1
    assert "not a raw count" in result.stderr


def test_validator_rejects_high_risk_without_uncertainty_gate(
    tmp_path: Path,
) -> None:
    """A hot vulnerable but unsupported zone must not be selected."""
    input_path, output_dir = build_case(tmp_path)
    summary_path = output_dir / "census-summary.csv"
    with summary_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    excluded = next(
        row for row in rows if row["selection_status"] == "uncertainty_excluded"
    )
    excluded["selection_status"] = "selected"
    with summary_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    result = validate_case(input_path, output_dir)
    assert result.returncode == 1
    assert "temperature, elderly-rate, and uncertainty gates" in result.stderr


def test_validator_rejects_inaccessible_map(tmp_path: Path) -> None:
    """The public map artifact must expose an accessible name and description."""
    input_path, output_dir = build_case(tmp_path)
    map_path = output_dir / "urban-heat-map.svg"
    content = map_path.read_text(encoding="utf-8")
    map_path.write_text(
        content.replace(' role="img"', ""),
        encoding="utf-8",
        newline="\n",
    )
    result = validate_case(input_path, output_dir)
    assert result.returncode == 1
    assert 'missing accessibility marker role="img"' in result.stderr
