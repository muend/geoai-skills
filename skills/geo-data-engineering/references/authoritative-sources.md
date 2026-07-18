# Authoritative sources

- Last verified: 2026-07-19
- Review cadence: every 3 months
- Refresh triggers: GDAL, PROJ, GeoParquet, or STAC specification release

## Canonical sources

- [GeoParquet specification](https://geoparquet.org/releases/v1.1.0/) — interoperable vector metadata and geometry encoding.
- [GDAL documentation](https://gdal.org/en/stable/) — format drivers and transformation behavior.
- [PROJ documentation](https://proj.org/en/stable/) — coordinate operations and grid requirements.
- [STAC specification](https://github.com/radiantearth/stac-spec) — catalog and asset metadata contracts.

Pin concrete format/specification versions in pipelines. Verify driver capability against the deployed GDAL/PROJ build rather than assuming the latest documentation matches runtime behavior.
