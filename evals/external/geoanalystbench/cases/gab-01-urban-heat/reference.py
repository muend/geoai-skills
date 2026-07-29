"""Independent reference solution for external case GAB-01."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any


Number = int | float
Point = dict[str, Any]


def load_fixture(path: Path) -> dict[str, Any]:
    """Load and validate the synthetic urban-heat fixture."""
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if payload.get("crs") != "EPSG:32636":
        raise ValueError("urban-heat fixture must use projected EPSG:32636")
    if payload.get("coordinate_units") != "metres":
        raise ValueError("urban-heat coordinates must use metres")
    if payload.get("temperature_units") != "degrees Celsius":
        raise ValueError("temperature units must be degrees Celsius")

    points = payload.get("temperature_points")
    zones = payload.get("census_zones")
    if not isinstance(points, list) or len(points) != 36:
        raise ValueError("fixture must contain exactly 36 temperature points")
    if not isinstance(zones, list) or len(zones) != 12:
        raise ValueError("fixture must contain exactly 12 census zones")

    coordinates: set[tuple[float, float]] = set()
    station_ids: set[str] = set()
    for point in points:
        if not isinstance(point, dict):
            raise ValueError("every temperature point must be an object")
        station_id = point.get("station_id")
        coordinate = (float(point["x"]), float(point["y"]))
        temperature = float(point["temperature_c"])
        if not isinstance(station_id, str) or not station_id:
            raise ValueError("every temperature point needs a station_id")
        if station_id in station_ids or coordinate in coordinates:
            raise ValueError("station identifiers and coordinates must be unique")
        if not all(math.isfinite(value) for value in (*coordinate, temperature)):
            raise ValueError("point coordinates and temperatures must be finite")
        station_ids.add(station_id)
        coordinates.add(coordinate)

    census_ids: set[str] = set()
    for zone in zones:
        if not isinstance(zone, dict):
            raise ValueError("every census zone must be an object")
        census_id = zone.get("census_id")
        bbox = zone.get("bbox")
        total = zone.get("total_population")
        elderly = zone.get("elderly_population")
        if not isinstance(census_id, str) or census_id in census_ids:
            raise ValueError("census identifiers must be present and unique")
        if (
            not isinstance(bbox, list)
            or len(bbox) != 4
            or not all(isinstance(value, (int, float)) for value in bbox)
            or float(bbox[0]) >= float(bbox[2])
            or float(bbox[1]) >= float(bbox[3])
        ):
            raise ValueError("every census zone needs a valid projected bbox")
        if (
            not isinstance(total, int)
            or not isinstance(elderly, int)
            or total <= 0
            or elderly < 0
            or elderly > total
        ):
            raise ValueError("census populations must satisfy 0 <= elderly <= total")
        census_ids.add(census_id)

    variogram = payload.get("variogram", {})
    if variogram.get("model") != "exponential":
        raise ValueError("reference contract requires an exponential variogram")
    for field in ("nugget", "partial_sill", "range_m", "max_lag_m"):
        value = variogram.get(field)
        if not isinstance(value, (int, float)) or float(value) <= 0:
            raise ValueError(f"variogram {field} must be positive")
    return payload


def distance(first: Point, second: Point) -> float:
    """Return Euclidean distance in the fixture's projected metre units."""
    return math.hypot(
        float(first["x"]) - float(second["x"]),
        float(first["y"]) - float(second["y"]),
    )


def modeled_semivariance(distance_m: float, variogram: dict[str, Any]) -> float:
    """Return exponential-model semivariance at one distance."""
    if distance_m == 0:
        return 0.0
    nugget = float(variogram["nugget"])
    partial_sill = float(variogram["partial_sill"])
    range_m = float(variogram["range_m"])
    return nugget + partial_sill * (1.0 - math.exp(-distance_m / range_m))


def solve_linear_system(matrix: list[list[float]], vector: list[float]) -> list[float]:
    """Solve a dense linear system with partial-pivot Gaussian elimination."""
    size = len(vector)
    augmented = [row[:] + [vector[index]] for index, row in enumerate(matrix)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(augmented[row][column]))
        if abs(augmented[pivot][column]) < 1e-12:
            raise ValueError("kriging system is singular")
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


