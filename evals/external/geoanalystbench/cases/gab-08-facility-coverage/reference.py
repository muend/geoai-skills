"""Independent reference solution for external case GAB-08."""

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


def load_network(path: Path) -> dict[str, Any]:
    """Load and validate the synthetic facility-coverage network."""
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if payload.get("crs") != "EPSG:32636":
        raise ValueError("network must use the projected EPSG:32636 CRS")
    if payload.get("mode") != "driving":
        raise ValueError("network mode must be driving")
    if payload.get("directed") is not False:
        raise ValueError("network must explicitly declare directed=false")
    cutoff = payload.get("coverage_cutoff_minutes")
    if not isinstance(cutoff, (int, float)) or not math.isfinite(cutoff) or cutoff <= 0:
        raise ValueError("coverage cutoff must be positive and finite")

    nodes = payload.get("nodes")
    edges = payload.get("edges")
    facilities = payload.get("facilities")
    demands = payload.get("demands")
    if not all(isinstance(value, list) for value in (nodes, edges, facilities, demands)):
        raise ValueError("nodes, edges, facilities, and demands must be arrays")

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

    facility_ids = [
        facility.get("facility_id")
        for facility in facilities
        if isinstance(facility, dict)
    ]
    if len(facility_ids) != len(facilities) or len(set(facility_ids)) != len(
        facility_ids
    ):
        raise ValueError("facility identifiers must be present and unique")
    if any(facility.get("node_id") not in known_nodes for facility in facilities):
        raise ValueError("every facility must reference a known node")

    demand_ids = [
        demand.get("demand_id") for demand in demands if isinstance(demand, dict)
    ]
    if len(demand_ids) != len(demands) or len(set(demand_ids)) != len(demand_ids):
        raise ValueError("demand identifiers must be present and unique")
    for demand in demands:
        if demand.get("node_id") not in known_nodes:
            raise ValueError("every demand must reference a known node")
        population = demand.get("population")
        if not isinstance(population, int) or population < 0:
            raise ValueError("every demand population must be a non-negative integer")
    return payload


def shortest_paths(
    network: dict[str, Any],
    source: str,
) -> tuple[dict[str, float], dict[str, str]]:
    """Return least travel times and predecessors from one network node."""
    adjacency: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for edge in network["edges"]:
        start = str(edge["from"])
        end = str(edge["to"])
        cost = float(edge["time_minutes"])
        adjacency[start].append((end, cost))
        adjacency[end].append((start, cost))
    for neighbors in adjacency.values():
        neighbors.sort()

    distances = {source: 0.0}
    predecessor: dict[str, str] = {}
    sequence = itertools.count()
    queue = [(0.0, next(sequence), source)]
    while queue:
        current_cost, _, current = heapq.heappop(queue)
        if current_cost != distances.get(current):
            continue
        for target, edge_cost in adjacency.get(current, []):
            next_cost = current_cost + edge_cost
            if next_cost >= distances.get(target, math.inf):
                continue
            distances[target] = next_cost
            predecessor[target] = current
            heapq.heappush(queue, (next_cost, next(sequence), target))
    return distances, predecessor


def reconstruct_path(predecessor: dict[str, str], source: str, target: str) -> list[str]:
    """Reconstruct one least-cost path."""
    path = [target]
    while path[-1] != source:
        path.append(predecessor[path[-1]])
    path.reverse()
    return path


