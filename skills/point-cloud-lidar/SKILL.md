---
name: point-cloud-lidar
description: >-
  LiDAR and point cloud processing: PDAL pipelines, LAS/LAZ/COPC handling,
  ground classification, DTM/DSM/CHM generation, canopy and building
  metrics, and photogrammetric (SfM) point clouds. Use when the primary input
  is LAS, LAZ, COPC, LiDAR, or an unstructured 3D point cloud. This skill owns
  vertical datum agreement, co-registration and the vertical-accuracy budget
  when two acquisitions are differenced with comparability not yet established;
  once datum, geoid and accuracy are documented, a subsidence or
  elevation-change question is change-detection's. Route a derived DEM, DTM,
  DSM or CHM to terrain-hydrology unless point-level classification,
  comparability, or metrics remain in scope.
license: MIT
metadata:
  author: Muhammed Enes Duran
---

# Point Clouds & LiDAR

Purpose: from raw returns to defensible elevation and structure products.
The recurring failure modes: **trusting vendor classification blindly**,
**mixing return types in surfaces** (DSM from last returns, DTM with
vegetation), and **ignoring point density** when choosing output
resolution.

## First contact with any cloud

```bash
pdal info input.laz --summary        # counts, bounds, CRS, classes, returns
```

Report before touching anything: point count, density (pts/m² — decides
achievable raster resolution), CRS (horizontal AND vertical datum —
ellipsoidal vs orthometric heights differ by the geoid undulation, tens of
meters in places), classification present?, return numbers present?,
flight-line overlap artifacts. A cloud without CRS metadata: resolve from
the provider, never assume.

## Format and scale

| Format | Use |
|---|---|
| **LAZ** | Compressed interchange/archive — default |
| **COPC** (cloud-optimized LAZ) | Streaming/HTTP range access, web viewers |
| LAS | Only when a tool can't read LAZ |
| Entwine/EPT | Massive multi-tile collections, indexed |

Tile large collections; process per-tile with buffered edges (~2× search
radius) to avoid seam artifacts in filters and surfaces; drop the buffer
on write.

## PDAL pipeline pattern

```json
{
  "pipeline": [
    "input.laz",
    {"type": "filters.reprojection", "out_srs": "EPSG:32636"},
    {"type": "filters.outlier", "method": "statistical",
     "mean_k": 8, "multiplier": 2.5},
    {"type": "filters.smrf", "slope": 0.15, "window": 18.0,
     "threshold": 0.5, "scalar": 1.2},
    {"type": "writers.las", "filename": "classified.laz",
     "extra_dims": "all"}
  ]
}
```

Run: `pdal pipeline pipeline.json`. Denoise BEFORE ground classification
(low outliers below ground destroy SMRF/CSF); tune `slope` up for steep
terrain, `window` to the largest non-ground object (big buildings need
bigger windows).

## Ground classification & DTM

- If vendor class 2 (ground) exists: **audit it** on 2-3 cross-sections
  (bridges, dense canopy, steep slopes) before trusting; reclassify where
  it fails.
- Algorithms: SMRF (PDAL default, robust), CSF (cloth simulation, good in
  steep forest). Parameters are terrain-dependent — show a cross-section
  plot as evidence, not just the parameter list.
- DTM from ground-only points; interpolation: TIN → raster (standard for
  DTM) or IDW for dense clouds. Output resolution ≥ ~1/√density; a 0.5 m
  DTM from 1 pt/m² data is invented detail.
- DSM from **first returns / highest-point** binning. CHM = DSM − DTM,
  clamp negatives to 0, and use a pit-free algorithm for forestry (naive
  CHMs are pocked by within-crown pits).

## Structure metrics

- **Forestry**: height percentiles (p95 ≈ canopy height), canopy cover
  (first returns > 2 m / all first returns), density metrics per grid cell
  or plot; normalize heights against the DTM first (`filters.hag_dem` or
  `filters.hag_nn`). Individual tree detection: local maxima on pit-free
  CHM + watershed segmentation — validate count against field plots or
  manual photo-interpretation samples.
- **Buildings**: class 6 or planar-patch extraction; building height =
  p90(roof points HAG); footprint fusion with cadastre/OSM polygons via
  zonal statistics on HAG.
- Downstream terrain analysis (slope, watersheds) → `terrain-hydrology`;
  DL on point clouds or derived rasters → `geo-deep-learning`.

## SfM/photogrammetric clouds — not LiDAR

