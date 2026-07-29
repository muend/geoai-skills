"""Validate artifacts for external GeoAnalystBench-derived case GAB-39."""

from __future__ import annotations

import argparse
import json
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


def validate_model_comparison(
    actual: Any,
    expected: dict[str, Any],
    errors: list[str],
) -> None:
    """Validate OLS-first diagnostics and the model-selection gate."""
    if not isinstance(actual, dict):
        errors.append("model-comparison.json must contain a JSON object")
        return
    global_ols = actual.get("global_ols")
    if not isinstance(global_ols, dict) or global_ols.get("fit_order") != 1:
        errors.append("model-comparison.json must fit global OLS before local models")
    else:
        primary = global_ols.get("residual_moran_primary")
        sensitivity = global_ols.get("residual_moran_sensitivity")
        if (
            not isinstance(primary, dict)
            or primary.get("weights") != "queen"
            or primary.get("permutations") != 999
        ):
            errors.append(
                "model-comparison.json must include queen OLS residual Moran "
                "diagnostics with 999 permutations"
            )
        if not isinstance(sensitivity, dict) or sensitivity.get("weights") != "rook":
            errors.append(
                "model-comparison.json must include rook residual-Moran sensitivity"
            )
    decision = actual.get("decision")
    if not isinstance(decision, dict):
        errors.append("model-comparison.json must include a model decision")
    else:
        if decision.get("selected_model") != "global OLS":
            errors.append(
                "local model may not be selected when blocked RMSE is worse than OLS"
            )
        if decision.get("prompt_named_model_forced") is not False:
            errors.append("the prompt may not force a local model")
        if decision.get("causal_claim_allowed") is not False:
            errors.append("spatial association may not be reported as causal")
    if actual != expected:
        errors.append("model-comparison.json differs from the reference decision")


def validate_spatial_validation(
    actual: Any,
    expected: dict[str, Any],
    errors: list[str],
) -> None:
    """Validate coherent blocked splits and metrics."""
    if not isinstance(actual, dict):
        errors.append("spatial-validation.json must contain a JSON object")
        return
    if actual.get("method") != "four-fold spatial block cross-validation":
        errors.append("spatial-validation.json must use four spatial blocks")
    if actual.get("random_only_validation") is not False:
        errors.append("spatial-validation.json must reject random-only validation")
    leakage = actual.get("leakage_audit")
    if (
        not isinstance(leakage, dict)
        or leakage.get("same_area_in_train_and_test") is not False
        or leakage.get("preprocessing_fit_scope") != "training fold only"
    ):
        errors.append("spatial-validation.json must prove a leakage-free split")
    folds = actual.get("folds")
    if not isinstance(folds, list) or len(folds) != 4:
        errors.append("spatial-validation.json must report all four spatial folds")
    if actual != expected:
        errors.append("spatial-validation.json differs from the reference metrics")


def validate_collinearity(
    actual: Any,
    expected: dict[str, Any],
    errors: list[str],
) -> None:
    """Validate VIF exclusion and extrapolation warnings."""
    if not isinstance(actual, dict):
        errors.append("collinearity-extrapolation.json must contain a JSON object")
        return
    vif = actual.get("vif")
    if (
        not isinstance(vif, dict)
        or float(vif.get("green_share_proxy", 0.0)) <= 10.0
    ):
        errors.append("green_share_proxy must be diagnosed above the VIF threshold")
    if "green_share_proxy" not in actual.get("excluded_features", []):
        errors.append("green_share_proxy must be excluded from the final model")
    if "green_share_proxy" in actual.get("final_predictors", []):
        errors.append("the collinear nuisance feature may not enter the final model")
    support = actual.get("local_fit_support")
    if (
        not isinstance(support, dict)
        or not support.get("unstable_area_ids")
        or "warning" not in support
    ):
        errors.append(
            "collinearity-extrapolation.json must retain unstable-region warnings"
        )
    if actual != expected:
        errors.append("collinearity-extrapolation.json differs from the reference")


def validate_map(
    actual: Any,
    expected: dict[str, Any],
    filename: str,
    uncertainty: bool,
    errors: list[str],
) -> None:
    """Validate coefficient-map units, FDR, support, and exact geometry."""
    if not isinstance(actual, dict):
        errors.append(f"{filename} must contain a GeoJSON object")
        return
    if actual.get("crs") != "EPSG:32636":
        errors.append(f"{filename}: map CRS must remain EPSG:32636")
    if actual.get("coordinate_units") != "metres":
        errors.append(f"{filename}: map coordinate units must be metres")
    if actual.get("coefficient_units") != (
        "degrees Celsius per unit green-share proportion"
    ):
        errors.append(f"{filename}: coefficient scale and units must remain explicit")
    if "global OLS selected" not in str(actual.get("model_status", "")):
        errors.append(f"{filename}: map must warn that the local model was not selected")
    if "not supported" not in str(actual.get("causal_interpretation", "")):
        errors.append(f"{filename}: map must reject causal interpretation")
    features = actual.get("features")
    if not isinstance(features, list) or len(features) != 144:
        errors.append(f"{filename}: map must contain exactly 144 lattice polygons")
    else:
        unstable_count = 0
        for feature in features:
            properties = feature.get("properties", {})
            required = {
                "coefficient_units",
                "coefficient_scale",
                "bandwidth_m",
                "effective_sample_size",
                "condition_number",
                "fdr_method",
                "q_value",
                "fdr_significant",
                "stable",
                "warning",
            }
            if uncertainty:
                required.update(
                    {
                        "standard_error",
                        "t_value",
                        "p_value_normal_approximation",
                    }
                )
            if not required.issubset(properties):
                errors.append(
                    f"{filename}: every feature needs scale, uncertainty, FDR, "
                    "support, and warning fields"
                )
                break
            if properties["stable"] is False:
                unstable_count += 1
                if not properties["warning"]:
                    errors.append(
                        f"{filename}: unstable features need an explicit warning"
                    )
                    break
        if unstable_count == 0:
            errors.append(f"{filename}: at least one low-support region must be flagged")
    if actual != expected:
        errors.append(f"{filename} differs from the reference map")


def validate(input_path: Path, output_dir: Path) -> list[str]:
    """Validate the complete GAB-39 artifact contract."""
    errors: list[str] = []
    try:
        fixture = oracle.load_fixture(input_path)
        expected = oracle.build_outputs(fixture)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [f"input fixture is invalid: {exc}"]

    actual = {
        filename: read_json(output_dir / filename, errors)
        for filename in expected
    }
    validate_model_comparison(
        actual["model-comparison.json"],
        expected["model-comparison.json"],
        errors,
    )
    validate_spatial_validation(
        actual["spatial-validation.json"],
        expected["spatial-validation.json"],
        errors,
    )
    validate_collinearity(
        actual["collinearity-extrapolation.json"],
        expected["collinearity-extrapolation.json"],
        errors,
    )
    validate_map(
        actual["local-coefficients.geojson"],
        expected["local-coefficients.geojson"],
        "local-coefficients.geojson",
        False,
        errors,
    )
    validate_map(
        actual["coefficient-uncertainty.geojson"],
        expected["coefficient-uncertainty.geojson"],
        "coefficient-uncertainty.geojson",
        True,
        errors,
    )
    if actual["provenance.json"] != expected["provenance.json"]:
        errors.append("provenance.json must preserve weights, inference, and split rules")
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
    print("gab-39-spatial-regression artifacts: pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
