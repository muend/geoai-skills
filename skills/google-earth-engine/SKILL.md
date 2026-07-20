---
name: google-earth-engine
description: >-
  Invoke when Earth Engine, GEE, ee., or geemap is named; when work needs its
  server-side catalog; or when choosing Earth Engine versus local xarray or
  desktop processing for a large area or long archive. Covers image
  collections, masking, compositing, reducers, zonal statistics, time series,
  classification, quota-aware batching, and exports. This is an execution
  platform skill; combine it with remote-sensing-analysis or change-detection
  when those skills own the scientific method.
license: MIT
metadata:
  version: "0.1.0"
  author: Muhammed Enes Duran
---

# Google Earth Engine

Purpose: use GEE's server-side model correctly. The recurring failure
modes are **client/server confusion** (calling `.getInfo()` in loops,
Python `if` on server objects), **unbounded computation** (timeouts from
unscaled reductions), and **silent default scales** (statistics computed
at the wrong resolution).

## Mental model — everything is deferred

`ee.Image`, `ee.ImageCollection`, `ee.FeatureCollection` are **server-side
descriptions**, not data. Nothing computes until an output is requested
(`getInfo`, export, map tile). Consequences:

- Never use Python `if`/`for` on server values — use `ee.Algorithms.If`
  sparingly, prefer `.map()` + filters. A Python loop that calls
  `.getInfo()` per element is the #1 GEE performance bug.
- `.getInfo()` blocks and transfers; use it for tiny scalars only.
  Anything sized → **Export** (to Drive/GCS/Asset).
- Debug with `.aggregate_array()`, `.first()`, `.limit(3)` probes — not by
  printing whole collections.

## Canonical pipeline (Sentinel-2 cloud-free composite)

```python
import ee
ee.Initialize(project="my-project")

aoi = ee.Geometry.Rectangle([27.0, 38.3, 27.4, 38.6])

def mask_s2(img):
    # Cloud Score+ is the current best practice (threshold ~0.5-0.65)
    cs = img.linkCollection(csplus, ["cs_cdf"]).select("cs_cdf")
    return img.updateMask(cs.gte(0.6))

csplus = ee.ImageCollection("GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED")
s2 = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
      .filterBounds(aoi)
      .filterDate("2025-05-01", "2025-09-30")
      .map(mask_s2))
composite = s2.median().clip(aoi)
ndvi = composite.normalizedDifference(["B8", "B4"]).rename("ndvi")
```

Collection choices: `S2_SR_HARMONIZED` (post-2022 offset harmonized),
`LANDSAT/LC08/C02/T1_L2` + friends (apply scale factors: optical
`*0.0000275 - 0.2`), `MODIS/061/...` for daily/coarse, ERA5-Land for
climate. Record collection IDs + date filters in the deliverable.

## Reducers and zonal statistics — scale is not optional

```python
stats = ndvi.reduceRegions(
    collection=districts,
    reducer=ee.Reducer.mean().combine(ee.Reducer.stdDev(), sharedInputs=True),
    scale=10,                    # ALWAYS explicit — native resolution
    tileScale=4,                 # raise when "computation timed out"
)
```

- `scale` defaults to the map zoom level in some paths — silently coarse
  statistics. Always set it to the data's native resolution (or state the
  deliberate coarsening).
- `bestEffort=True` silently degrades scale to fit limits — avoid in
  analysis; prefer `tileScale` + exports.
- Large reductions → `Export.table.toDrive`, not `.getInfo()`.
- Weighted vs unweighted reducers differ at polygon edges
  (`.unweighted()` for counts of whole pixels); state which you used.

## Time series

- Build per-period composites with a mapped function over
  `ee.List.sequence` of dates (monthly/seasonal medians), then reduce —
  don't export daily stacks you'll aggregate anyway.
- For per-pixel trends: `ee.Reducer.sensSlope()` (robust) or
  `linearFit`; harmonic regression (`.addBands` of sin/cos terms) for
  phenology. Mask by count of valid observations — trends from 4 pixels
  of 200 possible are noise; report the count band.
- For break detection at archive scale (LandTrendr/CCDC available in GEE),
  method selection follows `change-detection`.

## Classification in GEE

`ee.Classifier.smileRandomForest` covers most cases. Training samples via
`image.sampleRegions`; split train/test **spatially** (add a grid-cell
attribute and filter — random `randomColumn` splits leak; see
`ml-experiment-standards` → `references/spatial-cv-protocol.md`). Report
per-class accuracy from `errorMatrix`; area estimates from a classified
map still need design-based adjustment (`change-detection` / Olofsson).

## Exports and hand-off

- `Export.image.toDrive/toCloudStorage` with explicit `region`, `scale`,
  `crs`, `maxPixels`; use `crsTransform` when pixel alignment with an
  existing raster matters.
- Export > ~10⁸ pixels: shard by tiles or use `toAsset` intermediate.
- Hand off to the local Python stack (rasterio/xarray) via COG exports, or
  `xee` for xarray-native access; visualize interactively with `geemap`.

## Quotas and etiquette

Batch tasks queue (check task status; don't fire hundreds blindly).
Interactive requests time out at ~5 min — long jobs go to batch export.
Cache intermediate products as assets when a pipeline reuses them.

## Verification protocol

1. Probe: `composite.select("B4").projection().nominalScale().getInfo()`
   and band names — confirms scale/CRS assumptions before reductions.
2. Visual check in geemap at 2 zoom levels vs a basemap.
3. Cross-check one zonal statistic against a local computation on an
   exported clip (catches scale/masking discrepancies).
4. Report: collection IDs, date ranges, mask method + threshold, scale,
   reducer types.

## Pitfalls checklist

- `.getInfo()` inside a loop (move logic server-side).
- Missing `scale` in reduceRegion(s) → zoom-dependent statistics.
- Landsat C2 used without scale factors → reflectance > 1.
- `bestEffort=True` hiding resolution degradation.
- Median composite including cloudy pixels (mask BEFORE reduce).
- Python conditionals on server-side objects (always false-y).
- Trend maps without valid-observation-count masking.

## Execution contract

- **Workflow:** define collection and period; build a server-side mask and transform pipeline; test on a small region; compute; verify scale and projection; export reproducibly.
- **Decision rules:** use Earth Engine for planetary archives and scalable aggregation, local tools for sensitive or offline data, and batch exports for work beyond interactive limits.
- **Verification protocol:** probe bands, projection, scale, masks, and observation counts; inspect spatial samples; cross-check one exported statistic locally; record collection versions and parameters.
- **Failure modes:** stop for client-side loops, implicit scale, masked-pixel bias, quota-driven silent degradation, expired assets, or unbounded region operations.
- **Deliverables:** runnable script, collection and date manifest, mask and reducer parameters, task/export settings, verification evidence, and exported asset inventory.
- **Source freshness:** consult [the authoritative source registry](references/authoritative-sources.md) at execution time for catalog, API, quota, and policy changes.
