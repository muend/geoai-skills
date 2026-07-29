"""Generate the deterministic synthetic facility-coverage fixture for GAB-08."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


NETWORK: dict[str, Any] = {
    "schema_version": 1,
    "crs": "EPSG:32636",
    "coordinate_units": "metres",
    "mode": "driving",
    "cost_field": "time_minutes",
    "cost_units": "minutes",
    "coverage_cutoff_minutes": 5.0,
    "directed": False,
    "nodes": [
        {"id": "A", "x": 450000.0, "y": 4420000.0},
        {"id": "B", "x": 450100.0, "y": 4420000.0},
        {"id": "C", "x": 450200.0, "y": 4420000.0},
        {"id": "D", "x": 450100.0, "y": 4420100.0},
        {"id": "E", "x": 450300.0, "y": 4420000.0},
        {"id": "F", "x": 450400.0, "y": 4420000.0},
        {"id": "G", "x": 450500.0, "y": 4420000.0},
        {"id": "H", "x": 450020.0, "y": 4420020.0},
        {"id": "I", "x": 451000.0, "y": 4421000.0},
    ],
    "edges": [
        {"from": "A", "to": "B", "distance_m": 100.0, "time_minutes": 2.0},
        {"from": "A", "to": "D", "distance_m": 141.4, "time_minutes": 4.0},
        {"from": "A", "to": "H", "distance_m": 28.3, "time_minutes": 8.0},
        {"from": "B", "to": "C", "distance_m": 100.0, "time_minutes": 2.0},
        {"from": "C", "to": "E", "distance_m": 100.0, "time_minutes": 2.0},
        {"from": "D", "to": "E", "distance_m": 223.6, "time_minutes": 4.0},
        {"from": "E", "to": "F", "distance_m": 100.0, "time_minutes": 3.0},
        {"from": "F", "to": "G", "distance_m": 100.0, "time_minutes": 3.0},
    ],
    "facilities": [
        {"facility_id": "F1", "node_id": "A"},
        {"facility_id": "F2", "node_id": "E"},
    ],
    "demands": [
        {"demand_id": "D1", "node_id": "B", "population": 100},
        {"demand_id": "D2", "node_id": "C", "population": 200},
        {"demand_id": "D3", "node_id": "D", "population": 150},
        {"demand_id": "D4", "node_id": "F", "population": 120},
        {"demand_id": "D5", "node_id": "G", "population": 80},
        {"demand_id": "D6", "node_id": "H", "population": 90},
        {"demand_id": "D7", "node_id": "I", "population": 60},
    ],
}


def write_fixture(output_dir: Path) -> Path:
    """Write a byte-stable network fixture and return its path."""
    output_dir.mkdir(parents=True, exist_ok=True)
    fixture_path = output_dir / "coverage-network.json"
    fixture_path.write_text(
        json.dumps(NETWORK, indent=2, sort_keys=True) + "\n",
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
