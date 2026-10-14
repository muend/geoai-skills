"""Bounded artifact validators, not certificates of field safety or scientific truth.

All inputs are files under one evidence directory. Missing/unsupported evidence
abstains; a concrete contradiction fails. No model or network calls are made.
"""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from .core import contained, finite, outcome, read_json, report


def projected(crs: str) -> None:
    from pyproj import CRS

    value = CRS.from_user_input(crs)
    if not value.is_projected or any(a.unit_name != "metre" for a in value.axis_info):
        raise ValueError("pilot geometry must use an explicitly projected metre CRS")


def features(root: Path, filename: str) -> list[dict[str, Any]]:
    value = read_json(contained(root, filename))
    if value["type"] != "FeatureCollection" or not isinstance(value["features"], list):
        raise ValueError("expected a GeoJSON FeatureCollection")
    return value["features"]


def walkability(root: Path, spec: dict[str, Any]) -> dict[str, Any]:
    from shapely.geometry import shape
    from shapely.ops import unary_union

    projected(spec["crs"])
    routes = features(root, spec["route"])
    edges = features(root, spec["network"])
    barriers = features(root, spec["barriers"])
    if not routes or not edges or spec.get("coverage_complete") is not True:
        return outcome("walkability", "abstain", "Network or barrier coverage is incomplete")
    tolerance = finite(spec["tolerance_m"])
    if tolerance < 0 or tolerance > 1:
        raise ValueError("tolerance must be between 0 and 1 metre")
    issues = []
    for edge in edges:
        g = shape(edge["geometry"])
        if g.geom_type != "LineString" or not g.is_valid or g.is_empty:
            raise ValueError("network evidence must contain valid LineStrings")
        if edge["properties"]["foot_access"] not in {"yes", "no"}:
            raise ValueError("network access is unknown")

    def covers(lines: list, geometry: Any) -> bool:
        network = unary_union(lines)
        return (network.buffer(tolerance) if tolerance else network).covers(geometry)

    for i, route in enumerate(routes):
        geometry = shape(route["geometry"])
        level = route["properties"]["level"]
        if not geometry.is_valid or geometry.is_empty or geometry.geom_type != "LineString":
            return outcome("walkability", "fail", "Invalid route geometry", feature=i)
        allowed = []
        for edge in edges:
            p = edge["properties"]
            if p["level"] == level and p["foot_access"] == "yes":
                allowed.append(shape(edge["geometry"]))
        if not allowed or not covers(allowed, geometry):
            issues.append({"route": i, "reason": "outside permitted same-level network"})
        for barrier in barriers:
            p = barrier["properties"]
            obstacle = shape(barrier["geometry"])
            if (not obstacle.is_valid or obstacle.is_empty
                    or obstacle.geom_type not in {"Polygon", "MultiPolygon"}):
                return outcome("walkability", "abstain", "Invalid barrier geometry")
            if p["level"] != level or not geometry.intersects(obstacle):
                continue
            crossing = geometry.intersection(obstacle)
            # Water crossing requires a matching explicit bridge, not mere proximity.
            bridges = [shape(e["geometry"]) for e in edges
                       if e["properties"].get("bridge") is True
                       and e["properties"]["level"] == level
                       and e["properties"]["foot_access"] == "yes"]
            if p["kind"] == "water" and bridges and (
                    covers(bridges, crossing)):
                continue
            issues.append({"route": i, "barrier": p["id"],
                           "intersection": crossing.wkt})
    return outcome("walkability", "fail" if issues else "pass",
                   "Modelled access contradictions" if issues else "No modelled contradiction",
                   findings=issues, scope="supplied network and barriers; not field verification")


