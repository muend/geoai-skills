# Spatial cross-validation protocol (canonical)

This is the single authoritative statement of the spatial split rule for
this repo. Other skills (`geoai-orchestrator`, `geo-deep-learning`,
`remote-sensing-analysis`, `geostatistics-interpolation`,
`google-earth-engine`) link here instead of restating it.

## Why random splits are fraudulent on spatial data

Tobler's first law: near things are more related than distant things.
Nearby observations (adjacent pixels, chips, parcels, stations) are
near-duplicates. A random train/test split scatters near-duplicates across
both sides, so the model is evaluated on data it has effectively seen.
Reported metrics inflate — often dramatically (10+ points of mIoU/accuracy
in segmentation tasks is common) — and the model fails on genuinely new
areas. This is not a minor bias; it is the difference between a publishable
result and a fake one.

## The rule

**Split by geographic block, scene, or region — never by random
observation.** The unit of assignment must be spatially coherent and larger
than the autocorrelation range of the phenomenon.

## Practical recipe

1. **Assign block IDs.** Overlay a coarse grid over the study area (block
   size ≥ the autocorrelation range — estimate from a variogram of the
   target or a key predictor; when unknown, use a generous size, e.g.
   several km for 10 m imagery tasks).

   ```python
   import numpy as np

   block = 5_000  # meters — must exceed autocorrelation range
   gdf["block_id"] = (
       (gdf.geometry.x // block).astype(int).astype(str)
       + "_"
       + (gdf.geometry.y // block).astype(int).astype(str)
   )
   ```

2. **Split blocks, not rows.** `GroupKFold` (or `StratifiedGroupKFold`)
   with `groups=block_id`; for a single hold-out, sample block IDs.

   ```python
   from sklearn.model_selection import GroupKFold

   for tr, te in GroupKFold(n_splits=5).split(X, y, groups=gdf["block_id"]):
       ...
   ```

3. **Verify zero spatial overlap.** Compute the minimum distance between
   train and test geometries per fold; it should be ≥ the intended
   separation. For chips: assert no train chip's bounds intersect any test
   chip's bounds.

4. **Document the split** in run metadata: block size, n blocks per fold,
   min train-test distance, and the map of fold assignment (a plotted fold
   map is the fastest reviewer check).

## Variants

- **Scene/region hold-out**: for generalization claims across areas, hold
  out entire scenes/regions/cities — the strongest and most honest test.
- **Buffered leave-one-out (spatial LOO)**: for small n point datasets
  (interpolation), exclude a buffer around each test point from training.
- **Grouped non-spatial structure**: if observations also cluster by
  non-spatial keys (patient, farm, survey team), group by the coarser of
  the two structures — or both.
- **Time + space**: when data are spatio-temporal, block in both
  dimensions; a model tested on the same place in a different month has
  leaked place.

## Honest reporting

Report the spatially blocked metric as THE metric. If you also computed a
random-split metric, you may show it only as an explicit "upper bound
under leakage" comparison — never as the headline number. Expect the
blocked number to be worse; that is the point.
