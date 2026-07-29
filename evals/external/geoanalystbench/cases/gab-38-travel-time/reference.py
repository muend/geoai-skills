"""Independent reference solution for external case GAB-38."""

from __future__ import annotations

import argparse
import csv
import heapq
import itertools
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

State = tuple[str | None, str]


def load_network(path: Path) -> dict[str, Any]:
    """Load and validate the synthetic directed network."""
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if payload.get("directed") is not True:
        raise ValueError("network must declare directed=true")
    if payload.get("crs") != "EPSG:32636":
        raise ValueError("network must use the projected EPSG:32636 CRS")

    nodes = payload.get("nodes")
    edges = payload.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        raise ValueError("nodes and edges must be arrays")

    node_ids = [node.get("id") for node in nodes if isinstance(node, dict)]
    if len(node_ids) != len(nodes) or len(set(node_ids)) != len(node_ids):
        raise ValueError("node identifiers must be present and unique")
    known_nodes = set(node_ids)

    for edge in edges:
        if not isinstance(edge, dict):
            raise ValueError("every edge must be an object")
        if edge.get("from") not in known_nodes or edge.get("to") not in known_nodes:
            raise ValueError("every edge endpoint must reference a known node")
        cost = edge.get("time_minutes")
        if not isinstance(cost, (int, float)) or not math.isfinite(cost) or cost <= 0:
            raise ValueError("every time_minutes value must be positive and finite")

    origin = payload.get("origin")
    destinations = payload.get("destinations")
    if origin not in known_nodes:
        raise ValueError("origin must reference a known node")
    if not isinstance(destinations, list) or not destinations:
        raise ValueError("destinations must be a non-empty array")
    if any(destination not in known_nodes for destination in destinations):
        raise ValueError("every destination must reference a known node")
    return payload


def shortest_paths(network: dict[str, Any]) -> dict[str, tuple[float, list[str]] | None]:
    """Compute state-aware shortest paths while enforcing forbidden turns."""
    adjacency: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for edge in network["edges"]:
        adjacency[edge["from"]].append(edge)
    for edges in adjacency.values():
        edges.sort(key=lambda item: (item["to"], item["time_minutes"]))

    forbidden = {
        tuple(turn["via"])
        for turn in network.get("forbidden_turns", [])
        if isinstance(turn, dict) and isinstance(turn.get("via"), list)
    }
    origin = str(network["origin"])
    initial: State = (None, origin)
    best: dict[State, float] = {initial: 0.0}
    parent: dict[State, State] = {}
    queue: list[tuple[float, int, State]] = []
    sequence = itertools.count()
    heapq.heappush(queue, (0.0, next(sequence), initial))

    while queue:
        current_cost, _, state = heapq.heappop(queue)
        if current_cost != best.get(state):
            continue
        previous, current = state
        for edge in adjacency.get(current, []):
            target = str(edge["to"])
            if previous is not None and (previous, current, target) in forbidden:
                continue
            next_state: State = (current, target)
            next_cost = current_cost + float(edge["time_minutes"])
            if next_cost >= best.get(next_state, math.inf):
                continue
            best[next_state] = next_cost
            parent[next_state] = state
            heapq.heappush(queue, (next_cost, next(sequence), next_state))

    results: dict[str, tuple[float, list[str]] | None] = {}
    for destination in network["destinations"]:
        candidates = [
            (cost, state)
            for state, cost in best.items()
            if state[1] == destination
        ]
        if not candidates:
            results[destination] = None
            continue
        cost, terminal = min(candidates, key=lambda item: (item[0], item[1][0] or ""))
        path = [terminal[1]]
        cursor = terminal
        while cursor != initial:
            cursor = parent[cursor]
            path.append(cursor[1])
        path.reverse()
        results[destination] = (cost, path)
    return results


def write_outputs(
    network: dict[str, Any],
    results: dict[str, tuple[float, list[str]] | None],
    output_dir: Path,
) -> None:
    """Write deterministic CSV, GeoJSON, and summary artifacts."""
    output_dir.mkdir(parents=True, exist_ok=True)
    coordinates = {
        node["id"]: [float(node["x"]), float(node["y"])]
        for node in network["nodes"]
    }

    csv_path = output_dir / "travel-times.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "destination_id",
                "reachable",
                "travel_time_minutes",
                "path",
            ],
            lineterminator="\n",
        )
        writer.writeheader()
        for destination in network["destinations"]:
            result = results[destination]
            writer.writerow(
                {
                    "destination_id": destination,
                    "reachable": str(result is not None).lower(),
                    "travel_time_minutes": "" if result is None else f"{result[0]:.3f}",
                    "path": "" if result is None else ">".join(result[1]),
                }
            )

    features = []
    for destination in network["destinations"]:
        result = results[destination]
        if result is None:
            continue
        cost, path = result
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "destination_id": destination,
                    "travel_time_minutes": cost,
                    "path": path,
                },
                "geometry": {
                    "type": "LineString",
                    "coordinates": [coordinates[node_id] for node_id in path],
                },
            }
        )
    routes = {
        "type": "FeatureCollection",
        "crs": {
            "type": "name",
            "properties": {"name": network["crs"]},
        },
        "features": features,
    }
    (output_dir / "routes.geojson").write_text(
        json.dumps(routes, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    reachable_count = sum(result is not None for result in results.values())
    summary = {
        "schema_version": 1,
        "origin": network["origin"],
        "destination_count": len(network["destinations"]),
        "reachable_count": reachable_count,
        "unreachable_count": len(network["destinations"]) - reachable_count,
        "directed": network["directed"],
        "crs": network["crs"],
        "cost_field": network["cost_field"],
        "cost_units": network["cost_units"],
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
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
    network = load_network(args.input)
    results = shortest_paths(network)
    write_outputs(network, results, args.output_dir)
    print(f"reference outputs: {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
