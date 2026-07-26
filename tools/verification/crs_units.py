"""Refuse measurements taken in the wrong units.

The failure this exists for is silent: a buffer, area, length or slope computed
on a geographic CRS returns a number. The number is wrong by roughly a factor
of 100,000, and nothing in the output says so. This is the single most common
way a geospatial result is confidently incorrect.

Two independent checks:

* ``check_planar_operation`` — a metric operation must not run on an angular
  CRS. "5000" in EPSG:4326 means 5000 degrees.
* ``check_vertical_horizontal_units`` — slope, aspect and curvature divide a
  vertical difference by a horizontal one. If the DEM's elevation is in metres
  and its horizontal CRS is in feet (or degrees), every derived angle is wrong.

No pyproj dependency: the CRS registry here is a small, explicit table. That is
a deliberate trade — a check that needs a heavy optional dependency is a check
that gets skipped. Unknown codes ABSTAIN rather than guess.
"""

from __future__ import annotations

import re

from .result import Result, abstained, failed, passed

CHECK_PLANAR = "crs.planar_operation"
CHECK_VERTICAL = "crs.vertical_horizontal_units"

# Angular (geographic) CRSs commonly used. Values are degrees, not metres.
ANGULAR_EPSG = {
    4326: "WGS 84",
    4269: "NAD83",
    4258: "ETRS89",
    4267: "NAD27",
    4283: "GDA94",
    4171: "RGF93",
}

# Projected CRSs whose axis unit is US survey feet or international feet.
FOOT_EPSG = {
    2225: "NAD83 / California zone 1 (ftUS)",
    2263: "NAD83 / New York Long Island (ftUS)",
    2276: "NAD83 / Texas North Central (ftUS)",
    6539: "NAD83(2011) / New York Long Island (ftUS)",
}

METRIC_OPERATIONS = {
    "buffer",
    "area",
    "length",
    "distance",
    "centroid_distance",
    "nearest_distance",
    "slope",
    "aspect",
    "curvature",
    "viewshed",
    "watershed",
    "density",
    "hillshade",
}

_EPSG_PATTERN = re.compile(r"(?:epsg\s*[:=]?\s*)?(?<!\d)(\d{4,6})(?!\d)", re.I)


def parse_epsg(crs: str | int | None) -> int | None:
    """Extract an EPSG code from 'EPSG:4326', 'epsg 4326', 4326 or None.

    The digit run is anchored on both sides. Without that, 'EPSG:99999999'
    silently parsed as 999999 — a wrong code that happens to look plausible is
    worse than no code, because it turns a clear abstention into a confident
    lookup against the wrong entry.
    """
    if crs is None:
        return None
    if isinstance(crs, int):
        return crs
    match = _EPSG_PATTERN.search(str(crs))
    return int(match.group(1)) if match else None


def axis_unit(crs: str | int | None) -> str | None:
    """Return 'degree', 'foot', 'metre' or None when the code is unknown."""
    code = parse_epsg(crs)
    if code is None:
        return None
    if code in ANGULAR_EPSG:
        return "degree"
    if code in FOOT_EPSG:
        return "foot"
    # UTM north/south, Web Mercator and the national grids in the 2000-9999
    # projected band are metre-based unless listed above. Anything outside the
    # known projected ranges is unknown rather than assumed.
    if 2000 <= code <= 32799 or code == 3857:
        return "metre"
    return None


def check_planar_operation(
    operation: str,
    crs: str | int | None,
    *,
    value: float | None = None,
) -> Result:
    """Fail when a metric operation is requested on an angular CRS."""
    op = operation.strip().lower()
    if op not in METRIC_OPERATIONS:
        return abstained(
            CHECK_PLANAR,
            f"operation {operation!r} is not a known metric operation",
            known=sorted(METRIC_OPERATIONS),
        )

    code = parse_epsg(crs)
    if code is None:
        return abstained(
            CHECK_PLANAR,
            f"no EPSG code could be read from crs={crs!r}; unit is unknown",
        )

    unit = axis_unit(code)
    if unit is None:
        return abstained(
            CHECK_PLANAR, f"EPSG:{code} is not in the unit registry", epsg=code
        )

    if unit == "degree":
        quoted = f"{value} degrees" if value is not None else "a value in degrees"
        return failed(
            CHECK_PLANAR,
            f"{op} on EPSG:{code} ({ANGULAR_EPSG.get(code, 'angular CRS')}) "
            f"measures in degrees, not metres",
            evidence=[
                f"operation={op}",
                f"crs=EPSG:{code} axis unit=degree",
                f"the result would be {quoted}",
            ],
            epsg=code,
            unit=unit,
        )

    if unit == "foot":
        return failed(
            CHECK_PLANAR,
            f"{op} on EPSG:{code} returns feet; record the unit or reproject",
            evidence=[f"crs=EPSG:{code} axis unit=foot"],
            epsg=code,
            unit=unit,
        )

    return passed(
        CHECK_PLANAR, f"{op} on EPSG:{code} is metric", epsg=code, unit=unit
    )


def check_vertical_horizontal_units(
    horizontal_crs: str | int | None,
    vertical_unit: str | None,
) -> Result:
    """Fail when elevation units do not match the horizontal axis units.

    Slope = rise / run. If rise is metres and run is degrees or feet, the angle
    is meaningless, and the raster still renders.
    """
    if not vertical_unit:
        return abstained(CHECK_VERTICAL, "vertical unit was not declared")

    horizontal = axis_unit(horizontal_crs)
    if horizontal is None:
        return abstained(
            CHECK_VERTICAL,
            f"horizontal unit unknown for crs={horizontal_crs!r}",
        )

    vertical = vertical_unit.strip().lower()
    aliases = {
        "m": "metre",
        "meter": "metre",
        "meters": "metre",
        "metres": "metre",
        "metre": "metre",
        "ft": "foot",
        "feet": "foot",
        "foot": "foot",
        "us survey foot": "foot",
    }
    vertical = aliases.get(vertical, vertical)

    if horizontal == "degree":
        return failed(
            CHECK_VERTICAL,
            f"elevation in {vertical} over an angular horizontal CRS: "
            f"slope and aspect cannot be computed correctly",
            evidence=[
                f"horizontal={horizontal} (EPSG:{parse_epsg(horizontal_crs)})",
                f"vertical={vertical}",
                "reproject to a metric projected CRS before deriving slope",
            ],
            horizontal=horizontal,
            vertical=vertical,
        )

    if vertical != horizontal:
        return failed(
            CHECK_VERTICAL,
            f"vertical unit {vertical} does not match horizontal unit {horizontal}",
            evidence=[f"horizontal={horizontal}", f"vertical={vertical}"],
            horizontal=horizontal,
            vertical=vertical,
        )

    return passed(
        CHECK_VERTICAL,
        f"vertical and horizontal units agree ({horizontal})",
        horizontal=horizontal,
        vertical=vertical,
    )
