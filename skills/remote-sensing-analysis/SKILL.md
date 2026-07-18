---
name: remote-sensing-analysis
description: >-
  Search, load, correct, and analyze satellite and aerial imagery:
  Sentinel-1/2, Landsat, MODIS, drone orthomosaics, spectral indices (NDVI,
  NDWI, NDBI...), cloud masking, compositing, land cover classification, SAR,
  and time-series extraction. Use for imagery acquisition, preprocessing, and
  classical remote-sensing analysis. Route change as the primary deliverable
  to change-detection, neural model training or inference to
  geo-deep-learning, and planetary or multi-decade server-side execution to
  google-earth-engine.
license: MIT
metadata:
  version: "0.1.0"
  author: Muhammed Enes Duran
---

# Remote Sensing Analysis

Purpose: turn raw Earth observation imagery into defensible analytical
products. The failure modes here are subtle — uncorrected DNs treated as
reflectance, clouds counted as land cover change, indices computed on the
wrong bands — so this skill front-loads the checks.

## Data access (STAC-first)

Search via STAC APIs rather than per-provider portals; the workflow is
uniform and scriptable:

```python
import pystac_client
import odc.stac

catalog = pystac_client.Client.open("https://earth-search.aws.element84.com/v1")
items = catalog.search(
    collections=["sentinel-2-l2a"],
    bbox=[27.0, 38.3, 27.4, 38.6],
    datetime="2025-05-01/2025-09-30",
    query={"eo:cloud_cover": {"lt": 20}},
).item_collection()
ds = odc.stac.load(items, bands=["red", "nir", "scl"], resolution=10, chunks={})
```

Key collections: `sentinel-2-l2a` (10 m optical, surface reflectance),
`landsat-c2-l2` (30 m, 1982→), `sentinel-1-grd` (SAR, weather-independent).
Microsoft Planetary Computer mirrors most (needs `planetary_computer`
signing). For continental/global extents or decades-long stacks, route to
`google-earth-engine` instead of downloading. Record collection + item IDs +
search parameters for reproducibility.

## Processing-level discipline

| Level | Meaning | Analysis-ready? |
|---|---|---|
| L1C / L1TP | Top-of-atmosphere (TOA) | Indices OK-ish; cross-date comparison risky |
| **L2A / L2SP** | Surface reflectance (BOA) | Yes — default choice |
| GRD (SAR) | Detected amplitude | Needs terrain correction + speckle filter |

Always state which level you used. Never mix TOA and BOA scenes in one
composite or time series. Landsat Collection 2 L2 needs its scale factors
applied (`reflectance = DN * 0.0000275 - 0.2`).

## Cloud and quality masking — before anything else

- Sentinel-2: mask with SCL band (drop classes 3 cloud shadow, 8-9 clouds,
  10 cirrus, 11 snow — keep 4 vegetation, 5 bare, 6 water, 7 unclassified
  with care).
- Landsat C2: decode `QA_PIXEL` bitfields (cloud, shadow, cirrus bits).
- Report the % of valid pixels after masking per scene; scenes below ~60%
  valid usually deserve exclusion.
- For gap-free products, build median composites over a season rather than
  cherry-picking single scenes.

## Spectral indices

Compute on surface reflectance, guard against division by zero, and name
bands explicitly — band **numbers differ across sensors** (NIR is B8 on
Sentinel-2, B5 on Landsat 8/9):

```python
import numpy as np
import xarray as xr

def normalized_diff(a: xr.DataArray, b: xr.DataArray) -> xr.DataArray:
    """(a - b) / (a + b) with zero-denominator protection."""
    return xr.where(a + b == 0, np.nan, (a - b) / (a + b))

ndvi = normalized_diff(ds.nir, ds.red)     # vegetation
ndwi = normalized_diff(ds.green, ds.nir)   # open water (McFeeters)
ndbi = normalized_diff(ds.swir16, ds.nir)  # built-up
```

Interpretation guardrails: NDVI thresholds are scene- and season-dependent;
never hardcode "NDVI > 0.3 = vegetation" without checking the histogram.
Water confuses NDBI; shadows mimic water in NDWI — cross-check indices
against each other and against true-color.

## Classification workflow

1. Define a legend with mutually exclusive, imagery-separable classes.
2. Collect training samples spatially spread across the scene; record them
   as a versioned vector file.
3. Features: bands + indices + texture (GLCM) + temporal statistics if
   multi-date. For deep learning routes, hand off to `geo-deep-learning`.
4. Validate with a **spatially independent** test set (see
   `ml-experiment-standards` → `references/spatial-cv-protocol.md`) and
   report per-class F1/IoU plus a confusion matrix — overall accuracy alone
   hides rare-class failure.
5. Map the errors: a spatial plot of misclassifications reveals systematic
   problems (terrain shadow, urban/bare confusion) that global metrics hide.

## SAR notes (Sentinel-1)

Preprocess: orbit file → thermal noise removal → calibration (σ⁰) →
terrain correction (Range-Doppler with a DEM) → speckle filter (Lee/Refined
Lee) → dB conversion. Work in dB for statistics; VV/VH ratio is a strong
water/vegetation discriminator. SAR sees through clouds — prefer it for
flood mapping and continuous monitoring.

## Pitfalls checklist

- Comparing scenes across dates without consistent atmospheric correction.
- Ignoring 20 m→10 m band mixing on Sentinel-2 (B11/B12 are natively 20 m).
- Computing indices on integer DNs without scale factors → nonsense ranges.
- Median composites of SAR in linear units (do statistics in dB).
- Training and test pixels from the same field/polygon → leaked accuracy.
- Forgetting nodata masks after reprojection (edges become zeros → fake
  land cover).

## Execution contract

- **Workflow:** define phenomenon and scale; select sensor, product level, and dates; harmonize calibration, masks, CRS, and resolution; derive features; analyze; validate spatially; publish provenance.
- **Decision rules:** use this skill for imagery preparation and classical analysis, change detection for explicit temporal differencing, deep learning for neural training, and Earth Engine for archive-scale execution.
- **Verification protocol:** inspect masks and valid counts, confirm scale factors and band resolution, overlay outputs, use spatially independent validation, map errors, and test seasonal or sensor sensitivity.
- **Failure modes:** reject results for cloud or shadow leakage, incomparable processing levels, resampling artifacts, label leakage, nodata contamination, or claims beyond sensor resolution.
- **Deliverables:** analysis-ready imagery or features, processing manifest, masks, derived products, validation metrics and error map, reproducible code, and limitations.
- **Source freshness:** consult [the authoritative source registry](references/authoritative-sources.md) at execution time for product, calibration, and catalog changes.
