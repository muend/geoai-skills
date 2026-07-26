"""Suppress before release, not after someone re-identifies a person.

Measured behaviour: "Proposes aggregation with k-anonymity suppression and
trip-end truncation" scored 17%. The model produces a beautiful origin-
destination flow map from GPS traces and never mentions that a flow of one
between a home and a clinic is a person.

Two mechanisms:

* ``suppress_small_counts`` — k-anonymity on aggregated cells or OD pairs, with
  the secondary suppression that people usually forget: if a row has exactly
  one suppressed cell, its value is recoverable by subtraction from the row
  total, so a second cell must go too.
* ``truncate_trip_ends`` — the first and last stretch of a trajectory sits at
  the home and the destination. Truncating a fixed distance at each end removes
  the two most identifying points.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import atan2, cos, radians, sin, sqrt
from collections.abc import Iterable
from typing import Any

from .result import Result, abstained, failed, passed

CHECK_K = "privacy.k_anonymity"
CHECK_TRIP = "privacy.trip_ends"

EARTH_RADIUS_M = 6_371_008.8


def haversine_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Great-circle distance in metres between two (lon, lat) points."""
    lon1, lat1 = radians(a[0]), radians(a[1])
    lon2, lat2 = radians(b[0]), radians(b[1])
    dlon, dlat = lon2 - lon1, lat2 - lat1
    h = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_M * atan2(sqrt(h), sqrt(1 - h))


@dataclass
class Suppression:
    cells: dict[Any, int | None]
    suppressed: list[Any]
    secondary: list[Any]
    k: int

    @property
    def n_suppressed(self) -> int:
        return len(self.suppressed) + len(self.secondary)


def suppress_small_counts(
    counts: dict[Any, int],
    *,
    k: int = 5,
    row_of: Any = None,
) -> Suppression:
    """Blank every cell below ``k``, then blank a second cell where needed.

    ``row_of`` maps a cell key to a grouping key (an OD origin, a tract, a
    period). Within a group, a single suppressed cell is not suppressed at all
    if the group total is published: subtract and the value reappears.
    """
    if k < 2:
        raise ValueError("k-anonymity with k < 2 suppresses nothing")

    released: dict[Any, int | None] = {}
    primary: list[Any] = []
    for key, value in counts.items():
        if value < k and value > 0:
            released[key] = None
            primary.append(key)
        else:
            released[key] = value

    secondary: list[Any] = []
    if row_of is not None:
        groups: dict[Any, list[Any]] = {}
        for key in counts:
            groups.setdefault(row_of(key), []).append(key)
        for _, members in groups.items():
            hidden = [m for m in members if released[m] is None]
            if len(hidden) != 1:
                continue
            candidates = sorted(
                (m for m in members if released[m] is not None),
                key=lambda m: (counts[m], repr(m)),
            )
            if candidates:
                victim = candidates[0]
                released[victim] = None
                secondary.append(victim)

    return Suppression(released, primary, secondary, k)


def check_k_anonymity(
    counts: dict[Any, int],
    *,
    k: int = 5,
    released_keys: Iterable[Any] | None = None,
) -> Result:
    """Fail when any released cell is below the threshold."""
    if not counts:
        return abstained(CHECK_K, "no counts supplied")
    if k < 2:
        return abstained(CHECK_K, f"k={k} is not a privacy threshold")

    keys = set(counts) if released_keys is None else set(released_keys)
    offenders = sorted(
        ((key, counts[key]) for key in keys if 0 < counts[key] < k),
        key=lambda item: item[1],
    )

    if offenders:
        shown = [f"{key!r}: n={value}" for key, value in offenders[:8]]
        if len(offenders) > 8:
            shown.append(f"... and {len(offenders) - 8} more")
        return failed(
            CHECK_K,
            f"{len(offenders)} released cell(s) below k={k}; individuals are "
            f"re-identifiable",
            evidence=shown,
            k=k,
            n_offending=len(offenders),
        )

    return passed(
        CHECK_K,
        f"all {len(keys)} released cell(s) meet k={k}",
        k=k,
        n_cells=len(keys),
    )


def truncate_trip_ends(
    points: list[tuple[float, float]],
    *,
    radius_m: float = 300.0,
) -> list[tuple[float, float]]:
    """Drop the leading and trailing points within ``radius_m`` of each end.

    The origin and destination are the identifying part of a trajectory: home
    and workplace, or home and clinic. Everything between them is far less
    revealing.
    """
    if radius_m <= 0:
        raise ValueError("truncation radius must be positive")
    if len(points) < 3:
        return []

    start, end = points[0], points[-1]
    first = 0
    while first < len(points) and haversine_m(points[first], start) < radius_m:
        first += 1
    last = len(points) - 1
    while last >= 0 and haversine_m(points[last], end) < radius_m:
        last -= 1

    return points[first : last + 1] if first <= last else []


def check_trip_ends_truncated(
    original: list[tuple[float, float]],
    released: list[tuple[float, float]],
    *,
    radius_m: float = 300.0,
) -> Result:
    """Fail when a released trajectory still starts or ends at the real ends."""
    if len(original) < 3:
        return abstained(CHECK_TRIP, "trajectory too short to assess")
    if not released:
        return passed(
            CHECK_TRIP, "trajectory fully suppressed", radius_m=radius_m
        )

    problems: list[str] = []
    if haversine_m(released[0], original[0]) < radius_m:
        problems.append(
            f"released start is {haversine_m(released[0], original[0]):.0f} m "
            f"from the true origin (threshold {radius_m:.0f} m)"
        )
    if haversine_m(released[-1], original[-1]) < radius_m:
        problems.append(
            f"released end is {haversine_m(released[-1], original[-1]):.0f} m "
            f"from the true destination (threshold {radius_m:.0f} m)"
        )

    if problems:
        return failed(
            CHECK_TRIP,
            "trip ends were not truncated; origin and destination are exposed",
            evidence=problems,
            radius_m=radius_m,
        )

    return passed(
        CHECK_TRIP,
        f"both trip ends truncated beyond {radius_m:.0f} m",
        radius_m=radius_m,
        n_points=len(released),
    )
