"""Independent reference solution for external case GAB-39."""

from __future__ import annotations

import argparse
import json
import math
import random
from pathlib import Path
from typing import Any


Record = dict[str, Any]


def load_fixture(path: Path) -> dict[str, Any]:
    """Load and validate the synthetic spatial-regression fixture."""
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if payload.get("crs") != "EPSG:32636":
        raise ValueError("spatial-regression fixture must use EPSG:32636")
    if payload.get("coordinate_units") != "metres":
        raise ValueError("spatial-regression coordinates must use metres")
    observations = payload.get("observations")
    if not isinstance(observations, list) or len(observations) != 144:
        raise ValueError("fixture must contain exactly 144 lattice observations")
    area_ids: set[str] = set()
    cells: set[tuple[int, int]] = set()
    for observation in observations:
        if not isinstance(observation, dict):
            raise ValueError("every observation must be an object")
        area_id = observation.get("area_id")
        cell = (int(observation["row"]), int(observation["column"]))
        if (
            not isinstance(area_id, str)
            or area_id in area_ids
            or cell in cells
            or not 0 <= cell[0] < 12
            or not 0 <= cell[1] < 12
        ):
            raise ValueError("area identifiers and 12-by-12 cells must be unique")
        values = [
            observation["centroid_x"],
            observation["centroid_y"],
            observation["green_share"],
            observation["income_index"],
            observation["green_share_proxy"],
            observation["target_temperature_c"],
        ]
        if not all(isinstance(value, (int, float)) and math.isfinite(value) for value in values):
            raise ValueError("all model coordinates and values must be finite")
        area_ids.add(area_id)
        cells.add(cell)
    if payload.get("weights", {}).get("transform") != "row-standardized":
        raise ValueError("weights must be row-standardized")
    if payload.get("inference", {}).get("permutations") != 999:
        raise ValueError("Moran inference must use exactly 999 permutations")
    return payload


def solve_linear_system(matrix: list[list[float]], vector: list[float]) -> list[float]:
    """Solve a dense linear system with partial-pivot elimination."""
    size = len(vector)
    augmented = [row[:] + [vector[index]] for index, row in enumerate(matrix)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(augmented[row][column]))
        if abs(augmented[pivot][column]) < 1e-12:
            raise ValueError("regression design is singular")
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        pivot_value = augmented[column][column]
        for item in range(column, size + 1):
            augmented[column][item] /= pivot_value
        for row in range(size):
            if row == column:
                continue
            factor = augmented[row][column]
            if factor == 0:
                continue
            for item in range(column, size + 1):
                augmented[row][item] -= factor * augmented[column][item]
    return [augmented[row][size] for row in range(size)]


def inverse_matrix(matrix: list[list[float]]) -> list[list[float]]:
    """Return a dense matrix inverse."""
    size = len(matrix)
    columns = []
    for column in range(size):
        unit = [1.0 if row == column else 0.0 for row in range(size)]
        columns.append(solve_linear_system(matrix, unit))
    return [[columns[column][row] for column in range(size)] for row in range(size)]


def matrix_one_norm(matrix: list[list[float]]) -> float:
    """Return the maximum absolute column sum."""
    return max(
        sum(abs(matrix[row][column]) for row in range(len(matrix)))
        for column in range(len(matrix[0]))
    )


def design_row(record: Record, predictors: list[str]) -> list[float]:
    """Return an intercept-plus-predictor row."""
    return [1.0, *(float(record[field]) for field in predictors)]


