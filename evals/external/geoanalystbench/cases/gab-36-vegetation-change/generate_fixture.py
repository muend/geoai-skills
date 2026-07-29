"""Generate deterministic synthetic surface-reflectance scenes for GAB-36."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

PRE_RED = 2000
PRE_NIR = 6000
POST_VALUES = {
    "H": (3000, 3000),
    "M": (2500, 4500),
    "B": (2400, 4800),
    "L": (2200, 5200),
    "S": (2000, 6000),
    "X": (3000, 3000),
}
CELL_CODES = [
    ["H", "H", "H", "M", "M"],
    ["M", "M", "B", "B", "L"],
    ["L", "S", "S", "S", "S"],
    ["S", "S", "X", "X", "S"],
]


def grid_for_band(index: int) -> list[list[int]]:
    """Return the deterministic post-event DN grid for red or NIR."""
    return [
        [POST_VALUES[code][index] for code in row]
        for row in CELL_CODES
    ]


SCENES: dict[str, Any] = {
    "schema_version": 1,
    "sensor": "SYNTHETIC-S2-L2A-LIKE",
    "product_level": "surface_reflectance",
    "pre_acquired": "2025-06-10",
    "post_acquired": "2025-06-20",
    "phenology": "matched",
    "co_registration_rmse_pixels": 0.1,
    "crs": "EPSG:32636",
    "grid": {
        "rows": 4,
        "columns": 5,
        "origin_x": 500000.0,
        "origin_y": 4420040.0,
        "pixel_width_m": 10.0,
        "pixel_height_m": 10.0,
    },
    "reflectance_scale_factor": 0.0001,
    "savi_l": 0.5,
    "damage_threshold": -0.2,
    "sensitivity_thresholds": [-0.15, -0.2, -0.25],
    "pre": {
        "red_dn": [[PRE_RED] * 5 for _ in range(4)],
        "nir_dn": [[PRE_NIR] * 5 for _ in range(4)],
        "valid_mask": [
            [True, True, True, True, True],
            [True, True, True, True, True],
            [True, True, True, True, True],
            [True, True, False, True, True],
        ],
    },
    "post": {
        "red_dn": grid_for_band(0),
        "nir_dn": grid_for_band(1),
        "valid_mask": [
            [True, True, True, True, True],
            [True, True, True, True, True],
            [True, True, True, True, True],
            [True, True, True, False, True],
        ],
    },
}


def write_fixture(output_dir: Path) -> Path:
    """Write a byte-stable scene fixture and return its path."""
    output_dir.mkdir(parents=True, exist_ok=True)
    fixture_path = output_dir / "hailstorm-scenes.json"
    fixture_path.write_text(
        json.dumps(SCENES, indent=2, sort_keys=True) + "\n",
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
    args = parse_args()
    fixture_path = write_fixture(args.output_dir)
    print(f"generated: {fixture_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
