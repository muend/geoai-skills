"""Refuse to compare observations that are not comparable.

Measured behaviour: "Rejects per-date Jenks breaks as incomparable" scored 20%.
The model optimises each date independently — best classification for date one,
best classification for date two — and the resulting panel looks like change
when the only thing that changed is the class boundaries.

The same trap has four other doors: different sensors, different processing
levels, different seasons, different spatial resolutions. Each produces a
difference image that is technically correct and scientifically meaningless.

This module compares scene descriptors and names every axis that breaks
comparability, rather than returning a single yes/no that hides which one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .result import Result, abstained, failed, passed

CHECK = "comparability.scenes"
CHECK_BREAKS = "comparability.class_breaks"

# Processing levels that are not interchangeable. Top-of-atmosphere reflectance
# and surface reflectance differ by the whole atmospheric correction.
PROCESSING_ORDER = {
    "l1c": "top-of-atmosphere",
    "l1t": "top-of-atmosphere",
    "toa": "top-of-atmosphere",
    "l2a": "surface",
    "l2sp": "surface",
    "sr": "surface",
    "boa": "surface",
}

SEASON_BY_MONTH = {
    12: "djf", 1: "djf", 2: "djf",
    3: "mam", 4: "mam", 5: "mam",
    6: "jja", 7: "jja", 8: "jja",
    9: "son", 10: "son", 11: "son",
}


@dataclass
class Scene:
    """Everything about an observation that determines comparability."""

    label: str
    sensor: str | None = None
    processing_level: str | None = None
    acquired_month: int | None = None
    resolution_m: float | None = None
    crs: str | None = None
    bands: tuple[str, ...] | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def processing_family(self) -> str | None:
        if not self.processing_level:
            return None
        return PROCESSING_ORDER.get(self.processing_level.strip().lower())

    @property
    def season(self) -> str | None:
        if self.acquired_month is None:
            return None
        return SEASON_BY_MONTH.get(int(self.acquired_month))


def compare_scenes(
    scenes: list[Scene],
    *,
    allow_cross_sensor: bool = False,
    allow_cross_season: bool = False,
    resolution_tolerance: float = 0.0,
) -> Result:
    """Fail when scenes differ on an axis that invalidates differencing."""
    if len(scenes) < 2:
        return abstained(CHECK, "fewer than two scenes supplied")

    problems: list[str] = []
    unknown: list[str] = []
    reference = scenes[0]

    for scene in scenes[1:]:
        pair = f"{reference.label} vs {scene.label}"

        if reference.sensor and scene.sensor:
            if reference.sensor != scene.sensor and not allow_cross_sensor:
                problems.append(
                    f"{pair}: different sensors ({reference.sensor} vs "
                    f"{scene.sensor}); harmonise band responses first or declare "
                    f"cross-sensor explicitly"
                )
        else:
            unknown.append(f"{pair}: sensor not declared on both scenes")

        left_family = reference.processing_family
        right_family = scene.processing_family
        if left_family and right_family:
            if left_family != right_family:
                problems.append(
                    f"{pair}: {reference.processing_level} is {left_family} but "
                    f"{scene.processing_level} is {right_family}; the difference "
                    f"would include the atmospheric correction"
                )
        elif reference.processing_level or scene.processing_level:
            unknown.append(
                f"{pair}: processing level not declared or not recognised "
                f"({reference.processing_level!r}, {scene.processing_level!r})"
            )

        if reference.season and scene.season:
            if reference.season != scene.season and not allow_cross_season:
                problems.append(
                    f"{pair}: different seasons ({reference.season} vs "
                    f"{scene.season}); phenology will dominate the difference"
                )
        else:
            unknown.append(f"{pair}: acquisition month not declared on both scenes")

        if reference.resolution_m is not None and scene.resolution_m is not None:
            gap = abs(reference.resolution_m - scene.resolution_m)
            if gap > resolution_tolerance:
                problems.append(
                    f"{pair}: resolution differs ({reference.resolution_m} m vs "
                    f"{scene.resolution_m} m); resample to a common grid first"
                )

        if reference.crs and scene.crs and reference.crs != scene.crs:
            problems.append(
                f"{pair}: different CRS ({reference.crs} vs {scene.crs}); "
                f"pixels do not align"
            )

        if reference.bands and scene.bands and reference.bands != scene.bands:
            problems.append(
                f"{pair}: band sets differ ({reference.bands} vs {scene.bands})"
            )

    if problems:
        return failed(
            CHECK,
            f"{len(problems)} comparability break(s) across {len(scenes)} scenes",
            evidence=problems + [f"(also unverified) {u}" for u in unknown],
            n_scenes=len(scenes),
        )

    if unknown:
        return abstained(
            CHECK,
            f"scenes agree on every declared axis but {len(unknown)} axis/axes "
            f"were not declared",
            undeclared=unknown,
        )

    return passed(CHECK, f"{len(scenes)} scenes are comparable", n_scenes=len(scenes))


def check_shared_class_breaks(
    breaks_by_date: dict[str, list[float]],
    *,
    tolerance: float = 1e-9,
) -> Result:
    """Fail when a map series uses per-date class boundaries.

    A choropleth series with per-date Jenks breaks shows the classifier's
    behaviour, not the data's. The panels are individually optimal and jointly
    uninterpretable.
    """
    if len(breaks_by_date) < 2:
        return abstained(CHECK_BREAKS, "fewer than two dates supplied")

    labels = sorted(breaks_by_date)
    reference_label = labels[0]
    reference = list(breaks_by_date[reference_label])

    differing: list[str] = []
    for label in labels[1:]:
        candidate = list(breaks_by_date[label])
        if len(candidate) != len(reference):
            differing.append(
                f"{label}: {len(candidate)} classes vs {len(reference)} in "
                f"{reference_label}"
            )
            continue
        gaps = [
            f"class {i}: {a} vs {b}"
            for i, (a, b) in enumerate(zip(reference, candidate, strict=True))
            if abs(a - b) > tolerance
        ]
        if gaps:
            differing.append(f"{label} differs from {reference_label} at " + "; ".join(gaps))

    if differing:
        return failed(
            CHECK_BREAKS,
            f"class breaks differ across {len(breaks_by_date)} dates; the panels "
            f"cannot be read as change",
            evidence=differing + [
                "compute one classification over the pooled distribution and "
                "apply it to every date"
            ],
            n_dates=len(breaks_by_date),
        )

    return passed(
        CHECK_BREAKS,
        f"all {len(breaks_by_date)} dates share one classification",
        n_dates=len(breaks_by_date),
        class_edges=reference,
    )
