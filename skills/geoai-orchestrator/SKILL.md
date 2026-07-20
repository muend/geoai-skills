---
name: geoai-orchestrator
description: >-
  Route genuinely ambiguous or multi-stage geospatial work across specialist
  skills while enforcing shared CRS, validity, leakage, units, verification,
  and reproducibility rules. Use for requests spanning multiple stages such as
  acquisition, imagery, modeling, analysis, and map delivery, or for an
  explicit end-to-end pipeline. Never invoke for one domain merely because a
  parameter is unclear. Code implementation/review, backend or platform
  choice, and production-readiness review are direct specialist tasks. Do not
  add this skill as a layer around one specialist.
license: MIT
metadata:
  version: "0.1.0"
  author: Muhammed Enes Duran
---

# GeoAI Orchestrator

The hub of a 17-skill geospatial module. Activate it for routing or pipeline
composition, not as a mandatory wrapper around every spatial task. Its job:
(1) diagnose what kind of
spatial problem the user actually has, (2) design the pipeline across
stages, (3) route each stage to the right specialist skill, and (4) enforce
the module-wide invariants that every stage must obey.

## Module map — route by problem type

| Stage / problem | Specialist skill |
|---|---|
| Data acquisition, formats, CRS, tiling, pipelines | `geo-data-engineering` |
| Satellite/aerial imagery, spectral indices, classification | `remote-sensing-analysis` |
| Planetary-scale archives, GEE Python API, cloud compositing | `google-earth-engine` |
| CNN/U-Net/ViT on EO data, segmentation, detection | `geo-deep-learning` |
| Autocorrelation, hotspots, clusters, spatial regression | `spatial-statistics` |
| Site selection, suitability, AHP/weighted overlay | `mcda-suitability-analysis` |
| Interpolation from point samples, kriging, variograms | `geostatistics-interpolation` |
| DEM, slope, watersheds, flow, viewshed | `terrain-hydrology` |
| LiDAR / point clouds, DTM/DSM/CHM, PDAL | `point-cloud-lidar` |
| Routing, service areas, accessibility, OD matrices | `network-accessibility-analysis` |
| GPS tracks, trajectories, stops/trips, map matching | `movement-trajectory` |
| Multi-temporal comparison, land cover change, trends | `change-detection` |
| Map design, choropleths, web maps, publication figures | `cartography-geoviz` |
| Spatial SQL, PostGIS, large-scale spatial joins | `postgis-spatial-sql` |

Invoke every selected specialist with the `Skill` tool before executing its
stage; listing a specialist in a plan is not a completed handoff. For
cross-cutting method standards (leakage, metrics, reproducibility), invoke
`ml-experiment-standards` and `swe-devops-standards` when their rules apply.

## Pipeline design protocol

For any multi-stage request, produce a short pipeline plan BEFORE writing
code, and get confirmation only when scope is ambiguous:

```
## Pipeline: <goal>
1. <stage> → <skill> → output: <artifact> → check: <verification criterion>
2. ...
Success criterion: <what the user can inspect to accept the result>
```

Every stage ends with a verification criterion. Spatial work fails silently
(wrong CRS, empty joins, inverted axes produce plausible-looking garbage),
so a stage without a check is not a stage.

## Module-wide invariants (enforced in every stage)

1. **CRS is explicit, always.** Report the CRS of every input on first
   contact. Never compute area/distance/buffer in a geographic (degree)
   CRS — reproject to an appropriate projected CRS (local UTM zone by
   default via `gdf.estimate_utm_crs()`; equal-area such as EPSG:6933 for
   global area statistics). If a CRS is undefined, stop and resolve it;
   never guess silently.
2. **Axis order discipline.** GeoJSON is lon/lat; many APIs and humans say
   lat/lon. Verify with a known landmark before pipeline-scale processing.
3. **Geometry validity before analysis.** Check `is_valid`; repair with
   `shapely.make_valid` (not `buffer(0)`, which can silently drop parts).
4. **Row-count accounting.** After every join/overlay/filter, report rows
   in vs rows out. Silent duplication or loss is the top geospatial bug.
5. **Spatial autocorrelation awareness.** Random train/test splits on
   spatial data leak. Any ML stage follows the canonical protocol in
   `ml-experiment-standards` → `references/spatial-cv-protocol.md`.
6. **Units in column names.** `area_ha`, `dist_km`, `elev_m` — never bare
   `area`. Unit confusion survives code review; column names don't lie.
7. **Visual + numeric verification.** Every spatial output gets both a
   summary table AND a quick map check (`.explore()`, a PNG, or GIS
   software). A confusion matrix cannot show spatially clustered errors.
8. **Reproducibility.** Pin package versions, seed randomness, log
   parameters. Intermediate artifacts go to GeoPackage or GeoParquet, never
   shapefile (10-char column truncation, 2 GB limit, no proper encoding).

## Internationalization note

Attribute tables in non-ASCII locales break naive string handling.
Canonical example: Turkish dotted/dotless I — `'İ'.lower()` yields a
2-character string in Python. Before any string matching on attributes,
apply a locale-aware normalization step and show `value_counts()` of
cleaned categorical fields. Prefer UTF-8 formats; legacy shapefiles may
carry cp1252/cp125x mojibake silently.

## Choosing the stack

Default to the open Python stack: GeoPandas + Shapely 2 + Rasterio +
xarray/rioxarray + PyProj. Route to PostGIS when data exceeds comfortable
memory (~millions of features) or needs concurrent/repeated querying; to
Earth Engine when the data is a planetary archive rather than local files.
Use GDAL CLI for bulk format conversion. If the user works in ArcGIS Pro or
QGIS, generate headless-runnable scripts (arcpy / PyQGIS) rather than click
instructions, and keep the analysis logic portable.

## Anti-patterns to catch early

- Buffering in degrees ("0.01 degree buffer") — reproject first.
- `EPSG:4326 → Web Mercator` area statistics — Mercator distorts area
  massively away from the equator.
- Joining datasets from different CRS without alignment.
- Treating a DEM's nodata value (-9999, 3.4e38) as real elevation.
- Classifying imagery without checking cloud/shadow masks.
- Reporting model accuracy without a spatially independent test set.

## Execution contract

- **Workflow:** clarify objective and deliverable; decompose the multi-stage problem; route each stage to the narrowest skill; declare handoffs and invariants; integrate and verify the final artifact.
- **Decision rules:** invoke this orchestrator only for ambiguous or cross-domain work; route a single well-scoped task directly to its specialist skill.
- **Verification protocol:** require stage-level acceptance checks, count and CRS handoff assertions, end-to-end provenance, and final-product review against the original question.
- **Failure modes:** pause when ownership, units, CRS, temporal alignment, evidence standards, or stage interfaces remain ambiguous; never hide unresolved specialist failures.
- **Deliverables:** pipeline plan, skill-routing table, stage inputs and outputs, verification gates, risk register, and final integration checklist.
- **Source freshness:** consult [the authoritative source registry](references/authoritative-sources.md) and the selected specialists' registries before fixing interfaces.
