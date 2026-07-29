"""Generate the deterministic synthetic spatial-regression fixture for GAB-39."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


ORIGIN_X = 450000.0
ORIGIN_Y = 4420000.0
GRID_SIZE = 12
CELL_SIZE_M = 1000.0


def build_observations() -> list[dict[str, Any]]:
    """Build 144 lattice polygons with known coefficient and error structure."""
    observations: list[dict[str, Any]] = []
    for row in range(GRID_SIZE):
        for column in range(GRID_SIZE):
            green_share = 0.12 + 0.045 * row + 0.015 * (column % 3)
            income_index = 0.25 + 0.04 * column + 0.015 * ((row * 2 + column) % 4)
            green_proxy = green_share * 0.985 + 0.002 * ((row + column) % 5)
            true_green_coefficient = -3.0 - 4.0 * column / (GRID_SIZE - 1)
            smooth_spatial_error = 0.62 * math.sin((row + column) / 3.0)
            deterministic_noise = (((row * 7 + column * 11) % 17) - 8) * 0.025
            target = (
                32.0
                + true_green_coefficient * green_share
                + 1.8 * income_index
                + smooth_spatial_error
                + deterministic_noise
            )
            min_x = ORIGIN_X + column * CELL_SIZE_M
            min_y = ORIGIN_Y + row * CELL_SIZE_M
            observations.append(
                {
                    "area_id": f"A{row * GRID_SIZE + column + 1:03d}",
                    "row": row,
                    "column": column,
                    "bbox": [
                        min_x,
                        min_y,
                        min_x + CELL_SIZE_M,
                        min_y + CELL_SIZE_M,
                    ],
                    "centroid_x": min_x + CELL_SIZE_M / 2.0,
                    "centroid_y": min_y + CELL_SIZE_M / 2.0,
                    "green_share": round(green_share, 6),
                    "income_index": round(income_index, 6),
                    "green_share_proxy": round(green_proxy, 6),
                    "target_temperature_c": round(target, 6),
                    "true_green_coefficient_c_per_share": round(
                        true_green_coefficient,
                        6,
                    ),
                }
            )
    return observations


def build_fixture() -> dict[str, Any]:
    """Build the complete independent regression fixture."""
    return {
        "schema_version": 1,
        "crs": "EPSG:32636",
        "coordinate_units": "metres",
        "target": {
            "field": "target_temperature_c",
            "units": "degrees Celsius",
        },
        "predictors": [
            {
                "field": "green_share",
                "units": "proportion from 0 to 1",
                "role": "varying coefficient",
            },
            {
                "field": "income_index",
                "units": "unitless index from 0 to 1",
                "role": "global control",
            },
        ],
        "nuisance_feature": {
            "field": "green_share_proxy",
            "units": "proportion from 0 to 1",
            "expected_issue": "collinear with green_share",
        },
        "lattice": {
            "origin_x": ORIGIN_X,
            "origin_y": ORIGIN_Y,
            "rows": GRID_SIZE,
            "columns": GRID_SIZE,
            "cell_size_m": CELL_SIZE_M,
        },
        "weights": {
            "primary": "queen",
            "sensitivity": "rook",
            "transform": "row-standardized",
            "islands_expected": 0,
        },
        "inference": {
            "permutations": 999,
            "seed": 39,
            "fdr_method": "Benjamini-Hochberg",
            "fdr_alpha": 0.05,
        },
        "local_model": {
            "name": "Gaussian local weighted regression",
            "bandwidth_m": 4500.0,
            "minimum_effective_sample_size": 80.0,
        },
        "validation": {
            "method": "four-fold spatial block cross-validation",
            "block_rows": 6,
            "block_columns": 6,
            "metric": "RMSE degrees Celsius",
        },
        "decision_gate": {
            "ols_residual_moran_p_max": 0.05,
            "local_block_rmse_improvement_min": 0.10,
            "vif_exclusion_threshold": 10.0,
        },
        "observations": build_observations(),
    }


def write_fixture(output_dir: Path) -> Path:
    """Write a byte-stable fixture and return its path."""
    output_dir.mkdir(parents=True, exist_ok=True)
    fixture_path = output_dir / "spatial-regression.json"
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
