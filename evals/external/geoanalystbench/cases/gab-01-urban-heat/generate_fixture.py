"""Generate the deterministic synthetic urban-heat fixture for GAB-01."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


ORIGIN_X = 450000.0
ORIGIN_Y = 4420000.0
POINT_X_OFFSETS = [40.0, 112.0, 184.0, 256.0, 328.0, 400.0]
POINT_Y_OFFSETS = [30.0, 84.0, 138.0, 192.0, 246.0, 300.0]
NOISE = [
    [-0.18, 0.06, 0.12, -0.08, 0.16, -0.04],
    [0.10, -0.12, 0.04, 0.18, -0.06, 0.08],
    [-0.02, 0.14, -0.16, 0.06, 0.10, -0.08],
    [0.16, -0.04, 0.08, -0.14, 0.02, 0.12],
    [-0.10, 0.18, -0.06, 0.04, -0.12, 0.14],
    [0.08, -0.14, 0.16, -0.02, 0.06, -0.10],
]
POPULATIONS = [
    (1000, 120),
    (800, 120),
    (700, 140),
    (400, 140),
    (1200, 180),
    (900, 180),
    (600, 180),
    (300, 120),
    (1100, 220),
    (700, 210),
    (500, 175),
    (200, 100),
]


def temperature_field(x_offset: float, y_offset: float, noise: float) -> float:
    """Return a smooth deterministic temperature field plus bounded noise."""
    hotspot_distance_sq = (x_offset - 260.0) ** 2 + (y_offset - 180.0) ** 2
    hotspot = 1.15 * math.exp(-hotspot_distance_sq / (2.0 * 145.0**2))
    temperature = 27.9 + 0.0065 * x_offset + 0.0045 * y_offset + hotspot + noise
    return round(temperature, 3)


def build_points() -> list[dict[str, Any]]:
    """Build 36 projected temperature observations."""
    points: list[dict[str, Any]] = []
    for row, y_offset in enumerate(POINT_Y_OFFSETS):
        for column, x_offset in enumerate(POINT_X_OFFSETS):
            points.append(
                {
                    "station_id": f"T{row * 6 + column + 1:02d}",
                    "x": ORIGIN_X + x_offset,
                    "y": ORIGIN_Y + y_offset,
                    "temperature_c": temperature_field(
                        x_offset,
                        y_offset,
                        NOISE[row][column],
                    ),
                }
            )
    return points


def build_census_zones() -> list[dict[str, Any]]:
    """Build twelve 150-by-150-metre census zones."""
    zones: list[dict[str, Any]] = []
    for row in range(3):
        for column in range(4):
            index = row * 4 + column
            total_population, elderly_population = POPULATIONS[index]
            min_x = ORIGIN_X + column * 150.0
            min_y = ORIGIN_Y + row * 150.0
            zones.append(
                {
                    "census_id": f"C{index + 1:02d}",
                    "bbox": [min_x, min_y, min_x + 150.0, min_y + 150.0],
                    "total_population": total_population,
                    "elderly_population": elderly_population,
                }
            )
    return zones


def build_fixture() -> dict[str, Any]:
    """Build the complete independent fixture."""
    return {
        "schema_version": 1,
        "crs": "EPSG:32636",
        "coordinate_units": "metres",
        "temperature_units": "degrees Celsius",
        "domain": {
            "origin_x": ORIGIN_X,
            "origin_y": ORIGIN_Y,
            "width_m": 600.0,
            "height_m": 450.0,
        },
        "prediction_grid": {
            "cell_size_m": 50.0,
            "width": 12,
            "height": 9,
        },
        "variogram": {
            "estimator": "classical semivariance",
            "model": "exponential",
            "nugget": 0.05,
            "partial_sill": 3.0,
            "range_m": 220.0,
            "max_lag_m": 360.0,
            "bin_edges_m": [0.0, 90.0, 150.0, 220.0, 290.0, 360.0],
        },
        "validation": {
            "method": "four-fold spatial block cross-validation",
            "block_split_x": ORIGIN_X + 220.0,
            "block_split_y": ORIGIN_Y + 165.0,
        },
        "risk_rule": {
            "temperature_threshold_c": 31.0,
            "elderly_rate_threshold": 0.30,
            "max_mean_uncertainty_c": 1.15,
        },
        "temperature_points": build_points(),
        "census_zones": build_census_zones(),
    }


def write_fixture(output_dir: Path) -> Path:
    """Write a byte-stable fixture and return its path."""
    output_dir.mkdir(parents=True, exist_ok=True)
    fixture_path = output_dir / "urban-heat.json"
    fixture_path.write_text(
        json.dumps(build_fixture(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return fixture_path


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    """Generate the fixture."""
    fixture_path = write_fixture(parse_args().output_dir)
    print(f"generated: {fixture_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
