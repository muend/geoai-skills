---
name: mcda-suitability-analysis
description: >-
  Multi-criteria decision analysis for spatial site selection and
  suitability mapping: AHP with consistency checking, weighted overlay,
  criteria standardization, constraint masking, and sensitivity analysis.
  Use when multiple spatial criteria must become a ranked suitability
  surface or site shortlist. Trigger on "suitability", "AHP", "weighted
  overlay", or "criteria weights". Route travel-time service placement and
  location-allocation to network-accessibility-analysis.
license: MIT
metadata:
  version: "0.1.0"
  author: Muhammed Enes Duran
---

# MCDA & Suitability Analysis

Purpose: produce suitability maps whose weights, scales, and assumptions are
explicit, consistent, and stress-tested. A suitability map without a
sensitivity analysis is an opinion with a legend.

## Workflow

1. **Structure**: goal → criteria (factors) → constraints. Constraints are
   binary masks (legal exclusions, water bodies, slope > threshold) applied
   at the END by multiplication; factors are continuous and weighted.
   Keep them apart — encoding a constraint as a heavily-weighted factor is
   a classic error that lets forbidden areas score "acceptable".
2. **Criteria layers**: each factor as a raster on a COMMON grid (same CRS,
   extent, cell size, snap). Resample categorical layers with nearest,
   continuous with bilinear; document each.
3. **Standardization** to a common suitability scale (0-1 or 0-255):
   - Linear min-max for monotonic "more is better/worse".
   - Fuzzy membership (sigmoid/linear with control points) when suitability
     saturates — justify control points from domain knowledge.
   - Categorical layers: explicit reclass table, shown to the user.
   Direction check: confirm for EVERY layer whether high raw value means
   high or low suitability (slope: low=good; distance-to-road: usually
   low=good). Direction bugs survive to the final map invisibly.
4. **Weights** (AHP below, or direct/ranked methods with rationale).
5. **Aggregation**: weighted linear combination (WLC) default; OWA when
   the decision-maker's risk attitude (AND-like vs OR-like) matters.
6. **Constraint mask** multiply; classify the result (equal interval or
   quantiles — say which and why); **sensitivity analysis**; validate
   against known good/bad sites if any exist.

## AHP with consistency enforcement

Pairwise comparisons on Saaty's 1-9 scale; weights from the principal
eigenvector; consistency ratio (CR) must be < 0.10 or the matrix goes back
for revision. Run `scripts/ahp_weights.py` to compute weights + CR from a
reciprocal comparison matrix (it validates reciprocity and reports λ_max).

Practices: elicit comparisons pair by pair with verbal anchors ("moderately
more important" = 3); with multiple experts, aggregate judgments by
geometric mean BEFORE computing weights; report the full matrix, weights,
λ_max and CR in the deliverable. If CR ≥ 0.10, identify the most
inconsistent triad and ask the expert to revisit it — do not silently
massage numbers.

## Aggregation

```python
suit = np.zeros_like(factors[0], dtype="float32")
for w_i, f in zip(weights, factors):   # factors already standardized 0-1
    suit += w_i * f
suit *= constraint_mask                 # binary 0/1, applied last
```

OWA variant: sort factor values per cell and apply order weights — full
AND (min) to full OR (max) continuum; use when stakeholders disagree on
risk tolerance and show 2-3 scenarios.

## Sensitivity analysis — mandatory

A result that flips with a small weight change is not a result:

- **One-at-a-time**: perturb each weight ±20% (renormalize), recompute,
  report % of area changing suitability class and a stability map (cells
  that never change class across perturbations).
- **Scenario**: 2-3 alternative weight sets from different stakeholder
  priorities; present side-by-side.
- If a Monte Carlo budget exists: sample weights from Dirichlet around the
  AHP vector; per-cell probability of "highly suitable" is a far stronger
  product than a single map.

## Deliverable standard

Suitability map (classified + continuous), constraint mask map, weights
table with CR, standardization functions per criterion (with direction),
sensitivity/stability summary, and limitations paragraph (data currency,
resolution, criteria omitted). Route cartography to `cartography-geoviz`;
network-access criteria come from `network-accessibility-analysis`.

## Pitfalls checklist

- Direction inversion on a criterion (the silent killer — double-check
  distance-based factors).
- Mixing resolutions without declaring the resampling rule.
- CR ignored or unreported.
- Constraints blended as weights → forbidden zones scored medium.
- Classifying with quantiles then reading them as absolute suitability.
- No sensitivity analysis; single map presented as truth.

## Execution contract

- **Workflow:** define decision and stakeholders; separate constraints from factors; standardize criteria; elicit and validate weights; aggregate; test sensitivity; communicate uncertainty.
- **Decision rules:** use MCDA for transparent criteria-ranked surfaces, network analysis for route-constrained access, and optimization when discrete placement or capacity decisions dominate.
- **Verification protocol:** check criterion direction and alignment, AHP consistency, constraint enforcement, weight and threshold perturbations, and stable-versus-fragile areas.
- **Failure modes:** reject the model when criteria double-count the same construct, weights lack provenance, constraints leak into compensation, or rankings collapse under plausible perturbations.
- **Deliverables:** continuous and classified suitability maps, constraints, criteria transformations, weights and consistency ratio, sensitivity results, and limitations.
- **Source freshness:** consult [the authoritative source registry](references/authoritative-sources.md) before applying methods or implementation APIs and record the checked date.