def calculate_coverage(network: dict[str, Any]) -> list[dict[str, Any]]:
    """Calculate deterministic nearest-facility and overlap coverage records."""
    routing: dict[str, tuple[str, dict[str, float], dict[str, str]]] = {}
    for facility in sorted(network["facilities"], key=lambda item: item["facility_id"]):
        facility_id = str(facility["facility_id"])
        source = str(facility["node_id"])
        distances, predecessor = shortest_paths(network, source)
        routing[facility_id] = (source, distances, predecessor)

    cutoff = float(network["coverage_cutoff_minutes"])
    records = []
    for demand in sorted(network["demands"], key=lambda item: item["demand_id"]):
        target = str(demand["node_id"])
        candidates = []
        for facility_id, (source, distances, predecessor) in routing.items():
            if target not in distances:
                continue
            candidates.append(
                (
                    distances[target],
                    facility_id,
                    reconstruct_path(predecessor, source, target),
                )
            )
        candidates.sort(key=lambda item: (item[0], item[1]))
        within_cutoff = sorted(
            facility_id
            for cost, facility_id, _ in candidates
            if cost <= cutoff
        )
        if candidates:
            travel_time, assigned_facility, path = candidates[0]
            reachable = True
        else:
            travel_time, assigned_facility, path = None, None, []
            reachable = False
        records.append(
            {
                "demand_id": demand["demand_id"],
                "node_id": target,
                "population": demand["population"],
                "reachable": reachable,
                "covered": bool(within_cutoff),
                "assigned_facility": assigned_facility,
                "travel_time_minutes": travel_time,
                "facilities_within_cutoff": within_cutoff,
                "path": path,
            }
        )
    return records


def write_outputs(
    network: dict[str, Any],
    records: list[dict[str, Any]],
    output_dir: Path,
) -> None:
    """Write deterministic coverage, service-gap, and summary artifacts."""
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "demand-coverage.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "demand_id",
                "population",
                "reachable",
                "covered",
                "assigned_facility",
                "travel_time_minutes",
                "facilities_within_cutoff",
                "path",
            ],
            lineterminator="\n",
        )
        writer.writeheader()
        for record in records:
            writer.writerow(
                {
                    "demand_id": record["demand_id"],
                    "population": record["population"],
                    "reachable": str(record["reachable"]).lower(),
                    "covered": str(record["covered"]).lower(),
                    "assigned_facility": record["assigned_facility"] or "",
                    "travel_time_minutes": (
                        ""
                        if record["travel_time_minutes"] is None
                        else f"{record['travel_time_minutes']:.3f}"
                    ),
                    "facilities_within_cutoff": "|".join(
                        record["facilities_within_cutoff"]
                    ),
                    "path": ">".join(record["path"]),
                }
            )

    coordinates = {
        node["id"]: [float(node["x"]), float(node["y"])]
        for node in network["nodes"]
    }
    gap_features = []
    for record in records:
        if record["covered"]:
            continue
        gap_features.append(
            {
                "type": "Feature",
                "properties": {
                    "demand_id": record["demand_id"],
                    "population": record["population"],
                    "reachable": record["reachable"],
                    "reason": (
                        "beyond_cutoff" if record["reachable"] else "unreachable"
                    ),
                    "assigned_facility": record["assigned_facility"],
                    "travel_time_minutes": record["travel_time_minutes"],
                },
                "geometry": {
                    "type": "Point",
                    "coordinates": coordinates[record["node_id"]],
                },
            }
        )
    gaps = {
        "type": "FeatureCollection",
        "crs": {"type": "name", "properties": {"name": network["crs"]}},
        "features": gap_features,
    }
    (output_dir / "service-gaps.geojson").write_text(
        json.dumps(gaps, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    total_population = sum(int(record["population"]) for record in records)
    covered_population = sum(
        int(record["population"]) for record in records if record["covered"]
    )
    overlap_records = [
        record for record in records if len(record["facilities_within_cutoff"]) > 1
    ]
    summary = {
        "schema_version": 1,
        "crs": network["crs"],
        "mode": network["mode"],
        "cost_field": network["cost_field"],
        "cost_units": network["cost_units"],
        "coverage_cutoff_minutes": network["coverage_cutoff_minutes"],
        "facility_count": len(network["facilities"]),
        "demand_count": len(records),
        "covered_demand_count": sum(record["covered"] for record in records),
        "uncovered_demand_count": sum(not record["covered"] for record in records),
        "unreachable_demand_count": sum(
            not record["reachable"] for record in records
        ),
        "overlap_demand_count": len(overlap_records),
        "overlap_population": sum(
            int(record["population"]) for record in overlap_records
        ),
        "total_population": total_population,
        "covered_population": covered_population,
        "uncovered_population": total_population - covered_population,
        "coverage_share": covered_population / total_population,
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
    records = calculate_coverage(network)
    write_outputs(network, records, args.output_dir)
    print(f"reference outputs: {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
