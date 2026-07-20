---
name: change-detection
description: >-
  Invoke whenever the primary question is what, where, or how much changed
  between times, including two-scene comparisons, deforestation, urban growth,
  disaster damage, and parcel-change audits. Covers bi-temporal differencing,
  post-classification comparison, adjusted area, and time-series trend/break
  analysis (BFAST/LandTrendr/CCDC-style). Invoke even when seasons, sensors,
  or processing levels are not comparable; diagnosing an invalid comparison
  is part of change analysis. Use remote-sensing-analysis for single-date
  preparation and add google-earth-engine only when GEE executes the work.
license: MIT
metadata:
  version: "0.1.0"
  author: Muhammed Enes Duran
---

# Change Detection & Spatio-temporal Analysis

Purpose: separate real surface change from the four great impostors —
misregistration, radiometric drift, phenology, and classification error.
Every method below exists to control one of them; skipping the controls
produces confident maps of nothing.

## Preconditions (where change detection is won or lost)

1. **Co-registration**: sub-pixel alignment between dates (AROSICS or
   manual tie-points). Half a pixel of shift creates edge-shaped phantom
   change everywhere. Verify: flicker-compare crisp features.
2. **Radiometric consistency**: same processing level (surface
   reflectance), same sensor if possible; if mixing sensors, harmonize
   (e.g., Landsat↔Sentinel-2 HLS) or use relative normalization (PIFs).
3. **Same season / phenological stage** for bi-temporal work — a May vs
   September pair "detects" summer. If season can't be matched, use
   composites or time-series methods instead.
4. **Cloud/shadow masks intersected across dates**; analyze only mutually
   valid pixels and report that coverage %.

## Method selection

| Situation | Method |
|---|---|
| Two dates, continuous "how much" | Index differencing (ΔNDVI, ΔNBR...) with statistical thresholding |
| Two dates, categorical "from-what-to-what" | Post-classification comparison (only with strong classifiers) |
| Two dates, multivariate robust | Change vector analysis (CVA); MAD/iMAD for sensor-robust detection |
| Dense stack, gradual + abrupt | Trend + break analysis (BFAST/LandTrendr/CCDC family; at archive scale → `google-earth-engine`) |
| Structure change (buildings) | DL bi-temporal segmentation (siamese U-Net) → `geo-deep-learning` |
| SAR pairs (clouds, disasters) | Log-ratio of calibrated backscatter + speckle handling |
| Vector vintages (parcels, buildings) | Geometry+attribute diff with tolerance (below) |

## Thresholding — never eyeball it

Difference images need a defensible threshold: μ ± k·σ on the difference
histogram (report k), Otsu when bimodal, or supervised thresholds
calibrated on labeled change/no-change samples. Deliver the histogram with
the chosen cut marked. Sensitivity: report changed-area at k-0.5 and
k+0.5; if the story flips, the detection is fragile — say so.

## Post-classification comparison (PCC) — handle with care

PCC error compounds: two 90%-accurate maps yield ≤ ~81% change accuracy,
and biased errors create systematic false transitions. Rules:

- Use ONE classifier trained on both dates' imagery (same legend, same
  features) rather than two independent legacy maps.
- Build the full **transition matrix** (from-class → to-class areas), not
  just a change/no-change binary — impossible transitions (water→forest
  in 1 year) are your error detector.
- Apply a minimum mapping unit consistent across dates before differencing.

## Time-series (dense stack) analysis

- Build a gap-filled, cloud-masked index stack (xarray, time dimension).
- Decompose trend + seasonality + breaks; per-pixel linear trends need
  significance testing (Mann-Kendall + Sen's slope for monotonic trends —
  and FDR correction across millions of pixels, or your "greening map" is
  noise).
- Label break DATES, not just presence — timing is usually the analytic
  payload (when did clearing start?).
- Validate detected breaks against known events (fires, construction
  permits, disaster dates) wherever records exist.

## Vector change audit (two vintages of the same layer)

- Match features by stable ID if it exists; else spatial matching with IoU
  threshold (report it).
- Classify: added / removed / geometry-changed (area delta > tolerance) /
  attribute-changed. Tolerances absorb digitization jitter — 1-2 m for
  cadastre-grade, more for digitized-from-imagery.
- Sum area deltas by class and reconcile totals; unexplained residual =
  matching bugs.

## Accuracy assessment (the deliverable's spine)

Change is rare, so random sampling wastes effort on stable pixels — use
**stratified sampling** (strata: change/no-change or per-transition) with
good-practice area estimation (Olofsson et al. protocol): report
user's/producer's accuracy per stratum AND **area estimates with
confidence intervals** adjusted for map error. A raw pixel count of the
change map is a biased area estimate — always say the adjusted number.

## Reporting template

```
## Change: <phenomenon>, <T1> → <T2 or period>
- Data: <sensor/level>, co-registration RMSE: <px>, valid overlap: <%>
- Method: <...> threshold/params: <...> (sensitivity: <stable/fragile>)
- Transitions: <matrix or top-5 list with areas ± CI>
- Accuracy: stratified n=<>, UA/PA per class, adjusted areas ± CI
- Impostor controls: season <matched?>, radiometry <harmonized?>
```

## Pitfalls checklist

- Phantom edge-change from misregistration.
- Seasonal difference sold as land cover change.
- PCC with two independently produced legacy maps.
- Threshold chosen "because it looked right", no sensitivity.
- Raw changed-pixel counts reported as area (no error-adjusted estimate).
- Trend maps without multiple-testing control.
- SAR change on unfiltered linear-power images.

## Execution contract

- **Workflow:** define the change question; harmonize extent, season, radiometry, resolution, and registration; select method; estimate change; validate; report uncertainty.
- **Decision rules:** use direct differencing only for comparable continuous signals, post-classification comparison for stable class legends, and time-series methods when a dense temporal stack exists.
- **Verification protocol:** quantify co-registration, valid overlap, threshold sensitivity, transition accounting, and accuracy-adjusted area with confidence intervals.
- **Failure modes:** reject causal change claims when season, sensor, clouds, registration, or independent map errors can explain the signal.
- **Deliverables:** change map, transition or trend table, parameter record, validation sample and metrics, adjusted-area estimate, and limitations.
- **Source freshness:** consult [the authoritative source registry](references/authoritative-sources.md) before using version-sensitive products or APIs and record the checked date.
