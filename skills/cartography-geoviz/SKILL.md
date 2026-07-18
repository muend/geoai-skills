---
name: cartography-geoviz
description: >-
  Design publication-quality maps and interactive geovisualizations:
  choropleths, proportional symbols, bivariate maps, flow maps, raster
  rendering, small multiples, web maps (Folium/MapLibre/Kepler.gl), and
  static figures. Use when cartographic design or delivery is requested,
  including classification, color, legends, display projections,
  interaction, and accessibility. Trigger on "make a map", "choropleth",
  "web map", or map-review requests. Do not trigger merely because another
  analysis creates a temporary diagnostic plot.
license: MIT
metadata:
  version: "0.1.0"
  author: Muhammed Enes Duran
---

# Cartography & Geovisualization

Purpose: maps that communicate honestly. Cartographic choices (class
breaks, ramps, normalization, projection) can manufacture or hide
patterns; this skill treats them as analytical decisions with stated
rationale, not styling.

## The first three questions

1. **What's the message?** One map = one message. If two variables
   compete, consider small multiples or a bivariate scheme — not twelve
   legend classes.
2. **Normalized?** Choropleths of raw counts are population maps in
   disguise. Rates, densities, or per-capita for area-based color; raw
   magnitudes → proportional symbols instead.
3. **Static or interactive?** Print/PDF/paper → matplotlib/QGIS layout;
   exploration/stakeholders → Folium/MapLibre; big point data →
   Kepler.gl/deck.gl (GPU).

## Thematic map type selection

| Data | Map type |
|---|---|
| Rate/ratio by polygon | Choropleth |
| Count/magnitude by place | Proportional/graduated symbols |
| Two related rates | Bivariate choropleth (3×3 max) |
| Individual-level density | Dot density or KDE surface (label bandwidth) |
| Continuous field (raster) | Classified or stretched render + hillshade context |
| Movement/OD | Flow map (width∝volume), aggregate to avoid hairballs |
| Change over time | Small multiples > animation for analysis; animation for outreach |

## Classification — the honesty lever

- **Natural breaks (Jenks)**: default for skewed data; breaks are
  data-specific, so NOT comparable across maps/dates.
- **Quantiles**: guaranteed color balance; can split near-identical values.
- **Equal interval**: comparable and intuitive; fails on skew.
- **Manual/defined**: the ONLY correct choice for map series (same breaks
  across all dates/regions) and for domain thresholds (WHO limits, slope
  classes).
- 5±2 classes; show the histogram with breaks in the workflow; state the
  scheme in the caption/metadata. Try two schemes — if the story changes
  materially, the story is the classification, and the reader must be told.

## Color

- Ramps from ColorBrewer/`cmcrameri`/viridis family: sequential (ordered),
  diverging (meaningful midpoint — zero, mean, threshold), qualitative
  (categories, ≤ 8).
- Colorblind-safe by default (~8% of male readers); never red-green
  diverging without checking a CVD simulator.
- NoData ≠ zero: render as neutral gray with its own legend entry, never
  the ramp's low end.
- Muted basemaps (CartoDB Positron) under thematic layers — the basemap
  must never win.

## Projection for display

- Web tiles = Web Mercator: fine for city scale; area comparisons at
  continental scale on Mercator are visual lies — use equal-area
  projections (Albers, Mollweide, Equal Earth) for static thematic maps of
  large extents.
- National mapping → the national grid; polar work → polar stereographic.
- Label the projection on publication maps.

## Required furniture (publication static maps)

Title (the message, not the filename), legend (units!, sensible number
formatting), scale bar (projected CRS only — degrees have no fixed scale),
north arrow (only when north isn't up or the audience expects it), data
source + date + projection + author, and an inset locator map for
unfamiliar regions.

```python
# GeoPandas static map core
ax = gdf.plot(column="rate_per_1k", scheme="naturalbreaks", k=5,
              cmap="YlGnBu", legend=True, edgecolor="white", linewidth=0.3,
              missing_kwds={"color": "#d9d9d9", "label": "No data"})
ax.set_axis_off()
```

Export: 300 dpi PNG/PDF for print; SVG when editors will touch it; COG +
style for GIS handoff.

## Interactive maps

- Folium/MapLibre: tooltips with formatted values, layer control, sensible
  initial bounds (`fit_bounds`), legend included (Folium needs a manual
  HTML/branca legend — don't ship without one).
- Performance: >~50k vector features → tile it (tippecanoe → PMTiles) or
  switch to deck.gl/Kepler; never dump 500k GeoJSON features into Leaflet.
- Every popup number formatted (thousands separators, units, rounding
  matched to precision honesty).

## Verification protocol

1. Squint test: does the message survive at thumbnail size?
2. CVD simulation pass.
3. Legend audit: units, rounding, class edges non-overlapping.
4. Cross-check 3 features' rendered values against the attribute table
   (classification bugs are silent).
5. For map series: identical breaks, ramp, and extent across panels.

## Pitfalls checklist

- Raw-count choropleth (population in disguise).
- Jenks breaks compared across two dates.
- Red-green diverging ramp, unlabeled midpoint.
- NoData painted as the lowest class.
- Scale bar on an unprojected (degree) map.
- Continental-area comparisons on Web Mercator.
- Interactive map with no legend or units.

## Execution contract

- **Workflow:** inspect audience, data semantics, scale, and output medium; select projection, normalization, classification, and visual hierarchy; render; verify; export.
- **Decision rules:** choose map type from the analytical question, normalize counts when exposure differs, and keep breaks fixed for comparisons.
- **Verification protocol:** run the five checks above and reconcile rendered values, units, class edges, and missing-data treatment against the source.
- **Failure modes:** stop or qualify delivery when denominators, CRS, units, accessibility, or cross-panel comparability are unresolved.
- **Deliverables:** final map, legend and units, data/source note, projection and classification rationale, accessibility note, and reproducible style or code.
- **Source freshness:** consult [the authoritative source registry](references/authoritative-sources.md) before using version-sensitive APIs and record the checked date.