def line_semantics(root: Path, spec: dict[str, Any]) -> dict[str, Any]:
    raw = contained(root, spec["svg"]).read_text(encoding="utf-8")
    if "<!DOCTYPE" in raw.upper() or "<!ENTITY" in raw.upper():
        raise ValueError("SVG entities are unsupported")
    tree = ET.fromstring(raw)  # noqa: S314 - entities rejected; local bounded fixture
    if any(n.tag.rsplit("}", 1)[-1] in {"style", "use", "script", "image", "foreignObject"}
           or any(n.get(a) is not None for a in
                  ("style", "class", "transform", "clip-path", "mask", "filter"))
           for n in tree.iter()):
        return outcome("line-semantics", "abstain", "CSS/transforms/embedded content unsupported")
    parents = {child: node for node in tree.iter() for child in node}

    def visible(node: Any) -> bool:
        while node is not None:
            if (node.get("display") == "none" or node.get("visibility") in {"hidden", "collapse"}
                    or finite(float(node.get("opacity", "1"))) <= 0):
                return False
            node = parents.get(node)
        return True

    paths = [n for n in tree.iter() if n.get("data-route-segment") is not None]
    if len(paths) < 2:
        return outcome("line-semantics", "abstain", "Need at least two identified segments")
    widths, points = [], []
    for node in paths:
        if node.tag.rsplit("}", 1)[-1] != "polyline" or node.get("style"):
            return outcome("line-semantics", "abstain", "Only explicit polyline strokes supported")
        widths.append(finite(float(node.attrib["stroke-width"])))
        if (widths[-1] <= 0 or not visible(node) or node.get("stroke") in {None, "none"}
                or finite(float(node.get("stroke-opacity", "1"))) <= 0):
            return outcome("line-semantics", "fail", "Non-visible segment width")
        pts = [tuple(finite(float(v)) for v in p.split(","))
               for p in node.attrib["points"].split()]
        if len(pts) < 2 or any(len(p) != 2 for p in pts):
            raise ValueError("invalid polyline points")
        points.append(pts)
    legends = {n.get("id"): "".join(n.itertext()).strip() for n in tree.iter()
               if n.tag.rsplit("}", 1)[-1] == "text" and visible(n)}
    issues = []
    if len(set(widths)) > 1 and not legends.get("width-legend"):
        issues.append("Width changes without a visible width legend")
    tolerance = finite(spec["join_tolerance"])
    if tolerance < 0:
        raise ValueError("negative join tolerance")
    gaps = [i for i in range(1, len(points))
            if math.dist(points[i - 1][-1], points[i][0]) > tolerance]
    if gaps and not legends.get("gap-legend"):
        issues.append("Disconnected segments without a visible gap legend")
    return outcome("line-semantics", "fail" if issues else "pass",
                   "; ".join(issues) if issues else "Structural line/legend checks passed",
                   widths=widths, gaps=gaps, human_review="required for comprehension",
                   scope="explicit SVG polylines only; text meaning not machine-certified")


def imagery(root: Path, spec: dict[str, Any]) -> dict[str, Any]:
    a, b = [read_json(contained(root, spec[key])) for key in ("before", "after")]
    required = ("sensor", "processing_level", "season", "crs", "transform", "values", "mask")
    if any(k not in scene for scene in (a, b) for k in required):
        return outcome("imagery-comparability", "abstain", "Scene evidence is incomplete")
    mismatches = [k for k in required[:5] if a[k] != b[k]]
    if mismatches:
        return outcome("imagery-comparability", "fail", "Incomparable observations",
                       axes=mismatches)
    if any(type(v) is not bool for scene in (a, b) for v in scene["mask"]):
        raise ValueError("observation masks must contain booleans")
    if len(a["values"]) != len(b["values"]) or any(
            len(s["values"]) != len(s["mask"]) for s in (a, b)):
        return outcome("imagery-comparability", "fail", "Grid/mask dimensions differ")
    usable = [i for i in range(len(a["values"])) if a["mask"][i] and b["mask"][i]]
    if not usable:
        return outcome("imagery-comparability", "abstain", "No mutually valid observations")
    expected = [finite(b["values"][i]) - finite(a["values"][i]) for i in usable]
    result = read_json(contained(root, spec["result"]))
    correct = result["indices"] == usable and len(result["difference"]) == len(expected)
    correct = correct and all(math.isclose(finite(x), y, abs_tol=1e-8)
                              for x, y in zip(result["difference"], expected, strict=True))
    return outcome("imagery-comparability", "pass" if correct else "fail",
                   "Mutual-mask difference checked", valid_pixels=len(usable),
                   scope="declared scene provenance and supplied pixel arrays")


def terrain(root: Path, spec: dict[str, Any]) -> dict[str, Any]:
    dem = read_json(contained(root, spec["dem"]))
    required = ("horizontal_unit", "vertical_unit", "vertical_datum", "cell_size", "nodata")
    if any(k not in dem or dem[k] is None for k in required):
        return outcome("terrain-units-nodata", "abstain", "DEM unit/datum evidence missing")
    if dem["horizontal_unit"] != "m" or dem["vertical_unit"] != "m":
        return outcome("terrain-units-nodata", "fail", "Unconverted horizontal/vertical units")
    size = finite(dem["cell_size"])
    if size <= 0:
        raise ValueError("cell size must be positive")
    values = dem["values"]
    expected = [None if a == dem["nodata"] or b == dem["nodata"] else
                math.degrees(math.atan(abs(finite(b) - finite(a)) / size))
                for a, b in zip(values[:-1], values[1:], strict=True)]
    result = read_json(contained(root, spec["result"]))["east_slope_degrees"]
    correct = bool(expected) and len(expected) == len(result)
    if correct:
        correct = all((x is None and y is None) or
                      (x is not None and y is not None and
                       math.isclose(finite(x), y, abs_tol=1e-8))
                      for x, y in zip(result, expected, strict=True))
    return outcome("terrain-units-nodata", "pass" if correct else "fail",
                   "East-neighbour slope and NoData propagation checked",
                   scope="one-dimensional metre-grid diagnostic, not a hydrological model")