def fit_weighted_regression(
    records: list[Record],
    predictors: list[str],
    weights: list[float] | None = None,
) -> dict[str, Any]:
    """Fit weighted least squares and return coefficients and diagnostics."""
    if weights is None:
        weights = [1.0] * len(records)
    if len(weights) != len(records) or any(weight <= 0 for weight in weights):
        raise ValueError("regression weights must be positive and aligned")
    design = [design_row(record, predictors) for record in records]
    target = [float(record["target_temperature_c"]) for record in records]
    parameter_count = len(predictors) + 1
    normal = [
        [
            sum(
                weights[index] * row[left] * row[right]
                for index, row in enumerate(design)
            )
            for right in range(parameter_count)
        ]
        for left in range(parameter_count)
    ]
    rhs = [
        sum(
            weights[index] * row[column] * target[index]
            for index, row in enumerate(design)
        )
        for column in range(parameter_count)
    ]
    coefficients = solve_linear_system(normal, rhs)
    predictions = [
        sum(value * coefficient for value, coefficient in zip(row, coefficients, strict=True))
        for row in design
    ]
    residuals = [
        observed - predicted
        for observed, predicted in zip(target, predictions, strict=True)
    ]
    weighted_sse = sum(
        weight * residual**2 for weight, residual in zip(weights, residuals, strict=True)
    )
    degrees_of_freedom = max(sum(weights) - parameter_count, 1.0)
    sigma_squared = weighted_sse / degrees_of_freedom
    inverse = inverse_matrix(normal)
    covariance = [
        [sigma_squared * value for value in row]
        for row in inverse
    ]
    standard_errors = [
        math.sqrt(max(covariance[index][index], 0.0))
        for index in range(parameter_count)
    ]
    condition_number = matrix_one_norm(normal) * matrix_one_norm(inverse)
    return {
        "coefficients": coefficients,
        "standard_errors": standard_errors,
        "predictions": predictions,
        "residuals": residuals,
        "sigma_squared": sigma_squared,
        "condition_number": condition_number,
    }


def correlation(first: list[float], second: list[float]) -> float:
    """Return Pearson correlation for two equally sized vectors."""
    first_mean = sum(first) / len(first)
    second_mean = sum(second) / len(second)
    numerator = sum(
        (left - first_mean) * (right - second_mean)
        for left, right in zip(first, second, strict=True)
    )
    first_scale = math.sqrt(sum((value - first_mean) ** 2 for value in first))
    second_scale = math.sqrt(sum((value - second_mean) ** 2 for value in second))
    return numerator / (first_scale * second_scale)


def variance_inflation_factors(
    records: list[Record],
    fields: list[str],
) -> dict[str, float]:
    """Return VIF values from the inverse predictor-correlation matrix."""
    columns = [[float(record[field]) for record in records] for field in fields]
    correlation_matrix = [
        [correlation(left, right) for right in columns]
        for left in columns
    ]
    inverse = inverse_matrix(correlation_matrix)
    return {
        field: round(inverse[index][index], 6)
        for index, field in enumerate(fields)
    }


def neighbors(records: list[Record], kind: str) -> list[list[int]]:
    """Build rook or queen lattice neighbor indices."""
    lookup = {
        (int(record["row"]), int(record["column"])): index
        for index, record in enumerate(records)
    }
    offsets = [(-1, 0), (1, 0), (0, -1), (0, 1)]
    if kind == "queen":
        offsets.extend([(-1, -1), (-1, 1), (1, -1), (1, 1)])
    result = []
    for record in records:
        row = int(record["row"])
        column = int(record["column"])
        result.append(
            sorted(
                lookup[(row + row_offset, column + column_offset)]
                for row_offset, column_offset in offsets
                if (row + row_offset, column + column_offset) in lookup
            )
        )
    return result


def moran_statistic(values: list[float], adjacency: list[list[int]]) -> float:
    """Return Moran's I for row-standardized neighbor weights."""
    mean = sum(values) / len(values)
    centered = [value - mean for value in values]
    denominator = sum(value**2 for value in centered)
    numerator = 0.0
    for index, linked in enumerate(adjacency):
        if linked:
            numerator += centered[index] * (
                sum(centered[neighbor] for neighbor in linked) / len(linked)
            )
    return numerator / denominator