Drone photogrammetry clouds have no returns, no canopy penetration
(ground under vegetation is guessed), correlated noise, and possible doming
from poor camera calibration. A "DTM" from SfM over forest is a canopy
model. State the sensor type in every deliverable; use LiDAR-specific
claims (penetration, return metrics) only for LiDAR.

## Vertical datum: resolve, transform, record

Every elevation product carries three obligations, and the third is the one
that gets skipped. **Stating the datum in your answer is not recording it.**
A height product whose vertical datum lives only in a chat reply is
indistinguishable from one with no datum at all the moment the file is
handed to anyone else.

1. **Resolve.** Read the vertical CRS from the header/VLR. Where it is
   missing or contradicted, resolve it against acquisition metadata (vendor
   flight report, project spec) or diagnose it: a tile-wide constant offset
   matching the local geoid undulation is the ellipsoidal-vs-orthometric
   fingerprint. Never infer a datum from elevation magnitude alone.
2. **Transform.** Apply an explicit, named transformation — a compound CRS
   plus geoid model through `filters.reprojection`, or a fitted per-tile
   offset when no geoid grid is available. Re-difference the overlaps
   afterwards and confirm strips agree within noise.
3. **Record it into the output, not just the reply.** Every delivered
   product must carry, in machine-readable form:
   - the compound or vertical CRS written into the file itself (LAS/LAZ
     header VLR, GeoTIFF CRS, or PROJJSON in the sidecar);
   - the **geoid model name and version** actually applied (e.g. EGM2008,
     GEOID18) and the transformation pipeline or EPSG operation code;
   - the **per-tile offsets applied**, where correction was per tile, with
     the control or reference each was fitted against;
   - the source of truth used to resolve an originally missing datum;
   - the residual strip-edge disagreement after correction.

   Emit this as a sidecar (`*.prj`/PROJJSON, a metadata JSON, or embedded
   raster tags) alongside the product, and never publish a height product
   whose vertical datum is unresolved. If the datum cannot be resolved,
   deliver the product labelled provisional with the unresolved datum
   recorded in the same metadata block — silence is not an option.

## Verification protocol

1. Cross-sections (2-3, including a building edge and a vegetated slope):
   ground class hugs terrain, DSM caps surface.
2. DTM minus known control points / national DEM: report RMSE and check
   for a constant offset = vertical datum mismatch.
3. Hillshade the DTM — classification artifacts (pits, pimples,
   flight-line stripes) are instantly visible.
4. Report density, CRS + vertical datum, classifier + parameters, and
   output resolution rationale in the answer — **and** confirm the verified
   vertical datum, geoid model, and transformation were written into the
   output metadata before the product is considered delivered.

## Pitfalls checklist

- Ellipsoidal heights delivered as orthometric (whole product offset by
  the geoid).
- Vertical datum resolved during the audit but never written into the
  delivered product's metadata — the next consumer inherits the same
  ambiguity you just spent the analysis removing.
- DTM resolution finer than point density supports.
- Vendor ground class trusted under dense canopy.
- CHM with negative values or crown pits (no pit-free processing).
- Per-tile processing without buffers → seam lines in derivatives.
- Outlier filter run AFTER ground classification.
- SfM cloud treated as canopy-penetrating LiDAR.

## Execution contract

- **Workflow:** inspect header, CRS, vertical datum, density, classes, and returns; tile with buffers; filter noise; classify; derive products; mosaic; validate in 3D and cross-section.
- **Decision rules:** use point-cloud workflows when return-level 3D evidence matters, terrain workflows after a validated DEM exists, and separate assumptions for LiDAR versus SfM clouds.
- **Verification protocol:** reconcile point counts and classes, inspect buffered seams and cross-sections, compare elevations to control, hillshade derived terrain, and report density-supported resolution.
- **Failure modes:** stop for unknown vertical datum, insufficient density, corrupt classification, tile seams, unbounded outliers, or product resolution finer than sampling supports. Never resolve a vertical datum and then ship the product without that datum and its transformation recorded in the output metadata.
- **Deliverables:** validated cloud or derived DTM/DSM/CHM, pipeline parameters, CRS and vertical datum, density and class report, QA graphics, accuracy metrics, and limitations. The verified vertical datum, the geoid model and transformation applied, and any per-tile offsets are written into the output metadata or a sidecar, not only into the answer text.
- **Source freshness:** consult [the authoritative source registry](references/authoritative-sources.md) before applying format, quality, or processing rules and record the checked date.