def spatial_split(root: Path, spec: dict[str, Any]) -> dict[str, Any]:
    projected(spec["crs"])
    rows = read_json(contained(root, spec["samples"]))
    if not rows or any(not all(k in r for k in ("split", "group", "x", "y")) for r in rows):
        return outcome("spatial-split", "abstain", "Missing split/group/coordinate evidence")
    train = [r for r in rows if r["split"] == "train"]
    test = [r for r in rows if r["split"] == "test"]
    if not train or not test:
        return outcome("spatial-split", "abstain", "Both train and test samples required")
    if any(r["split"] not in {"train", "test"} for r in rows):
        return outcome("spatial-split", "abstain", "Unsupported split labels")
    overlap = sorted({r["group"] for r in train} & {r["group"] for r in test})
    minimum = min(math.dist((finite(a["x"]), finite(a["y"])),
                            (finite(b["x"]), finite(b["y"]))) for a in train for b in test)
    threshold = finite(spec["minimum_separation_m"])
    if threshold <= 0:
        raise ValueError("minimum separation must be positive")
    return outcome("spatial-split", "fail" if overlap or minimum < threshold else "pass",
                   "Group overlap and point separation checked", overlap=overlap,
                   minimum_distance_m=minimum,
                   scope="point-sample diagnostic; threshold must be justified independently")


def suitability(root: Path, spec: dict[str, Any]) -> dict[str, Any]:
    data = read_json(contained(root, spec["criteria"]))
    result = read_json(contained(root, spec["result"]))
    if not data.get("weight_rationale") or not data.get("normalization"):
        return outcome("suitability-sensitivity", "abstain", "Weight/normalization evidence absent")
    weights = [finite(v) for v in data["weights"]]
    matrix = [[finite(v) for v in row] for row in data["alternatives"]]
    if not weights or not matrix or any(len(r) != len(weights) for r in matrix):
        raise ValueError("invalid criterion matrix")
    if any(w < 0 for w in weights) or not math.isclose(sum(weights), 1, abs_tol=1e-8):
        return outcome("suitability-sensitivity", "fail", "Weights are not a convex combination")
    if any(v < 0 or v > 1 for row in matrix for v in row):
        return outcome("suitability-sensitivity", "fail", "Expected normalized benefit criteria")
    scores = [sum(w * v for w, v in zip(weights, row, strict=True)) for row in matrix]
    winner = max(range(len(scores)), key=scores.__getitem__)
    winners = {i for i, s in enumerate(scores) if math.isclose(s, scores[winner], abs_tol=1e-8)}
    for index in range(len(weights)):
        for delta in (-0.1, 0.1):
            ws = list(weights)
            ws[index] = max(0.0, ws[index] + delta)
            total = sum(ws)
            if total == 0:
                continue
            perturbed = [sum(w * v / total for w, v in zip(ws, row, strict=True))
                         for row in matrix]
            best = max(perturbed)
            winners.update(i for i, s in enumerate(perturbed)
                           if math.isclose(s, best, abs_tol=1e-8))
    stable = len(winners) == 1
    correct = (result["winner"] == winner and result["stable_under_test"] == stable
               and len(result["scores"]) == len(scores))
    if correct:
        correct = all(math.isclose(finite(a), b, abs_tol=1e-8)
                      for a, b in zip(result["scores"], scores, strict=True))
    if result.get("claim") == "robust" and not stable:
        correct = False
    return outcome("suitability-sensitivity", "pass" if correct else "fail",
                   "Scores and +/-0.1 normalized weight perturbations checked",
                   winner=winner, stable_under_test=stable,
                   scope="specified sensitivity test, not universal robustness")


CHECKS = {"walkability": walkability, "line-semantics": line_semantics,
          "imagery-comparability": imagery, "terrain-units-nodata": terrain,
          "spatial-split": spatial_split, "suitability-sensitivity": suitability}


def run_check(name: str, root: Path, spec: dict[str, Any]) -> dict[str, Any]:
    try:
        if name not in CHECKS:
            return report([outcome(name, "abstain", "No executable validator registered")])
        return report([CHECKS[name](root, spec)])
    except (OSError, ValueError, TypeError, KeyError, ImportError, ET.ParseError) as exc:
        return report([outcome(name, "abstain", f"Cannot verify: {type(exc).__name__}: {exc}")])
