"""Executable contracts for GeoAnalystBench-derived case GAB-36."""

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
    / "gab-36-vegetation-change"
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
    input_path = fixture_dir / "hailstorm-scenes.json"
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
    assert (first / "hailstorm-scenes.json").read_bytes() == (
        second / "hailstorm-scenes.json"
    ).read_bytes()


def test_reference_outputs_pass_artifact_validation(tmp_path: Path) -> None:
    """The independent reference must satisfy every vegetation-change invariant."""
    input_path, output_dir = build_case(tmp_path)
    result = validate_case(input_path, output_dir)
    assert result.returncode == 0, result.stderr
    assert "artifacts: pass" in result.stdout


def test_validator_rejects_unintersected_quality_masks(tmp_path: Path) -> None:
    """A cell invalid on either date must remain null in every analytical grid."""
    input_path, output_dir = build_case(tmp_path)
    change_path = output_dir / "savi-change.json"
    change = json.loads(change_path.read_text(encoding="utf-8"))
    change["valid_overlap"][3][2] = True
    change["pre_savi"][3][2] = 0.461538462
    change["post_savi"][3][2] = 0.0
    change["delta_savi"][3][2] = -0.461538462
    change["damage_mask"][3][2] = True
    change_path.write_text(
        json.dumps(change, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    result = validate_case(input_path, output_dir)
    assert result.returncode == 1
    assert "valid-overlap mask is incorrect" in result.stderr
    assert "invalid cell outputs must all be null" in result.stderr


def test_validator_rejects_wrong_savi_scaling(tmp_path: Path) -> None:
    """SAVI values must reflect the declared DN scale and soil factor."""
    input_path, output_dir = build_case(tmp_path)
    change_path = output_dir / "savi-change.json"
    change = json.loads(change_path.read_text(encoding="utf-8"))
    change["pre_savi"][0][0] = 0.499968752
    change_path.write_text(
        json.dumps(change, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    result = validate_case(input_path, output_dir)
    assert result.returncode == 1
    assert "pre_savi does not match scaled SAVI" in result.stderr


def test_validator_rejects_wrong_hectare_conversion(tmp_path: Path) -> None:
    """Seven 100-square-metre cells equal 0.07 hectares, not seven hectares."""
    input_path, output_dir = build_case(tmp_path)
    summary_path = output_dir / "change-summary.csv"
    with summary_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    main_row = next(row for row in rows if row["threshold"] == "-0.200")
    main_row["damaged_area_hectares"] = "7.0000"
    with summary_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    result = validate_case(input_path, output_dir)
    assert result.returncode == 1
    assert "damaged area must equal 0.07 hectares" in result.stderr


def test_validator_rejects_missing_threshold_sensitivity(tmp_path: Path) -> None:
    """The primary area claim must retain both registered sensitivity bounds."""
    input_path, output_dir = build_case(tmp_path)
    summary_path = output_dir / "change-summary.csv"
    with summary_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    with summary_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(row for row in rows if row["threshold"] != "-0.250")

    result = validate_case(input_path, output_dir)
    assert result.returncode == 1
    assert "all three registered thresholds are required" in result.stderr


def test_validator_rejects_registration_claim_drift(tmp_path: Path) -> None:
    """Published provenance must preserve the registered co-registration RMSE."""
    input_path, output_dir = build_case(tmp_path)
    provenance_path = output_dir / "provenance.json"
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    provenance["co_registration_rmse_pixels"] = 1.0
    provenance_path.write_text(
        json.dumps(provenance, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    result = validate_case(input_path, output_dir)
    assert result.returncode == 1
    assert "co_registration_rmse_pixels must equal 0.1" in result.stderr
