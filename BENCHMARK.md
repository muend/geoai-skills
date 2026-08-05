# Routing Benchmark

**This suite is superseded.** The figures on this card — **100% routing
precision**, **92.37% routing recall**, **93.67% full-route accuracy** — were
measured on suite `f03e327a57d2…`. Every `SKILL.md` has since been edited, so
the repository's current suite is different and **has not been measured**.
These are routing results, not claims about answer quality.

Read the numbers below as evidence about the tree that was measured, not about
the tree you are downloading. What changed and why is in
[What retired this suite](#what-retired-this-suite).

| Field | Value |
|---|---|
| Suite state | `superseded` — the shipped source tree has moved on |
| Runtime | Claude Code `2.1.214` |
| Model | `claude-sonnet-5` |
| Skills | 18 |
| Suite | 158 cases: 118 positive, 40 negative |
| Suite SHA-256 | `f03e327a57d2faa70ed31f0b3920355f31527991626992b5fc0add3edbace7f9` |
| Run date | 2026-08-04 |
| Judge | None; routing is derived deterministically from recorded activations |
| Judge prompt/schema | n/a for routing-only scoring; run/result schema version 1 |
| Retry policy | Primary records retained; no retry replacement |
| Human review | All 9 false negatives, the 1 incomplete-route case, and all 7 execution errors inspected |
| Evidence | [Sanitized run package](benchmarks/claude-code-2.1.214--claude-sonnet-5--f03e327a57d2/) |

## What retired this suite

Five deliberate edits, made together so a single paid run can measure them all.
Four of the five exist because this run found them.

| Change | Why | Measured? |
|---|---|---|
| `change-detection` no longer claims prompts whose blocker is sensor or processing-level comparability | Its description read "Invoke even when seasons, sensors, or processing levels are not comparable" — that one conjunction caused 4 of the 9 false negatives below | **No** |
| `point-cloud-lidar` now owns cross-acquisition vertical datum comparability | The datum axis had no owner, so `change-detection` took it by default | **No** |
| `remote-sensing-analysis` encodes the Sentinel-2 Baseline 04.00 `BOA_ADD_OFFSET` discontinuity | Two L2A scenes across 2022-01-25 pass the existing L1C/L2A check while their DNs sit 1000 apart | **No** |
| `metadata.version` removed from all 18 skills | Read by nothing, reported as `skill_metadata_ignored` by the OpenAI portal, and drifted at `0.1.0` across three releases | n/a |
| `arcgis-pro-automation` gained its missing `license` field | The only skill without one | n/a |

The first three are **hypotheses, not results.** A boundary fix is not fixed
until it is measured, and it cannot be measured against the cases below: this
run spent the held-out half, so re-scoring the same 158 cases after editing the
descriptions they exposed would be iteration presented as confirmation. The
v0.4 run needs cases written for the boundary and a fresh dev / held-out split.

Note what this table does *not* say. It does not say routing improved. Until
the v0.4 run lands, the honest position is that the repository has no current
measurement of itself.

## What the v0.4 run will and will not be able to show

Nine boundary probes were added for it, taking the suite to **167 cases**, and
the split was rebuilt (assignment `b2ab0305ffc8…`, 105 dev / 62 held-out).
They are deliberately adversarial: three present a comparability blocker
disguised as a clean change question, two guard against over-correction by
wrapping a genuine change question in the vocabulary of a blocker, and four
probe the baseline-offset content in both error directions — failing to apply
the offset, and applying it twice on an already-harmonised collection.

All nine are declared in `analysed_before_split` and forced to **dev**. They
were written by the same author who diagnosed the defect and made the fix, so
they cannot be independent evidence and are not offered as any. Three
previously blind cases were moved to dev for the same reason: they were read
while narrowing the boundary.

The 62 held-out cases are a weaker instrument than the label implies. They were
blind when authored and were not consulted while making these changes, but the
`f03e327a57d2…` run measured the full suite, so their outcomes are known. They
can therefore detect a **regression** caused by the narrowing — which is the
real risk here, and worth measuring — but they cannot confirm an
**improvement**, because a case whose result you already know cannot surprise
you. The v0.4 report must state them that way.

Independence returns only when cases are written by an author who has not seen
these results. That is a v0.5 problem, and pretending otherwise now would cost
more than the missing evidence does.

### The first attempt at the fix failed, and the probes caught it

An eight-case pilot on 2026-08-05 (USD 1.33) ran six of the nine probes before
the full run. Three failed, in both directions:

| Probe | Expected | Observed |
|---|---|---|
| `baseline-discontinuity-handoff` | not `change-detection`; route to `remote-sensing-analysis` | `change-detection` alone |
| `season-and-sensor-conflict` | not `change-detection` | `change-detection` **and** `remote-sensing-analysis` |
| `documented-datum-elevation-change` | `change-detection` | `point-cloud-lidar` alone |

Two diagnoses, both concrete:

**A blocker the router cannot see is not a boundary.** The baseline probe says
"same tile, same month, both L2A" and carries no surface mismatch at all.
`change-detection`'s exclusion clause was keyed on features the prompt does not
contain, so it excluded nothing. The discontinuity had been documented in
`remote-sensing-analysis`'s *body* and deliberately kept out of its
*description*, on the reasoning that no case needed it yet — and routing only
ever sees descriptions. It is now in the description.

**Placement is part of a description, not styling.** The exclusion sat behind a
long list of positive triggers. The router matched the triggers and never
reached it. The precondition now leads, and a test pins it there.

**Unscoped ownership over-corrects.** `point-cloud-lidar` claimed the datum
axis "whenever two acquisitions are differenced", which swept up a case where
datum, geoid model and accuracy budget were all stated. Ownership is now bound
to *unestablished* comparability, with an explicit hand-back.

This is what the adversarial probes were for. A confirmatory case set would
have reported green and the failure would have surfaced after the full run
instead of for a dollar and change.

## Headline results

| Condition | TP | FN | FP | TN | Precision | Recall | Accuracy | Route accuracy |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Skills enabled | 109 | 9 | 0 | 40 | **100%** | **92.37%** | **94.30%** | **93.67%** |
| Skills disabled | 0 | 118 | 0 | 40 | n/a | 0% | 25.32% | 0% |

The disabled run is a control, not a competing configuration: the same runtime,
model, non-skill tools, prompts, and suite were used with all Agent Skills removed.
It produced **zero** recorded skill activations across all 158 cases, confirming
that the adapter did not invent activation evidence and that the isolated
workspace did not leak skill sources into the control.

Precision answers "when a target skill activated, how often was that activation
appropriate?" Recall answers "when a target skill should have activated, how often
did it?" Route accuracy is stricter: multi-skill and collision cases pass only when
the complete expected route is present, or the specified alternative route is used.

### Comparison with the archived 120-case card

| Metric | Archived (17 skills, 120 cases) | Current (18 skills, 158 cases) |
|---|---:|---:|
| Precision | 100% | 100% |
| Recall | 92.86% | 92.37% |
| Route accuracy | 92.5% | 93.67% |

Runtime and model are identical across both cards, so the runtime is not a
confound. The suite is not the same population, so these are two measurements of
different things, not a before/after improvement. Route accuracy rose and recall
fell slightly while the suite grew by 38 cases and one skill.

## Per-skill diagnostic

| Skill | Cases (+/-) | Precision | Recall | Route accuracy | Errors |
|---|---:|---:|---:|---:|---:|
| `geoai-orchestrator` | 9 (5/4) | 100% | 80.0% | 77.8% | 2 |
| `remote-sensing-analysis` | 9 (7/2) | 100% | 71.4% | 77.8% | 0 |
| `swe-devops-standards` | 9 (7/2) | 100% | 71.4% | 77.8% | 1 |
| `cartography-geoviz` | 8 (6/2) | 100% | 83.3% | 87.5% | 1 |
| `google-earth-engine` | 8 (6/2) | 100% | 83.3% | 87.5% | 0 |
| `point-cloud-lidar` | 9 (7/2) | 100% | 85.7% | 88.9% | 0 |
| `arcgis-pro-automation` | 13 (9/4) | 100% | 88.9% | 92.3% | 0 |
| `change-detection` | 9 (7/2) | 100% | 100% | 100% | 0 |
| `geo-data-engineering` | 8 (6/2) | 100% | 100% | 100% | 0 |
| `geo-deep-learning` | 9 (7/2) | 100% | 100% | 100% | 0 |
| `geostatistics-interpolation` | 9 (7/2) | 100% | 100% | 100% | 0 |
| `mcda-suitability-analysis` | 9 (7/2) | 100% | 100% | 100% | 0 |
| `ml-experiment-standards` | 8 (6/2) | 100% | 100% | 100% | 0 |
| `movement-trajectory` | 9 (7/2) | 100% | 100% | 100% | 0 |
| `network-accessibility-analysis` | 8 (6/2) | 100% | 100% | 100% | 0 |
| `postgis-spatial-sql` | 8 (6/2) | 100% | 100% | 100% | 0 |
| `spatial-statistics` | 8 (6/2) | 100% | 100% | 100% | 0 |
| `terrain-hydrology` | 8 (6/2) | 100% | 100% | 100% | 0 |

## Reviewed failures

All nine false negatives were inspected individually. They fall into three
groups, and the largest group is a single identifiable boundary defect.

### `change-detection` absorbs multi-date comparability cases — 4 of 9

| Case | Expected | Observed |
|---|---|---|
| `remote-sensing-analysis/mixed-level-trap` | `remote-sensing-analysis` | `change-detection` |
| `remote-sensing-analysis/cross-sensor-drought-comparability` | `remote-sensing-analysis` | `change-detection` |
| `point-cloud-lidar/mixed-datum-subsidence-refusal` | `point-cloud-lidar` | `change-detection` |
| `google-earth-engine/trend-map` | `google-earth-engine` | `change-detection` |

Every one of these prompts compares two dates, and every one is really about
sensor, datum, or processing-level comparability *before* any change can be
measured. `remote-sensing-analysis` documents exactly this boundary — it claims
ownership of multi-date harmonization and says change-detection applies only
once comparable observations exist. The written boundary is correct; the routing
signal "two dates" is simply stronger than it in practice.

This is worth stating plainly: `change-detection` scores 100% on its own nine
cases while being the direct cause of four other skills' misses. Precision as
defined here cannot see that, because it only asks whether an activation was
appropriate *within the target skill's own cases*. A skill that quietly annexes
neighbouring work is invisible to the headline precision number and shows up only
as reduced recall elsewhere. Treat the per-skill recall column, not precision, as
the boundary-health signal.

### Handoff to a plausible neighbour — 3 of 9

| Case | Expected | Observed |
|---|---|---|
| `geoai-orchestrator/ambulance-siting-equity-scope` | `geoai-orchestrator` | `mcda-suitability-analysis` |
| `swe-devops-standards/geospatial-etl-script` | `swe-devops-standards` | `geo-data-engineering` |
| `swe-devops-standards/concurrent-production-overwrite-refusal` | `swe-devops-standards` | `postgis-spatial-sql` |

Each landed on a defensible domain skill but missed the case's actual subject:
multi-stage scoping, delivery engineering discipline, and concurrent-write safety
respectively.

### No activation at all — 2 of 9

| Case | Expected | Observed |
|---|---|---|
| `arcgis-pro-automation/live-parcel-repair-refusal` | `arcgis-pro-automation` | none |
| `cartography-geoviz/map-series` | `cartography-geoviz` | none |

The first is a destructive-operation refusal case on live data with no backup —
the highest-consequence miss in the set, because the skill exists precisely to
force a preflight and refusal. The second is a short prompt ("maps of the same
indicator for 2010, 2015, 2020, 2025 side by side") that was answered directly.

### Incomplete route without a target miss — 1 case

`geoai-orchestrator/single-stage-routing` correctly withheld the orchestrator
(true negative) but did not activate the expected `geo-data-engineering`
alternative route. It is right on the target decision and wrong on the full
route, which is the gap between 94.30% accuracy and 93.67% route accuracy.

### Execution errors — 7 total

Four in the enabled condition (`cartography-geoviz/choropleth-request`,
`geoai-orchestrator/multi-stage-pipeline`, `geoai-orchestrator/single-devops-task`,
`swe-devops-standards/review-mode`) and three in the disabled condition
(`movement-trajectory/sampling-rate-circuity-comparison`,
`swe-devops-standards/repro-setup`, `swe-devops-standards/review-mode`).

All seven are `max_turns` terminations. **Every one of the four enabled errors
recorded the correct target activation before termination**, so each remains a
routing true positive and is counted separately as an execution error. Routing
metrics are therefore unaffected. No retry replaced any primary record.

These would matter for behavior scoring, where a truncated answer is a real
failure. They do not matter for routing, which is decided at activation time.

| Recorded usage | Skills enabled | Skills disabled |
|---|---:|---:|
| USD-equivalent cost | $20.207484 | $9.559424 |
| Aggregate per-case latency | 3,946.504 s | 2,489.674 s |
| Output tokens | 315,140 | 198,354 |

Latency is the sum of recorded case latencies, not elapsed wall-clock time; the
enabled run used four workers. Cost is adapter-reported subscription quota
consumption, not an invoice.

## Method and evidence

Each runtime received blind requests containing only `case_id` and prompt. Expected
routes, labels, rubrics, and case types stayed in the manifest. The suite includes
38 ambiguous, 46 collision, and 46 artifact-correctness-tagged cases; tags overlap.
Scoring is deterministic and contains no model call.

The published package contains:

- `metrics.json` — aggregate metrics, coverage, errors, and recorded usage;
- `per-skill.json` — recomputable skill-level routing diagnostics;
- `cases.jsonl` — expected routes, observed skill activations, outcomes, error codes,
  and trace hashes, with raw prompts, responses, and traces excluded;
- `README.md` — provenance, limitations, and reproduction commands.

The publisher independently recomputes aggregate routing metrics from case results,
requires exact enabled/disabled suite parity, rejects incomplete coverage, and fails
closed if behavior judgments are present.

## Scope and limitations

- Results apply only to the declared runtime/model pair. Triggering can differ across
  Claude, Codex, Cursor, versions, and model families.
- The model identifier is the adapter-reported runtime value. If a provider remaps
  an alias, the identifier alone cannot prove the underlying snapshot.
- The public eval prompts are a regression suite, not an independently hidden test
  set. They test documented routing boundaries and collision behavior. The suite is
  split into a 96-case development half and a 62-case held-out half
  (`evals/split.json`, assignment `a82ce97903b2…`); this card reports the full
  suite, and the split is a discipline commitment rather than an information
  barrier, since every prompt is readable in the public repository.
- **Behavior quality is not evaluated in this release.** Same-family preliminary
  judgments are excluded from headline evidence. Behavior metrics require a
  disclosed independent-family judge and the manual review protocol in
  [EVALUATION.md](EVALUATION.md).
- Per-skill samples are small (8–13 cases), so use them as diagnostics rather than
  population estimates. A single miss moves a per-skill recall figure by 11–14
  points.
- Precision does not detect a skill that over-triggers into another skill's
  territory; read the recall column for that. See *Reviewed failures*.
- Cost and latency are recorded adapter totals, not guarantees for other accounts,
  regions, concurrency settings, or cache states.
- The prior 17-skill, 120-case card remains available as archived evidence for the
  suite it was computed against:
  [`benchmarks/claude-code-2.1.214--claude-sonnet-5--d45ad2c82635/`](benchmarks/claude-code-2.1.214--claude-sonnet-5--d45ad2c82635/).
  Do not pool the two.

See [EVALUATION.md](EVALUATION.md) for the provider-neutral protocol and metric
definitions.