def moran_permutation(
    values: list[float],
    records: list[Record],
    kind: str,
    permutations: int,
    seed: int,
) -> dict[str, Any]:
    """Return deterministic permutation inference for Moran's I."""
    adjacency = neighbors(records, kind)
    observed = moran_statistic(values, adjacency)
    expected = -1.0 / (len(values) - 1)
    # Deterministic benchmark permutations are intentionally non-cryptographic.
    randomizer = random.Random(seed)  # noqa: S311
    exceedances = 0
    shuffled = values[:]
    for _ in range(permutations):
        randomizer.shuffle(shuffled)
        candidate = moran_statistic(shuffled, adjacency)
        if abs(candidate - expected) >= abs(observed - expected):
            exceedances += 1
    return {
        "weights": kind,
        "transform": "row-standardized",
        "islands": sum(not linked for linked in adjacency),
        "moran_i": round(observed, 6),
        "expected_i": round(expected, 6),
        "permutations": permutations,
        "seed": seed,
        "p_value_permutation_two_sided": round(
            (exceedances + 1) / (permutations + 1),
            6,
        ),
    }


def prediction_error_metrics(errors: list[float]) -> dict[str, Any]:
    """Return regression validation metrics."""
    mean_error = sum(errors) / len(errors)
    return {
        "count": len(errors),
        "mean_error_c": round(mean_error, 6),
        "mae_c": round(sum(abs(error) for error in errors) / len(errors), 6),
        "rmse_c": round(
            math.sqrt(sum(error**2 for error in errors) / len(errors)),
            6,
        ),
    }


def block_id(record: Record) -> str:
    """Assign one lattice polygon to one of four coherent spatial blocks."""
    north = int(record["row"]) >= 6
    east = int(record["column"]) >= 6
    return f"{'N' if north else 'S'}{'E' if east else 'W'}"


def local_weights(records: list[Record], target: Record, bandwidth_m: float) -> list[float]:
    """Return Gaussian geographic weights around one target centroid."""
    weights = []
    for record in records:
        distance_m = math.hypot(
            float(record["centroid_x"]) - float(target["centroid_x"]),
            float(record["centroid_y"]) - float(target["centroid_y"]),
        )
        weights.append(math.exp(-0.5 * (distance_m / bandwidth_m) ** 2))
    return weights


def local_fit(
    records: list[Record],
    target: Record,
    predictors: list[str],
    bandwidth_m: float,
) -> dict[str, Any]:
    """Fit one Gaussian local weighted regression at a target location."""
    weights = local_weights(records, target, bandwidth_m)
    model = fit_weighted_regression(records, predictors, weights)
    normalized = [weight / sum(weights) for weight in weights]
    effective_sample_size = 1.0 / sum(weight**2 for weight in normalized)
    target_row = design_row(target, predictors)
    prediction = sum(
        value * coefficient
        for value, coefficient in zip(
            target_row,
            model["coefficients"],
            strict=True,
        )
    )
    return {
        **model,
        "prediction": prediction,
        "effective_sample_size": effective_sample_size,
    }


def spatial_block_validation(
    records: list[Record],
    predictors: list[str],
    bandwidth_m: float,
) -> dict[str, Any]:
    """Compare global and local models over four spatial block folds."""
    global_errors: list[float] = []
    local_errors: list[float] = []
    folds = []
    for fold in ("NE", "NW", "SE", "SW"):
        training = [record for record in records if block_id(record) != fold]
        testing = [record for record in records if block_id(record) == fold]
        global_model = fit_weighted_regression(training, predictors)
        fold_global_errors = []
        fold_local_errors = []
        for target in testing:
            observed = float(target["target_temperature_c"])
            global_prediction = sum(
                value * coefficient
                for value, coefficient in zip(
                    design_row(target, predictors),
                    global_model["coefficients"],
                    strict=True,
                )
            )
            local_prediction = float(
                local_fit(training, target, predictors, bandwidth_m)["prediction"]
            )
            fold_global_errors.append(global_prediction - observed)
            fold_local_errors.append(local_prediction - observed)
        global_errors.extend(fold_global_errors)
        local_errors.extend(fold_local_errors)
        folds.append(
            {
                "fold": fold,
                "test_block_count": 1,
                "test_observation_count": len(testing),
                "train_observation_count": len(training),
                "global_ols": prediction_error_metrics(fold_global_errors),
                "local_weighted": prediction_error_metrics(fold_local_errors),
            }
        )
    global_metrics = prediction_error_metrics(global_errors)
    local_metrics = prediction_error_metrics(local_errors)
    improvement = (
        float(global_metrics["rmse_c"]) - float(local_metrics["rmse_c"])
    ) / float(global_metrics["rmse_c"])
    return {
        "method": "four-fold spatial block cross-validation",
        "assignment_unit": "contiguous 6-by-6 lattice block",
        "random_only_validation": False,
        "leakage_audit": {
            "same_area_in_train_and_test": False,
            "preprocessing_fit_scope": "training fold only",
            "test_blocks": ["NE", "NW", "SE", "SW"],
        },
        "folds": folds,
        "aggregate": {
            "global_ols": global_metrics,
            "local_weighted": local_metrics,
            "local_rmse_improvement_fraction": round(improvement, 6),
        },
    }