def ordinary_kriging(
    points: list[Point],
    x: float,
    y: float,
    variogram: dict[str, Any],
) -> tuple[float, float]:
    """Return ordinary-kriging prediction and standard deviation."""
    target = {"x": x, "y": y}
    count = len(points)
    matrix = [[0.0 for _ in range(count + 1)] for _ in range(count + 1)]
    vector = [0.0 for _ in range(count + 1)]
    for row, first in enumerate(points):
        for column, second in enumerate(points):
            matrix[row][column] = modeled_semivariance(
                distance(first, second),
                variogram,
            )
        matrix[row][count] = 1.0
        matrix[count][row] = 1.0
        vector[row] = modeled_semivariance(distance(first, target), variogram)
    vector[count] = 1.0
    solution = solve_linear_system(matrix, vector)
    weights = solution[:count]
    lagrange = solution[count]
    prediction = sum(
        weight * float(point["temperature_c"])
        for weight, point in zip(weights, points, strict=True)
    )
    variance = sum(
        weight * vector[index] for index, weight in enumerate(weights)
    ) + lagrange
    return prediction, math.sqrt(max(variance, 0.0))


def empirical_variogram(
    points: list[Point],
    variogram: dict[str, Any],
) -> list[dict[str, Number]]:
    """Calculate deterministic classical empirical-semivariance bins."""
    edges = [float(value) for value in variogram["bin_edges_m"]]
    bins: list[list[tuple[float, float]]] = [[] for _ in range(len(edges) - 1)]
    for first_index, first in enumerate(points):
        for second in points[first_index + 1 :]:
            lag = distance(first, second)
            if lag > float(variogram["max_lag_m"]):
                continue
            semivariance = 0.5 * (
                float(first["temperature_c"]) - float(second["temperature_c"])
            ) ** 2
            for index, (lower, upper) in enumerate(zip(edges, edges[1:], strict=True)):
                if lower < lag <= upper:
                    bins[index].append((lag, semivariance))
                    break
    diagnostics: list[dict[str, Number]] = []
    for index, pairs in enumerate(bins):
        diagnostics.append(
            {
                "bin_index": index + 1,
                "lower_m": edges[index],
                "upper_m": edges[index + 1],
                "pair_count": len(pairs),
                "mean_lag_m": (
                    round(sum(pair[0] for pair in pairs) / len(pairs), 6)
                    if pairs
                    else 0.0
                ),
                "semivariance": (
                    round(sum(pair[1] for pair in pairs) / len(pairs), 6)
                    if pairs
                    else 0.0
                ),
            }
        )
    return diagnostics


def validation_block(point: Point, validation: dict[str, Any]) -> str:
    """Assign one observation to one of four deterministic spatial blocks."""
    east = float(point["x"]) >= float(validation["block_split_x"])
    north = float(point["y"]) >= float(validation["block_split_y"])
    return f"{'N' if north else 'S'}{'E' if east else 'W'}"


def error_metrics(errors: list[float]) -> dict[str, Number]:
    """Return mean error and RMSE for a non-empty error vector."""
    return {
        "count": len(errors),
        "mean_error_c": round(sum(errors) / len(errors), 6),
        "rmse_c": round(
            math.sqrt(sum(error**2 for error in errors) / len(errors)),
            6,
        ),
    }


def spatial_block_validation(
    points: list[Point],
    variogram: dict[str, Any],
    validation: dict[str, Any],
) -> dict[str, Any]:
    """Run four-fold spatial block validation and a training-mean baseline."""
    folds = sorted({validation_block(point, validation) for point in points})
    all_errors: list[float] = []
    baseline_errors: list[float] = []
    fold_results = []
    for fold in folds:
        training = [
            point for point in points if validation_block(point, validation) != fold
        ]
        testing = [
            point for point in points if validation_block(point, validation) == fold
        ]
        training_mean = sum(float(point["temperature_c"]) for point in training) / len(
            training
        )
        fold_errors = []
        for point in testing:
            prediction, _ = ordinary_kriging(
                training,
                float(point["x"]),
                float(point["y"]),
                variogram,
            )
            observed = float(point["temperature_c"])
            fold_errors.append(prediction - observed)
            baseline_errors.append(training_mean - observed)
        all_errors.extend(fold_errors)
        fold_results.append({"fold": fold, **error_metrics(fold_errors)})
    return {
        "folds": fold_results,
        "aggregate": error_metrics(all_errors),
        "training_mean_baseline": error_metrics(baseline_errors),
    }


