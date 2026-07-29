"""Generate the deterministic synthetic network for external case GAB-38."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


NETWORK: dict[str, Any] = {
    "schema_version": 1,
    "crs": "EPSG:32636",
    "coordinate_units": "metres",
    "cost_field": "time_minutes",
    "cost_units": "minutes",
    "directed": True,
    "origin": "A",
    "destinations": ["B", "C", "D", "E", "F", "G"],
    "nodes": [
        {"id": "A", "x": 450000.0, "y": 4420000.0},
        {"id": "B", "x": 450100.0, "y": 4420000.0},
        {"id": "C", "x": 450200.0, "y": 4420000.0},
        {"id": "D", "x": 450100.0, "y": 4420100.0},
        {"id": "E", "x": 450200.0, "y": 4420100.0},
        {"id": "F", "x": 450300.0, "y": 4420000.0},
        {"id": "G", "x": 451000.0, "y": 4421000.0},
    ],
    "edges": [
        {"from": "A", "to": "B", "distance_m": 100.0, "time_minutes": 2.0},
        {"from": "A", "to": "D", "distance_m": 141.4, "time_minutes": 3.0},
        {"from": "B", "to": "C", "distance_m": 100.0, "time_minutes": 2.0},
        {"from": "B", "to": "E", "distance_m": 141.4, "time_minutes": 1.0},
        {"from": "C", "to": "F", "distance_m": 100.0, "time_minutes": 2.0},
        {"from": "D", "to": "A", "distance_m": 141.4, "time_minutes": 10.0},
        {"from": "D", "to": "E", "distance_m": 100.0, "time_minutes": 2.0},
        {"from": "E", "to": "C", "distance_m": 141.4, "time_minutes": 2.0},
        {"from": "E", "to": "D", "distance_m": 100.0, "time_minutes": 1.0},
    ],
    "forbidden_turns": [
        {"via": ["A", "B", "E"]},
    ],
}


def write_fixture(output_dir: Path) -> Path:
    """Write a byte-stable network fixture and return its path."""
    output_dir.mkdir(parents=True, exist_ok=True)
    fixture_path = output_dir / "network.json"
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
