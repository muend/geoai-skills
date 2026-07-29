"""Independent reference solution for external case GAB-36."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any

Grid = list[list[float | bool | int | None]]


def load_scenes(path: Path) -> dict[str, Any]:
    """Load and validate comparable synthetic reflectance scenes."""
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if payload.get("product_level") != "surface_reflectance":
        raise ValueError("both scenes must declare surface_reflectance")
    if payload.get("phenology") != "matched":
        raise ValueError("bi-temporal analysis requires matched phenology")
    if payload.get("crs") != "EPSG:32636":
        raise ValueError("projected EPSG:32636 CRS is required")

    grid = payload.get("grid")
    if not isinstance(grid, dict):
        raise ValueError("grid metadata must be an object")
    rows = grid.get("rows")
    columns = grid.get("columns")
    if not isinstance(rows, int) or not isinstance(columns, int) or rows <= 0 or columns <= 0:
        raise ValueError("grid rows and columns must be positive integers")
    for field in ("pixel_width_m", "pixel_height_m"):
        value = grid.get(field)
        if not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ValueError(f"{field} must be positive and finite")

    for scene_name in ("pre", "post"):
        scene = payload.get(scene_name)
        if not isinstance(scene, dict):
            raise ValueError(f"{scene_name} scene must be an object")
        for band_name in ("red_dn", "nir_dn", "valid_mask"):
            band = scene.get(band_name)
            if not isinstance(band, list) or len(band) != rows:
                raise ValueError(f"{scene_name}.{band_name} has incorrect rows")
            if any(not isinstance(row, list) or len(row) != columns for row in band):
                raise ValueError(f"{scene_name}.{band_name} has incorrect columns")

    scale = payload.get("reflectance_scale_factor")
    savi_l = payload.get("savi_l")
    if not isinstance(scale, (int, float)) or scale <= 0:
        raise ValueError("reflectance_scale_factor must be positive")
    if not isinstance(savi_l, (int, float)) or savi_l < 0:
        raise ValueError("savi_l must be non-negative")
    thresholds = payload.get("sensitivity_thresholds")
    if not isinstance(thresholds, list) or payload.get("damage_threshold") not in thresholds:
        raise ValueError("sensitivity thresholds must include the damage threshold")
    return payload


def savi(red_dn: int, nir_dn: int, scale: float, soil_factor: float) -> float:
    """Compute SAVI from scaled red and NIR surface reflectance."""
    red = red_dn * scale
    nir = nir_dn * scale
    denominator = nir + red + soil_factor
    if denominator == 0:
        raise ValueError("SAVI denominator cannot be zero")
    return ((nir - red) / denominator) * (1.0 + soil_factor)


def calculate_change(
    scenes: dict[str, Any],
) -> tuple[Grid, Grid, Grid, Grid, Grid]:
    """Return pre, post, delta, valid-overlap, and damage grids."""
    rows = int(scenes["grid"]["rows"])
    columns = int(scenes["grid"]["columns"])
    scale = float(scenes["reflectance_scale_factor"])
    soil_factor = float(scenes["savi_l"])
    threshold = float(scenes["damage_threshold"])
    pre_grid: Grid = []
    post_grid: Grid = []
    delta_grid: Grid = []
    valid_grid: Grid = []
    damage_grid: Grid = []

    for row_index in range(rows):
        pre_row: list[float | None] = []
        post_row: list[float | None] = []
        delta_row: list[float | None] = []
        valid_row: list[bool] = []
        damage_row: list[bool | None] = []
        for column_index in range(columns):
            valid = bool(
                scenes["pre"]["valid_mask"][row_index][column_index]
                and scenes["post"]["valid_mask"][row_index][column_index]
            )
            valid_row.append(valid)
            if not valid:
                pre_row.append(None)
                post_row.append(None)
                delta_row.append(None)
                damage_row.append(None)
                continue
            pre_value = savi(
                int(scenes["pre"]["red_dn"][row_index][column_index]),
                int(scenes["pre"]["nir_dn"][row_index][column_index]),
                scale,
                soil_factor,
            )
            post_value = savi(
                int(scenes["post"]["red_dn"][row_index][column_index]),
                int(scenes["post"]["nir_dn"][row_index][column_index]),
                scale,
                soil_factor,
            )
            delta = post_value - pre_value
            pre_row.append(round(pre_value, 9))
            post_row.append(round(post_value, 9))
            delta_row.append(round(delta, 9))
            damage_row.append(delta <= threshold)
        pre_grid.append(pre_row)
        post_grid.append(post_row)
        delta_grid.append(delta_row)
        valid_grid.append(valid_row)
        damage_grid.append(damage_row)
    return pre_grid, post_grid, delta_grid, valid_grid, damage_grid


def pixel_polygon(grid: dict[str, Any], row: int, column: int) -> list[list[float]]:
    """Return the projected polygon ring for one raster cell."""
    width = float(grid["pixel_width_m"])
    height = float(grid["pixel_height_m"])
    left = float(grid["origin_x"]) + column * width
    top = float(grid["origin_y"]) - row * height
    right = left + width
    bottom = top - height
    return [
        [left, top],
        [right, top],
        [right, bottom],
        [left, bottom],
        [left, top],
    ]


def write_outputs(
    scenes: dict[str, Any],
    grids: tuple[Grid, Grid, Grid, Grid, Grid],
    output_dir: Path,
) -> None:
    """Write deterministic change grids, polygons, summary, and provenance."""
    output_dir.mkdir(parents=True, exist_ok=True)
    pre_grid, post_grid, delta_grid, valid_grid, damage_grid = grids
    change_payload = {
        "schema_version": 1,
        "crs": scenes["crs"],
        "rows": scenes["grid"]["rows"],
        "columns": scenes["grid"]["columns"],
        "pre_savi": pre_grid,
        "post_savi": post_grid,
        "delta_savi": delta_grid,
        "valid_overlap": valid_grid,
        "damage_mask": damage_grid,
    }
    (output_dir / "savi-change.json").write_text(
        json.dumps(change_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    pixel_area_m2 = (
        float(scenes["grid"]["pixel_width_m"])
        * float(scenes["grid"]["pixel_height_m"])
    )
    features = []
    for row_index, row in enumerate(damage_grid):
        for column_index, damaged in enumerate(row):
            if damaged is not True:
                continue
            features.append(
                {
                    "type": "Feature",
                    "properties": {
                        "row": row_index,
                        "column": column_index,
                        "delta_savi": delta_grid[row_index][column_index],
                        "pixel_area_m2": pixel_area_m2,
                    },
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [
                            pixel_polygon(scenes["grid"], row_index, column_index)
                        ],
                    },
                }
            )
    damage_features = {
        "type": "FeatureCollection",
        "crs": {"type": "name", "properties": {"name": scenes["crs"]}},
        "features": features,
    }
    (output_dir / "damage-pixels.geojson").write_text(
        json.dumps(damage_features, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    valid_deltas = [
        float(value)
        for row in delta_grid
        for value in row
        if isinstance(value, (int, float))
    ]
    valid_pixels = len(valid_deltas)
    total_pixels = int(scenes["grid"]["rows"]) * int(scenes["grid"]["columns"])
    with (output_dir / "change-summary.csv").open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "threshold",
                "damaged_pixels",
                "damaged_area_hectares",
                "valid_pixels",
                "valid_overlap_percent",
            ],
            lineterminator="\n",
        )
        writer.writeheader()
        for threshold in scenes["sensitivity_thresholds"]:
            damaged_pixels = sum(value <= float(threshold) for value in valid_deltas)
            writer.writerow(
                {
                    "threshold": f"{float(threshold):.3f}",
                    "damaged_pixels": damaged_pixels,
                    "damaged_area_hectares": f"{damaged_pixels * pixel_area_m2 / 10000:.4f}",
                    "valid_pixels": valid_pixels,
                    "valid_overlap_percent": f"{valid_pixels / total_pixels * 100:.1f}",
                }
            )

    provenance = {
        "schema_version": 1,
        "sensor": scenes["sensor"],
        "product_level": scenes["product_level"],
        "pre_acquired": scenes["pre_acquired"],
        "post_acquired": scenes["post_acquired"],
        "phenology": scenes["phenology"],
        "co_registration_rmse_pixels": scenes["co_registration_rmse_pixels"],
        "crs": scenes["crs"],
        "pixel_width_m": scenes["grid"]["pixel_width_m"],
        "pixel_height_m": scenes["grid"]["pixel_height_m"],
        "reflectance_scale_factor": scenes["reflectance_scale_factor"],
        "savi_l": scenes["savi_l"],
        "damage_threshold": scenes["damage_threshold"],
        "valid_pixels": valid_pixels,
        "total_pixels": total_pixels,
        "valid_overlap_percent": valid_pixels / total_pixels * 100,
    }
    (output_dir / "provenance.json").write_text(
        json.dumps(provenance, indent=2, sort_keys=True) + "\n",
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
    """Execute the independent reference solution."""
    args = parse_args()
    scenes = load_scenes(args.input)
    grids = calculate_change(scenes)
    write_outputs(scenes, grids, args.output_dir)
    print(f"reference outputs: {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
