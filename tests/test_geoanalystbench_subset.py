"""Executable contract tests for the isolated GeoAnalystBench-derived subset."""

from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SUITE = ROOT / "evals" / "external" / "geoanalystbench"
CASE = SUITE / "cases" / "gab-38-travel-time"
GENERATOR = CASE / "generate_fixture.py"
REFERENCE = CASE / "reference.py"
ARTIFACT_VALIDATOR = CASE / "validate_artifacts.py"
SUITE_VALIDATOR = ROOT / "tools" / "validate_external_evals.py"
UPSTREAM_SHA = "b5d8c40a8d23639ec77e9acb11f79fd033c07338"


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
    reference = run_script(
        REFERENCE,
        "--input",
        str(fixture_dir / "network.json"),
        "--output-dir",
        str(output_dir),
    )
    assert reference.returncode == 0, reference.stderr
    return fixture_dir / "network.json", output_dir


def validate_case(input_path: Path, output_dir: Path) -> subprocess.CompletedProcess[str]:
    """Run the artifact validator."""
    return run_script(
        ARTIFACT_VALIDATOR,
        "--input",
        str(input_path),
        "--output-dir",
        str(output_dir),
    )


def test_external_suite_metadata_validates() -> None:
    """External cases must pass their separate schema and boundary validator."""
    result = run_script(SUITE_VALIDATOR)
    assert result.returncode == 0, result.stderr
    assert "3 external cases checked — 0 errors" in result.stdout


def test_fixture_generation_is_byte_deterministic(tmp_path: Path) -> None:
    """Repeated generation must produce identical fixture bytes."""
    first = tmp_path / "first"
    second = tmp_path / "second"
    assert run_script(GENERATOR, "--output-dir", str(first)).returncode == 0
    assert run_script(GENERATOR, "--output-dir", str(second)).returncode == 0
    assert (first / "network.json").read_bytes() == (second / "network.json").read_bytes()


def test_reference_outputs_pass_artifact_validation(tmp_path: Path) -> None:
    """The independent reference must satisfy the complete artifact contract."""
    input_path, output_dir = build_case(tmp_path)
    result = validate_case(input_path, output_dir)
    assert result.returncode == 0, result.stderr
    assert "artifacts: pass" in result.stdout


def test_validator_rejects_incorrect_travel_time(tmp_path: Path) -> None:
    """A plausible but wrong cost must not pass."""
    input_path, output_dir = build_case(tmp_path)
    csv_path = output_dir / "travel-times.csv"
    with csv_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    rows[3]["travel_time_minutes"] = "3.000"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    result = validate_case(input_path, output_dir)
    assert result.returncode == 1
    assert "expected 5.0 minutes" in result.stderr


def test_validator_rejects_silently_dropped_unreachable_destination(
    tmp_path: Path,
) -> None:
    """A common network-analysis omission must fail closed."""
    input_path, output_dir = build_case(tmp_path)
    csv_path = output_dir / "travel-times.csv"
    with csv_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(row for row in rows if row["destination_id"] != "G")

    result = validate_case(input_path, output_dir)
    assert result.returncode == 1
    assert "every destination exactly once" in result.stderr


def test_validator_rejects_route_geometry_that_disagrees_with_path(
    tmp_path: Path,
) -> None:
    """Route artifacts must be spatially consistent, not merely present."""
    input_path, output_dir = build_case(tmp_path)
    routes_path = output_dir / "routes.geojson"
    routes = json.loads(routes_path.read_text(encoding="utf-8"))
    routes["features"][0]["geometry"]["coordinates"].reverse()
    routes_path.write_text(
        json.dumps(routes, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    result = validate_case(input_path, output_dir)
    assert result.returncode == 1
    assert "route coordinates do not match" in result.stderr


def test_provenance_pins_upstream_and_excludes_upstream_assets() -> None:
    """The external subset must retain its legal and methodological boundary."""
    provenance = json.loads(
        (SUITE / "provenance.json").read_text(encoding="utf-8")
    )
    assert provenance["upstream"]["commit_sha"] == UPSTREAM_SHA
    assert provenance["upstream"]["license"] == "Apache-2.0"
    assert provenance["reuse"] == {
        "upstream_datasets_included": False,
        "upstream_reference_code_included": False,
        "upstream_prompts_copied_verbatim": False,
        "fixture_origin": "deterministic-synthetic",
        "implementation_origin": "independently-authored",
    }
    assert (SUITE / "LICENSE-APACHE-2.0").is_file()


@pytest.mark.parametrize("forbidden_name", ["evals", "private-planning"])
def test_external_material_is_not_inside_runtime_skills(forbidden_name: str) -> None:
    """External development evidence must not leak into runtime skill installs."""
    assert not any(
        forbidden_name in path.parts
        for path in (ROOT / "skills").rglob("*")
        if path.is_file()
    )
