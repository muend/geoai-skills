"""Standard vector hygiene pass with loud accounting.

Run:    python clean_vector.py input.gpkg output.parquet 32636
Import: from clean_vector import clean_vector
"""
from __future__ import annotations

import argparse
from pathlib import Path

import geopandas as gpd
from pyproj import CRS
from shapely import make_valid


def clean_vector(gdf: gpd.GeoDataFrame, target_epsg: int) -> gpd.GeoDataFrame:
    """Validity, emptiness, duplicates, CRS — returns a cleaned copy.

    Prints an accounting report of every change so silent data loss is
    impossible.

    Args:
        gdf: Input GeoDataFrame (any CRS, must be defined).
        target_epsg: EPSG code of the projected CRS to analyze in.

    Returns:
        Cleaned GeoDataFrame in the target CRS. Only exact duplicate features
        (same attributes and same geometry) are removed.

    Raises:
        ValueError: If the input CRS is undefined, the target CRS is not
            projected, or geometry repair leaves invalid features.
    """
    if gdf.crs is None:
        raise ValueError("Input CRS undefined — resolve it before cleaning.")

    target_crs = CRS.from_epsg(target_epsg)
    if not target_crs.is_projected:
        raise ValueError(
            f"Target EPSG:{target_epsg} is not projected — choose a CRS with "
            "linear units for analysis."
        )

    n0 = len(gdf)
    result = gdf.copy()

    missing_or_empty = result.geometry.isna() | result.geometry.is_empty
    removed_missing = int(missing_or_empty.sum())
    result = result.loc[~missing_or_empty].copy()

    invalid = ~result.geometry.is_valid
    repaired = int(invalid.sum())
    if repaired:
        result.loc[invalid, result.geometry.name] = result.loc[
            invalid, result.geometry.name
        ].apply(make_valid)

    invalid_after = ~result.geometry.is_valid
    if invalid_after.any():
        raise ValueError(
            f"Geometry repair left {int(invalid_after.sum())} invalid features."
        )

    empty_after_repair = result.geometry.isna() | result.geometry.is_empty
    removed_after_repair = int(empty_after_repair.sum())
    result = result.loc[~empty_after_repair].copy()

    # Include geometry in the duplicate key. Attribute-only deduplication can
    # silently delete distinct features that happen to share the same fields.
    duplicate_subset = list(result.columns)
    exact_duplicates = result.duplicated(subset=duplicate_subset, keep="first")
    removed_duplicates = int(exact_duplicates.sum())
    result = result.loc[~exact_duplicates].copy()

    result = result.to_crs(target_crs)
    geometry_types = ",".join(sorted(result.geometry.geom_type.unique()))
    print(
        f"rows {n0} -> {len(result)} | removed null/empty {removed_missing} "
        f"| repaired {repaired} | removed after repair {removed_after_repair} "
        f"| removed exact duplicates {removed_duplicates} "
        f"| geometry types {geometry_types or 'none'} "
        f"| CRS -> EPSG:{target_epsg}"
    )
    return result


def main() -> None:
    """Run the vector hygiene pass from the command line."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("target_epsg", type=int)
    args = parser.parse_args()

    output = clean_vector(gpd.read_file(args.source), args.target_epsg)
    if args.destination.suffix.lower() == ".parquet":
        output.to_parquet(args.destination)
    else:
        output.to_file(args.destination)
    print(f"wrote {args.destination}")


if __name__ == "__main__":
    main()
