"""Executable contracts for GeoAnalystBench-derived case GAB-39."""

from __future__ import annotations

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
    / "gab-39-spatial-regression"
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
    input_path = fixture_dir / "spatial-regression.json"
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


def rewrite_json(path: Path, payload: object) -> None:
    """Write one deterministically formatted JSON artifact."""
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def test_fixture_generation_is_byte_deterministic(tmp_path: Path) -> None:
    """Repeated generation must produce identical fixture bytes."""
    first = tmp_path / "first"
    second = tmp_path / "second"
    assert run_script(GENERATOR, "--output-dir", str(first)).returncode == 0
    assert run_script(GENERATOR, "--output-dir", str(second)).returncode == 0
    assert (first / "spatial-regression.json").read_bytes() == (
        second / "spatial-regression.json"
    ).read_bytes()


def test_reference_outputs_pass_artifact_validation(tmp_path: Path) -> None:
    """The reference must satisfy every spatial-regression invariant."""
    input_path, output_dir = build_case(tmp_path)
    result = validate_case(input_path, output_dir)
    assert result.returncode == 0, result.stderr
    assert "artifacts: pass" in result.stdout


def test_validator_rejects_prompt_forced_local_model(tmp_path: Path) -> None:
    """A named local method may not override worse spatial-block performance."""
    input_path, output_dir = build_case(tmp_path)
    path = output_dir / "model-comparison.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["decision"]["selected_model"] = "Gaussian local weighted regression"
    payload["decision"]["prompt_named_model_forced"] = True
    rewrite_json(path, payload)
    result = validate_case(input_path, output_dir)
    assert result.returncode == 1
    assert "blocked RMSE is worse than OLS" in result.stderr
    assert "prompt may not force a local model" in result.stderr


def test_validator_rejects_random_only_validation(tmp_path: Path) -> None:
    """Random observation folds may not replace coherent spatial blocks."""
    input_path, output_dir = build_case(tmp_path)
    path = output_dir / "spatial-validation.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["method"] = "random four-fold cross-validation"
    payload["random_only_validation"] = True
    rewrite_json(path, payload)
    result = validate_case(input_path, output_dir)
    assert result.returncode == 1
    assert "must use four spatial blocks" in result.stderr
    assert "reject random-only validation" in result.stderr


def test_validator_rejects_missing_residual_dependence_diagnostic(
    tmp_path: Path,
) -> None:
    """OLS residual Moran evidence must precede the model decision."""
    input_path, output_dir = build_case(tmp_path)
    path = output_dir / "model-comparison.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["global_ols"].pop("residual_moran_primary")
    rewrite_json(path, payload)
    result = validate_case(input_path, output_dir)
    assert result.returncode == 1
    assert "queen OLS residual Moran diagnostics" in result.stderr


def test_validator_rejects_collinear_nuisance_in_final_model(tmp_path: Path) -> None:
    """The high-VIF proxy must not enter the final predictor set."""
    input_path, output_dir = build_case(tmp_path)
    path = output_dir / "collinearity-extrapolation.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["excluded_features"] = []
    payload["final_predictors"].append("green_share_proxy")
    rewrite_json(path, payload)
    result = validate_case(input_path, output_dir)
    assert result.returncode == 1
    assert "must be excluded from the final model" in result.stderr
    assert "may not enter the final model" in result.stderr


def test_validator_rejects_missing_fdr_uncertainty(tmp_path: Path) -> None:
    """Local coefficient maps must retain multiplicity-adjusted uncertainty."""
    input_path, output_dir = build_case(tmp_path)
    path = output_dir / "coefficient-uncertainty.geojson"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["features"][0]["properties"].pop("q_value")
    payload["features"][0]["properties"].pop("standard_error")
    rewrite_json(path, payload)
    result = validate_case(input_path, output_dir)
    assert result.returncode == 1
    assert "scale, uncertainty, FDR, support, and warning fields" in result.stderr


def test_validator_rejects_missing_scale_and_units(tmp_path: Path) -> None:
    """Coefficient maps without a scale or units are not interpretable."""
    input_path, output_dir = build_case(tmp_path)
    path = output_dir / "local-coefficients.geojson"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["coefficient_units"] = ""
    payload["features"][0]["properties"].pop("coefficient_scale")
    rewrite_json(path, payload)
    result = validate_case(input_path, output_dir)
    assert result.returncode == 1
    assert "coefficient scale and units must remain explicit" in result.stderr
    assert "scale, uncertainty, FDR, support, and warning fields" in result.stderr


def test_validator_rejects_suppressed_unstable_region_warning(
    tmp_path: Path,
) -> None:
    """Low-support local estimates must remain visibly qualified."""
    input_path, output_dir = build_case(tmp_path)
    path = output_dir / "local-coefficients.geojson"
    payload = json.loads(path.read_text(encoding="utf-8"))
    unstable = next(
        feature
        for feature in payload["features"]
        if feature["properties"]["stable"] is False
    )
    unstable["properties"]["warning"] = ""
    rewrite_json(path, payload)
    result = validate_case(input_path, output_dir)
    assert result.returncode == 1
    assert "unstable features need an explicit warning" in result.stderr