def benjamini_hochberg(p_values: list[float]) -> list[float]:
    """Return Benjamini-Hochberg adjusted q-values."""
    count = len(p_values)
    ordered = sorted(enumerate(p_values), key=lambda item: item[1])
    adjusted = [1.0] * count
    running = 1.0
    for reverse_rank, (index, value) in enumerate(reversed(ordered), start=1):
        rank = count - reverse_rank + 1
        running = min(running, value * count / rank)
        adjusted[index] = min(running, 1.0)
    return adjusted


def polygon_geometry(record: Record) -> dict[str, Any]:
    """Return one bbox polygon in projected coordinates."""
    min_x, min_y, max_x, max_y = (float(value) for value in record["bbox"])
    return {
        "type": "Polygon",
        "coordinates": [
            [
                [min_x, min_y],
                [max_x, min_y],
                [max_x, max_y],
                [min_x, max_y],
                [min_x, min_y],
            ]
        ],
    }


def local_results(
    fixture: dict[str, Any],
    predictors: list[str],
) -> list[dict[str, Any]]:
    """Fit local models and attach uncertainty and FDR evidence."""
    records = fixture["observations"]
    bandwidth = float(fixture["local_model"]["bandwidth_m"])
    minimum_effective = float(
        fixture["local_model"]["minimum_effective_sample_size"]
    )
    results = []
    p_values = []
    for record in records:
        model = local_fit(records, record, predictors, bandwidth)
        coefficient = float(model["coefficients"][1])
        standard_error = float(model["standard_errors"][1])
        t_value = coefficient / standard_error
        p_value = math.erfc(abs(t_value) / math.sqrt(2.0))
        result = {
            "record": record,
            "coefficient": coefficient,
            "standard_error": standard_error,
            "t_value": t_value,
            "p_value": p_value,
            "prediction": float(model["prediction"]),
            "effective_sample_size": float(model["effective_sample_size"]),
            "condition_number": float(model["condition_number"]),
        }
        results.append(result)
        p_values.append(p_value)
    q_values = benjamini_hochberg(p_values)
    for result, q_value in zip(results, q_values, strict=True):
        result["q_value"] = q_value
        result["fdr_significant"] = q_value <= float(
            fixture["inference"]["fdr_alpha"]
        )
        result["stable"] = (
            result["effective_sample_size"] >= minimum_effective
            and result["condition_number"] <= 100000.0
        )
    return results