def interpolate_surfaces(fixture: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Interpolate temperature and uncertainty to the declared regular grid."""
    domain = fixture["domain"]
    grid = fixture["prediction_grid"]
    cell_size = float(grid["cell_size_m"])
    width = int(grid["width"])
    height = int(grid["height"])
    temperature_rows: list[list[float]] = []
    uncertainty_rows: list[list[float]] = []
    for row in range(height):
        temperature_row = []
        uncertainty_row = []
        y = float(domain["origin_y"]) + (row + 0.5) * cell_size
        for column in range(width):
            x = float(domain["origin_x"]) + (column + 0.5) * cell_size
            prediction, uncertainty = ordinary_kriging(
                fixture["temperature_points"],
                x,
                y,
                fixture["variogram"],
            )
            temperature_row.append(round(prediction, 6))
            uncertainty_row.append(round(uncertainty, 6))
        temperature_rows.append(temperature_row)
        uncertainty_rows.append(uncertainty_row)

    common = {
        "schema_version": 1,
        "crs": fixture["crs"],
        "origin_x": domain["origin_x"],
        "origin_y": domain["origin_y"],
        "cell_size_m": cell_size,
        "width": width,
        "height": height,
        "row_order": "south-to-north",
    }
    temperature = {
        **common,
        "variable": "ordinary_kriging_temperature_mean",
        "units": "degrees Celsius",
        "values": temperature_rows,
    }
    uncertainty = {
        **common,
        "variable": "ordinary_kriging_standard_deviation",
        "units": "degrees Celsius",
        "values": uncertainty_rows,
    }
    return temperature, uncertainty


def summarize_zones(
    fixture: dict[str, Any],
    temperature: dict[str, Any],
    uncertainty: dict[str, Any],
) -> list[dict[str, Any]]:
    """Summarize surfaces and vulnerability for all census zones."""
    origin_x = float(temperature["origin_x"])
    origin_y = float(temperature["origin_y"])
    cell_size = float(temperature["cell_size_m"])
    risk = fixture["risk_rule"]
    rows = []
    for zone in fixture["census_zones"]:
        min_x, min_y, max_x, max_y = (float(value) for value in zone["bbox"])
        temperatures = []
        uncertainties = []
        for grid_row in range(int(temperature["height"])):
            y = origin_y + (grid_row + 0.5) * cell_size
            for grid_column in range(int(temperature["width"])):
                x = origin_x + (grid_column + 0.5) * cell_size
                if min_x <= x < max_x and min_y <= y < max_y:
                    temperatures.append(
                        float(temperature["values"][grid_row][grid_column])
                    )
                    uncertainties.append(
                        float(uncertainty["values"][grid_row][grid_column])
                    )
        mean_temperature = sum(temperatures) / len(temperatures)
        mean_uncertainty = sum(uncertainties) / len(uncertainties)
        elderly_rate = float(zone["elderly_population"]) / float(
            zone["total_population"]
        )
        candidate = (
            mean_temperature >= float(risk["temperature_threshold_c"])
            and elderly_rate >= float(risk["elderly_rate_threshold"])
        )
        if candidate and mean_uncertainty <= float(risk["max_mean_uncertainty_c"]):
            status = "selected"
        elif candidate:
            status = "uncertainty_excluded"
        else:
            status = "not_selected"
        rows.append(
            {
                "census_id": zone["census_id"],
                "total_population": zone["total_population"],
                "elderly_population": zone["elderly_population"],
                "elderly_rate": round(elderly_rate, 6),
                "mean_temperature_c": round(mean_temperature, 6),
                "mean_uncertainty_c": round(mean_uncertainty, 6),
                "selection_status": status,
            }
        )
    return rows


def validation_report(fixture: dict[str, Any]) -> dict[str, Any]:
    """Build variogram and spatial-block validation evidence."""
    empirical = empirical_variogram(
        fixture["temperature_points"],
        fixture["variogram"],
    )
    return {
        "schema_version": 1,
        "validation_method": fixture["validation"]["method"],
        "random_only_validation": False,
        "empirical_variogram": empirical,
        "variogram_model": {
            key: fixture["variogram"][key]
            for key in ("model", "nugget", "partial_sill", "range_m", "max_lag_m")
        },
        "spatial_block_cv": spatial_block_validation(
            fixture["temperature_points"],
            fixture["variogram"],
            fixture["validation"],
        ),
        "diagnostics": {
            "duplicate_coordinate_count": 0,
            "nonempty_variogram_bins": sum(
                int(bin_result["pair_count"]) > 0 for bin_result in empirical
            ),
            "minimum_nonempty_bin_pair_count": min(
                int(bin_result["pair_count"])
                for bin_result in empirical
                if int(bin_result["pair_count"]) > 0
            ),
            "uncertainty_surface_delivered": True,
        },
    }


def provenance(fixture: dict[str, Any]) -> dict[str, Any]:
    """Build machine-readable processing and decision provenance."""
    return {
        "schema_version": 1,
        "case_id": "gab-01-urban-heat",
        "fixture": "fixtures/urban-heat.json",
        "crs": fixture["crs"],
        "coordinate_units": fixture["coordinate_units"],
        "method": "ordinary kriging",
        "variogram": fixture["variogram"],
        "prediction_grid": fixture["prediction_grid"],
        "validation": fixture["validation"],
        "risk_rule": fixture["risk_rule"],
        "map": {
            "format": "SVG",
            "temperature_classification": "manual fixed breaks",
            "temperature_breaks_c": [29.0, 30.0, 31.0, 32.0],
            "palette": "colorblind-safe sequential orange",
            "uncertainty_exclusion_symbol": "purple dashed outline",
        },
        "implementation": {
            "origin": "independently-authored",
            "runtime": "Python standard library",
            "randomness": "none",
        },
    }


def temperature_color(value: float) -> str:
    """Return one accessible sequential color for a fixed temperature class."""
    breaks = [29.0, 30.0, 31.0, 32.0]
    colors = ["#fff5eb", "#fee6ce", "#fdae6b", "#e6550d", "#7f2704"]
    index = sum(value >= threshold for threshold in breaks)
    return colors[index]


def render_svg(fixture: dict[str, Any], summaries: list[dict[str, Any]]) -> str:
    """Render a deterministic accessible census-zone heat-risk map."""
    domain = fixture["domain"]
    summary_by_id = {row["census_id"]: row for row in summaries}
    elements = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 850 560" '
        'role="img" aria-labelledby="map-title map-desc">',
        '<title id="map-title">Urban heat and uncertainty-screened vulnerability</title>',
        '<desc id="map-desc">Twelve census zones colored by mean temperature in '
        "degrees Celsius. Solid black outlines mark selected high-risk zones and "
        "purple dashed outlines mark candidates excluded for high uncertainty.</desc>",
        "<metadata>CRS EPSG:32636; manual fixed temperature classes; NoData none</metadata>",
        '<rect width="850" height="560" fill="#ffffff"/>',
        '<text x="40" y="22" font-family="sans-serif" font-size="16" '
        'font-weight="bold">Urban heat and vulnerability screening</text>',
    ]
    origin_x = float(domain["origin_x"])
    origin_y = float(domain["origin_y"])
    height = float(domain["height_m"])
    for zone in fixture["census_zones"]:
        summary = summary_by_id[zone["census_id"]]
        min_x, min_y, max_x, max_y = (float(value) for value in zone["bbox"])
        x = 40.0 + (min_x - origin_x)
        y = 40.0 + height - (max_y - origin_y)
        status = summary["selection_status"]
        stroke = "#252525"
        width = "1"
        dash = ""
        if status == "selected":
            stroke = "#000000"
            width = "4"
        elif status == "uncertainty_excluded":
            stroke = "#6a3d9a"
            width = "4"
            dash = ' stroke-dasharray="8 5"'
        elements.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{max_x - min_x:.1f}" '
            f'height="{max_y - min_y:.1f}" '
            f'fill="{temperature_color(float(summary["mean_temperature_c"]))}" '
            f'stroke="{stroke}" stroke-width="{width}"{dash} '
            f'data-census-id="{zone["census_id"]}" '
            f'data-selection-status="{status}" '
            f'data-temperature-c="{summary["mean_temperature_c"]:.6f}" '
            f'data-uncertainty-c="{summary["mean_uncertainty_c"]:.6f}"/>'
        )
        elements.append(
            f'<text x="{x + 8:.1f}" y="{y + 20:.1f}" '
            f'font-family="sans-serif" font-size="12">{zone["census_id"]}</text>'
        )

    legend = [
        ("&lt; 29", "#fff5eb"),
        ("29–&lt;30", "#fee6ce"),
        ("30–&lt;31", "#fdae6b"),
        ("31–&lt;32", "#e6550d"),
        ("≥ 32", "#7f2704"),
    ]
    elements.extend(
        [
            '<text x="680" y="55" font-family="sans-serif" font-size="14" '
            'font-weight="bold">Mean temperature (°C)</text>',
        ]
    )
    for index, (label, color) in enumerate(legend):
        y = 75 + index * 30
        elements.append(
            f'<rect x="680" y="{y}" width="24" height="20" fill="{color}" '
            'stroke="#252525" stroke-width="1"/>'
        )
        elements.append(
            f'<text x="714" y="{y + 15}" font-family="sans-serif" '
            f'font-size="12">{label}</text>'
        )
    elements.extend(
        [
            '<line x1="680" y1="250" x2="720" y2="250" stroke="#000000" '
            'stroke-width="4"/>',
            '<text x="730" y="255" font-family="sans-serif" font-size="12">'
            "Selected high risk</text>",
            '<line x1="680" y1="285" x2="720" y2="285" stroke="#6a3d9a" '
            'stroke-width="4" stroke-dasharray="8 5"/>',
            '<text x="730" y="290" font-family="sans-serif" font-size="12">'
            "Excluded: uncertainty</text>",
            '<text x="40" y="520" font-family="sans-serif" font-size="11">'
            "Projection: EPSG:32636 | Grid: 50 m | Temperature units: °C</text>",
            '<text x="40" y="540" font-family="sans-serif" font-size="11">'
            "Risk requires heat + elderly-rate thresholds and uncertainty ≤ ceiling</text>",
            "</svg>",
        ]
    )
    return "\n".join(elements) + "\n"


def write_outputs(fixture: dict[str, Any], output_dir: Path) -> None:
    """Write deterministic surface, summary, map, validation, and provenance files."""
    output_dir.mkdir(parents=True, exist_ok=True)
    temperature, uncertainty = interpolate_surfaces(fixture)
    summaries = summarize_zones(fixture, temperature, uncertainty)
    json_outputs = {
        "temperature-surface.json": temperature,
        "uncertainty-surface.json": uncertainty,
        "validation-report.json": validation_report(fixture),
        "provenance.json": provenance(fixture),
    }
    for filename, payload in json_outputs.items():
        (output_dir / filename).write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )

    with (output_dir / "census-summary.csv").open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:
        fieldnames = [
            "census_id",
            "total_population",
            "elderly_population",
            "elderly_rate",
            "mean_temperature_c",
            "mean_uncertainty_c",
            "selection_status",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in summaries:
            writer.writerow(
                {
                    **row,
                    "elderly_rate": f"{row['elderly_rate']:.6f}",
                    "mean_temperature_c": f"{row['mean_temperature_c']:.6f}",
                    "mean_uncertainty_c": f"{row['mean_uncertainty_c']:.6f}",
                }
            )
    (output_dir / "urban-heat-map.svg").write_text(
        render_svg(fixture, summaries),
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
