# Authoritative sources

- Last verified: 2026-08-05
- Review cadence: every 3 months
- Refresh triggers: collection reprocessing, calibration update, catalog deprecation, or sensor anomaly

## Canonical sources

- [USGS Landsat Collection 2 Level-2 products](https://www.usgs.gov/landsat-missions/landsat-collection-2-level-2-science-products) — official scaling, quality, and science-product semantics.
- [Copernicus Sentinel-2 documentation](https://documentation.dataspace.copernicus.eu/Data/SentinelMissions/Sentinel2.html) — official product and mission details.
- [STAC specification](https://github.com/radiantearth/stac-spec) — interoperable catalog and asset metadata.
- [SentiWiki — Sentinel-2 processing](https://sentiwiki.copernicus.eu/web/s2-processing) — processing baselines, `BOA_ADD_OFFSET` and `QUANTIFICATION_VALUE` semantics. Check the current baseline before assuming −1000.
- [Earth Engine `COPERNICUS/S2_SR_HARMONIZED`](https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_S2_SR_HARMONIZED) — worked example of a collection where the baseline offset is *already* removed; the canonical double-correction trap.

Record sensor, collection, processing level, **processing baseline**, product identifier, acquisition dates, calibration factors and offsets, quality masks, band resolutions, resampling, CRS, and software versions.