def local_geojsons(
    fixture: dict[str, Any],
    results: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build coefficient and uncertainty GeoJSON map artifacts."""
    coefficient_features = []
    uncertainty_features = []
    bandwidth = float(fixture["local_model"]["bandwidth_m"])
    for result in results:
        record = result["record"]
        warning = (
            "unstable local estimate: inspect effective sample size and condition number"
            if not result["stable"]
            else ""
        )
        common = {
            "area_id": record["area_id"],
            "predictor": "green_share",
            "coefficient_scale": "local Gaussian weighted regression",
            "coefficient_units": "degrees Celsius per unit green-share proportion",
            "bandwidth_m": bandwidth,
            "effective_sample_size": round(result["effective_sample_size"], 6),
            "condition_number": round(result["condition_number"], 6),
            "fdr_method": "Benjamini-Hochberg",
            "q_value": round(result["q_value"], 6),
            "fdr_significant": result["fdr_significant"],
            "stable": result["stable"],
            "warning": warning,
        }
        coefficient_features.append(
            {
                "type": "Feature",
                "properties": {
                    **common,
                    "coefficient": round(result["coefficient"], 6),
                },
                "geometry": polygon_geometry(record),
            }
        )
        uncertainty_features.append(
            {
                "type": "Feature",
                "properties": {
                    **common,
                    "standard_error": round(result["standard_error"], 6),
                    "t_value": round(result["t_value"], 6),
                    "p_value_normal_approximation": round(result["p_value"], 6),
                },
                "geometry": polygon_geometry(record),
            }
        )
    shared = {
        "type": "FeatureCollection",
        "crs": "EPSG:32636",
        "coordinate_units": "metres",
        "coefficient_units": "degrees Celsius per unit green-share proportion",
        "model_status": (
            "exploratory candidate; global OLS selected by spatial block validation"
        ),
        "causal_interpretation": "not supported; exploratory association only",
    }
    return (
        {
            **shared,
            "map": "local green-share coefficient",
            "features": coefficient_features,
        },
        {
            **shared,
            "map": "local green-share coefficient uncertainty",
            "features": uncertainty_features,
        },
    )


def build_outputs(fixture: dict[str, Any]) -> dict[str, Any]:
    """Calculate every expected GAB-39 artifact in memory."""
    records = fixture["observations"]
    predictors = ["green_share", "income_index"]
    nuisance = "green_share_proxy"
    vif = variance_inflation_factors(records, [*predictors, nuisance])
    global_model = fit_weighted_regression(records, predictors)
    target = [float(record["target_temperature_c"]) for record in records]
    target_mean = sum(target) / len(target)
    total_sum_squares = sum((value - target_mean) ** 2 for value in target)
    residual_sum_squares = sum(
        residual**2 for residual in global_model["residuals"]
    )
    queen_ols = moran_permutation(
        global_model["residuals"],
        records,
        "queen",
        int(fixture["inference"]["permutations"]),
        int(fixture["inference"]["seed"]),
    )
    rook_ols = moran_permutation(
        global_model["residuals"],
        records,
        "rook",
        int(fixture["inference"]["permutations"]),
        int(fixture["inference"]["seed"]) + 1,
    )
    validation = spatial_block_validation(
        records,
        predictors,
        float(fixture["local_model"]["bandwidth_m"]),
    )
    local = local_results(fixture, predictors)
    local_residuals = [
        float(result["record"]["target_temperature_c"]) - result["prediction"]
        for result in local
    ]
    queen_local = moran_permutation(
        local_residuals,
        records,
        "queen",
        int(fixture["inference"]["permutations"]),
        int(fixture["inference"]["seed"]) + 2,
    )
    rook_local = moran_permutation(
        local_residuals,
        records,
        "rook",
        int(fixture["inference"]["permutations"]),
        int(fixture["inference"]["seed"]) + 3,
    )
    gate = fixture["decision_gate"]
    moran_gate = (
        float(queen_ols["p_value_permutation_two_sided"])
        <= float(gate["ols_residual_moran_p_max"])
    )
    improvement_gate = (
        float(validation["aggregate"]["local_rmse_improvement_fraction"])
        >= float(gate["local_block_rmse_improvement_min"])
    )
    selected_model = (
        "Gaussian local weighted regression"
        if moran_gate and improvement_gate
        else "global OLS"
    )
    coefficient_map, uncertainty_map = local_geojsons(fixture, local)
    unstable_ids = [
        result["record"]["area_id"] for result in local if not result["stable"]
    ]
    model_comparison = {
        "schema_version": 1,
        "analysis_units": "144 regular 1-km square polygons",
        "target": "target_temperature_c",
        "target_units": "degrees Celsius",
        "global_ols": {
            "fit_order": 1,
            "predictors": predictors,
            "excluded_predictor": nuisance,
            "coefficients": {
                name: round(value, 6)
                for name, value in zip(
                    ["intercept", *predictors],
                    global_model["coefficients"],
                    strict=True,
                )
            },
            "standard_errors": {
                name: round(value, 6)
                for name, value in zip(
                    ["intercept", *predictors],
                    global_model["standard_errors"],
                    strict=True,
                )
            },
            "r_squared": round(1.0 - residual_sum_squares / total_sum_squares, 6),
            "residual_moran_primary": queen_ols,
            "residual_moran_sensitivity": rook_ols,
        },
        "local_model": {
            "name": fixture["local_model"]["name"],
            "predictors": predictors,
            "bandwidth_m": fixture["local_model"]["bandwidth_m"],
            "green_coefficient_min": round(
                min(result["coefficient"] for result in local),
                6,
            ),
            "green_coefficient_max": round(
                max(result["coefficient"] for result in local),
                6,
            ),
            "residual_moran_primary": queen_local,
            "residual_moran_sensitivity": rook_local,
        },
        "decision": {
            "selected_model": selected_model,
            "ols_fitted_before_local_model": True,
            "ols_residual_dependence_gate_passed": moran_gate,
            "blocked_rmse_improvement_gate_passed": improvement_gate,
            "decision_rule": (
                "select local only when OLS residual Moran p <= 0.05 and "
                "blocked RMSE improvement >= 0.10"
            ),
            "prompt_named_model_forced": False,
            "causal_claim_allowed": False,
            "interpretation": "exploratory spatial association, not causation",
        },
    }
    collinearity = {
        "schema_version": 1,
        "vif_threshold": fixture["decision_gate"]["vif_exclusion_threshold"],
        "vif": vif,
        "excluded_features": [nuisance],
        "final_predictors": predictors,
        "local_fit_support": {
            "minimum_effective_sample_size_required": fixture["local_model"][
                "minimum_effective_sample_size"
            ],
            "observed_effective_sample_size_min": round(
                min(result["effective_sample_size"] for result in local),
                6,
            ),
            "observed_effective_sample_size_max": round(
                max(result["effective_sample_size"] for result in local),
                6,
            ),
            "condition_number_max_allowed": 100000.0,
            "observed_condition_number_min": round(
                min(result["condition_number"] for result in local),
                6,
            ),
            "observed_condition_number_max": round(
                max(result["condition_number"] for result in local),
                6,
            ),
            "unstable_area_ids": unstable_ids,
            "warning": (
                "Coefficient maps must retain unstable-region warnings and "
                "must not be interpreted causally."
            ),
        },
    }
    provenance = {
        "schema_version": 1,
        "case_id": "gab-39-spatial-regression",
        "fixture": "fixtures/spatial-regression.json",
        "crs": fixture["crs"],
        "coordinate_units": fixture["coordinate_units"],
        "weights": fixture["weights"],
        "inference": fixture["inference"],
        "local_model": fixture["local_model"],
        "validation": fixture["validation"],
        "decision_gate": fixture["decision_gate"],
        "implementation": {
            "origin": "independently-authored",
            "runtime": "Python standard library",
            "randomness": "seeded Moran permutations only",
        },
    }
    return {
        "model-comparison.json": model_comparison,
        "spatial-validation.json": {
            "schema_version": 1,
            **validation,
        },
        "local-coefficients.geojson": coefficient_map,
        "coefficient-uncertainty.geojson": uncertainty_map,
        "collinearity-extrapolation.json": collinearity,
        "provenance.json": provenance,
    }


def write_outputs(fixture: dict[str, Any], output_dir: Path) -> None:
    """Write deterministic regression, validation, map, and provenance artifacts."""
    output_dir.mkdir(parents=True, exist_ok=True)
    for filename, payload in build_outputs(fixture).items():
        (output_dir / filename).write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    """Run the independent reference workflow."""
    args = parse_args()
    write_outputs(load_fixture(args.input), args.output_dir)
    print(f"wrote: {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
