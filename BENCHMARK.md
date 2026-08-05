# Routing Benchmark

An 18-skill, 167-case Claude Code run recorded **99.17% routing precision**,
**96.77% routing recall**, and **96.41% full-route accuracy** on suite
`efe27d8c1736…`. The paired skills-disabled control recorded **zero**
activations across all 167 cases.

These are routing results, not claims about answer quality. They record which
skill activated, and say nothing about whether the answer that followed was
correct. **Behavior quality has still never been measured.**

This run exists to test the boundary defect the previous card published. That
test is the subject of [What this run was for](#what-this-run-was-for), and it
includes two results that went the wrong way.

| Field | Value |
|---|---|
| Suite state | `current` — measured against the shipped source tree |
| Runtime | Claude Code `2.1.214` |
| Model | `claude-sonnet-5` |
| Skills | 18 |
| Suite | 167 cases: 124 positive, 43 negative |
| Suite SHA-256 | `efe27d8c1736c80fd001cfd1e037c8fe5d6f013767d0c710a151250ffeeb8e77` |
| Split | `evals/split.json`, assignment `b2ab0305ffc8…`, 105 dev / 62 held-out |
| Run date | 2026-08-05 |
| Judge | None; routing is derived deterministically from recorded activations |
| Judge prompt/schema | n/a for routing-only scoring; run/result schema version 1 |
| Retry policy | Primary records retained; no retry replacement |
| Human review | All 4 false negatives, the 1 false positive, the 1 incomplete-route case, and all 11 execution errors inspected |
| Evidence | [Sanitized run package](benchmarks/claude-code-2.1.214--claude-sonnet-5--efe27d8c1736/) |

## What this run was for

The [previous card](benchmarks/claude-code-2.1.214--claude-sonnet-5--f03e327a57d2/)
recorded nine false negatives and named a cause: one clause in the
`change-detection` description read

> Invoke even when seasons, sensors, or processing levels are not comparable;
> diagnosing an invalid comparison is part of change analysis.

That clause claimed three axes. One of them — season and phenology — genuinely
belongs to `change-detection` and carries two of its own critical positive
cases. The other two, sensor and processing level, belong to
`remote-sensing-analysis`; vertical datum, swept in by the same sentence,
belongs to `point-cloud-lidar`. A single conjunction equated all three.

Three descriptions were edited in response, nine adversarial boundary probes
were added, and the split was rebuilt. The card published those edits as
**hypotheses**, explicitly refusing to call them fixes. This run tests them.

Three checks were written down before the run, and all three were met.

**1. The control arm is clean.** Zero activations in 167 disabled cases, so the
pair is valid and the adapter is not inventing activation evidence.

**2. All four annexed cases returned to their own skills.**

| Case | Previous route | This run |
|---|---|---|
| `remote-sensing-analysis/mixed-level-trap` | `change-detection` | `remote-sensing-analysis` |
| `remote-sensing-analysis/cross-sensor-drought-comparability` | `change-detection` | `remote-sensing-analysis` |
| `point-cloud-lidar/mixed-datum-subsidence-refusal` | `change-detection` | `point-cloud-lidar` |
| `google-earth-engine/trend-map` | `change-detection` | `google-earth-engine` |

**3. Neither over-correction guard moved.**
`change-detection/documented-datum-elevation-change` and
`change-detection/short-series-small-area-breakpoints` still route to
`change-detection`. The boundary was narrowed without being cut too deep — the
failure mode that would have traded one defect for another.

### What the earlier pilot caught, for a dollar and change

An eight-case pilot (USD 1.39) ran six of the nine probes before the expensive
part. Three failed, in both directions, and produced three general rules:

**A blocker the router cannot see is not a boundary.** The
`baseline-discontinuity-handoff` probe says "same tile, same month, both L2A"
and carries no surface mismatch at all. The Sentinel-2 Baseline 04.00
discontinuity had been documented in `remote-sensing-analysis`'s *body* and
deliberately kept out of its *description*, on the reasoning that no case needed
it yet — and routing only ever sees descriptions. It is now in the description.

**Placement is part of a description, not styling.** The exclusion sat behind a
long list of positive triggers. The router matched the triggers and never
reached it. The precondition now leads, and a test pins it to the first 120
characters.

**Unscoped ownership over-corrects.** `point-cloud-lidar` claimed the datum axis
"whenever two acquisitions are differenced", which swept up a case where datum,
geoid model and accuracy budget were all stated. Ownership is now bound to
*unestablished* comparability, with an explicit hand-back.

A confirmatory case set would have reported green and surfaced the failure after
the full run instead of before it.

## Headline results

| Condition | TP | FN | FP | TN | Precision | Recall | Accuracy | Route accuracy |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Skills enabled | 120 | 4 | 1 | 42 | **99.17%** | **96.77%** | **97.01%** | **96.41%** |
| Skills disabled | 0 | 124 | 0 | 43 | n/a | 0% | 25.75% | 0% |

The disabled run is a control, not a competing configuration: the same runtime,
model, non-skill tools, prompts, and suite were used with all Agent Skills
removed. It produced **zero** recorded skill activations across all 167 cases,
confirming that the adapter did not invent activation evidence and that the
isolated workspace did not leak skill sources into the control.

Precision answers "when a target skill activated, how often was that activation
appropriate?" Recall answers "when a target skill should have activated, how
often did it?" Route accuracy is stricter: multi-skill and collision cases pass
only when the complete expected route is present, or the specified alternative
route is used.

### Split breakdown

| Population | Cases | TP | FN | FP | TN | Precision | Recall | Route accuracy |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Full suite | 167 | 120 | 4 | 1 | 42 | 99.17% | 96.77% | 96.41% |
| Dev | 105 | 80 | 2 | 1 | 22 | 98.77% | 97.56% | 97.14% |
| Held-out | 62 | 40 | 2 | 0 | 20 | 100% | 95.24% | 95.16% |

**This run spent the held-out half.** The disclosure Gate C requires is in the
[evidence package](benchmarks/claude-code-2.1.214--claude-sonnet-5--efe27d8c1736/README.md).

Read the held-out row with the limitation `evals/split-inputs.json` already
records: the `f03e327a57d2…` run measured the full previous suite, so the
outcome of every carried-over case was known before these edits were made. The
half can therefore **detect a regression** but cannot **confirm an
improvement** — a case whose result you already know cannot surprise you.

The exception is the 24 cases written blind, after the split, by an author who
had seen no measurement result and has not inspected them since. They are the
only genuinely independent evidence here, and they scored **23 of 24**. The
single miss,
`swe-devops-standards/concurrent-production-overwrite-refusal`, was already
failing in the previous run and was not a target of these edits.

The nine new boundary probes are **not** independent. They were written by the
author who diagnosed the defect and made the fix, declared
`analysed_before_split`, and forced into dev. Independence returns only when
cases are written by someone who has not seen these results; that is a v0.5
problem.

### Why this is not compared as a ratio

| Metric | This run (167 cases) | Previous run (158 cases) |
|---|---:|---:|
| Precision | 99.17% | 100% |
| Recall | 96.77% | 92.37% |
| Route accuracy | 96.41% | 93.67% |
| TP / FN / FP / TN | 120 / 4 / 1 / 42 | 109 / 9 / 0 / 40 |

**The two suites are different populations, so these columns are not a
before/after.** Nine cases were added, and they were written to break the fix,
not to pass it. Comparing the ratios would let the author of the new cases
choose the denominator.

The comparison that means something is case-level, across the 158 cases both
runs share. That is the next section.

## Case-level change across the 158 shared cases

### Seven of the nine previous false negatives closed

| Case | Previous | This run |
|---|---|---|
| `remote-sensing-analysis/mixed-level-trap` | fn | tp |
| `remote-sensing-analysis/cross-sensor-drought-comparability` | fn | tp |
| `point-cloud-lidar/mixed-datum-subsidence-refusal` | fn | tp |
| `google-earth-engine/trend-map` | fn | tp |
| `arcgis-pro-automation/live-parcel-repair-refusal` | fn | tp |
| `cartography-geoviz/map-series` | fn | tp |
| `geoai-orchestrator/ambulance-siting-equity-scope` | fn | tp |

The first four were the targeted annexation cases and are the result this run
was bought to produce. The last three were **not** targets, and why they closed
**was not measured**. The only description change touching those skills was the
removal of a `metadata.version` line, which routing does not read. They are
recorded as closed and unexplained.

### Three failures persist

| Case | Previous | This run | Observed |
|---|---|---|---|
| `swe-devops-standards/concurrent-production-overwrite-refusal` | fn | fn | `postgis-spatial-sql` fired |
| `swe-devops-standards/geospatial-etl-script` | fn | fn | `geo-data-engineering` fired |
| `geoai-orchestrator/single-stage-routing` | tn, route incomplete | tn, route incomplete | nothing fired |

The `swe-devops-standards` description is unchanged in this release. These two
misses were not this run's subject and did not close. Each lands on a defensible
domain skill but misses the case's actual subject — delivery-engineering
discipline and concurrent-write safety respectively.

### Two cases moved from `tp` to `fn`, and the cause is not established

| Case | Previous | This run | Observed |
|---|---|---|---|
| `geo-data-engineering/scale-strategy` | tp | **fn** | `postgis-spatial-sql` fired |
| `postgis-spatial-sql/predicate-audit` | tp | **fn** | nothing fired |

Neither can be attributed to an edit. The descriptions of
`geo-data-engineering`, `postgis-spatial-sql` and `swe-devops-standards` are
byte-identical to the previous run apart from the removed `metadata.version`
line, and routing does not read that field. Two explanations remain — run-to-run
variance, and a real regression caused indirectly by a neighbouring
description — and **a single run cannot distinguish them.** A replicate of the
enabled arm would; it has not been done.

This is reported as an unresolved finding rather than a hypothesis, because the
observation is measured and the cause is not.

### One false positive, on a new probe

`change-detection/season-and-sensor-conflict` — *"Compare a Landsat 8 scene from
July 2019 with a Sentinel-2 scene from October 2024 to map vegetation loss."*
Expected: `change-detection` must not fire, route to
`remote-sensing-analysis`. Observed: `cartography-geoviz`, `change-detection`,
`geoai-orchestrator`, `remote-sensing-analysis`.

The pre-run hypothesis was that this might be a **shared boundary pattern**,
testable against `remote-sensing-analysis/cross-sensor-drought-comparability`,
which has the same cross-sensor, cross-season shape. That case passed cleanly.
**The shared-pattern hypothesis is not supported**, which leaves the difference
in the prompt itself: this one carries a July-to-October phenology confounder
alongside the cross-sensor blocker, and phenology is `change-detection`'s own
impostor.

Whether the case is too strict or the boundary still leaks is open. It was
deliberately not tuned — adjusting a description against a single prompt is
overfitting, and editing a test until the system passes it is the practice this
repository exists to avoid. The expectation will be reconsidered in v0.5.

The other eight probes passed, including all four that test the Baseline 04.00
content in both error directions — failing to apply the offset, and applying it
twice on an already-harmonised collection.

## Per-skill diagnostic

| Skill | Cases (+/-) | Precision | Recall | Route accuracy | Errors |
|---|---:|---:|---:|---:|---:|
| `swe-devops-standards` | 9 (7/2) | 100% | 71.4% | 77.8% | 2 |
| `geo-data-engineering` | 8 (6/2) | 100% | 83.3% | 87.5% | 0 |
| `postgis-spatial-sql` | 8 (6/2) | 100% | 83.3% | 87.5% | 0 |
| `geoai-orchestrator` | 9 (5/4) | 100% | 100% | 88.9% | 3 |
| `change-detection` | 14 (9/5) | 90% | 100% | 92.9% | 0 |
| `arcgis-pro-automation` | 13 (9/4) | 100% | 100% | 100% | 1 |
| `cartography-geoviz` | 8 (6/2) | 100% | 100% | 100% | 2 |
| `geo-deep-learning` | 9 (7/2) | 100% | 100% | 100% | 0 |
| `geostatistics-interpolation` | 9 (7/2) | 100% | 100% | 100% | 0 |
| `google-earth-engine` | 9 (7/2) | 100% | 100% | 100% | 1 |
| `mcda-suitability-analysis` | 9 (7/2) | 100% | 100% | 100% | 0 |
| `ml-experiment-standards` | 8 (6/2) | 100% | 100% | 100% | 0 |
| `movement-trajectory` | 9 (7/2) | 100% | 100% | 100% | 0 |
| `network-accessibility-analysis` | 8 (6/2) | 100% | 100% | 100% | 0 |
| `point-cloud-lidar` | 10 (8/2) | 100% | 100% | 100% | 0 |
| `remote-sensing-analysis` | 11 (9/2) | 100% | 100% | 100% | 0 |
| `spatial-statistics` | 8 (6/2) | 100% | 100% | 100% | 0 |
| `terrain-hydrology` | 8 (6/2) | 100% | 100% | 100% | 0 |

Two rows carry the story of this release.

`remote-sensing-analysis` and `point-cloud-lidar` were at 71.4% and 85.7% recall
on the previous card, both dragged down by cases `change-detection` had annexed.
Both now sit at 100%.

`change-detection` sits at **90% precision**, down from 100%. That is not a
degradation — it is the defect finally becoming visible. The previous card said
plainly that precision cannot detect a skill over-triggering into a neighbour's
territory, because precision only asks whether an activation was appropriate
*within the target skill's own cases*. The fix for that blind spot is to write
negative cases under the annexing skill, and three of the nine probes do exactly
that. `change-detection` now carries five negative cases instead of two, and its
precision reports the one boundary case it still fails.

## Reviewed failures

Every non-clean case was inspected individually: 4 false negatives, 1 false
positive, 1 incomplete route, and 11 execution errors across both conditions.
The case-by-case detail is in
[Case-level change](#case-level-change-across-the-158-shared-cases) above.

### Incomplete route without a target miss — 1 case

`geoai-orchestrator/single-stage-routing` correctly withheld the orchestrator
(true negative) but did not activate the expected `geo-data-engineering`
alternative route. It is right on the target decision and wrong on the full
route, which is the gap between 97.01% accuracy and 96.41% route accuracy. It
behaved identically in the previous run.

### Execution errors — 11 total

Nine in the enabled condition and two in the disabled condition. All are
`max_turns` terminations. No retry replaced any primary record.

**Every one of the nine enabled errors had its activation recovered from the
raw trace, and none was lost.** The adapter writes the trace to disk before
parsing, so a parse failure at `max_turns` does not destroy the activation
evidence; the analysis tool re-reads it and marks each row recoverable or lost.
Eight of the nine are routing true positives or true negatives regardless.

| Errored case (enabled) | Split | Routing outcome |
|---|---|---|
| `arcgis-pro-automation/project-before-metric-buffer-plan` | held-out | tp |
| `cartography-geoviz/choropleth-request` | dev | tp |
| `cartography-geoviz/raster-classification-not-map` | held-out | tn |
| `geoai-orchestrator/ambulance-siting-equity-scope` | held-out | tp |
| `geoai-orchestrator/multi-stage-pipeline` | dev | tp |
| `geoai-orchestrator/single-devops-task` | dev | tn |
| `google-earth-engine/basin-scale-multidecade-landcover` | dev | tp |
| `swe-devops-standards/review-mode` | dev | tp |
| `swe-devops-standards/geospatial-etl-script` | dev | fn |

The enabled error count rose from 4 to 9 between runs. **Why it rose was not
measured.** It does not move the routing figures, because routing is decided at
activation time, but it would matter for behavior scoring, where a truncated
answer is a real failure.

| Recorded usage | Skills enabled | Skills disabled |
|---|---:|---:|
| USD-equivalent cost | $21.695770 | $10.208539 |
| Aggregate per-case latency | 4,208.044 s | 2,863.379 s |
| Output tokens | 313,884 | 221,980 |

Latency is the sum of recorded case latencies, not elapsed wall-clock time; the
enabled run used four workers. Cost is adapter-reported subscription quota
consumption, not an invoice.

## What this run does not show

- **Answer quality.** Never measured, in this release or any before it. Routing
  says a skill activated; it says nothing about whether the answer that followed
  was correct, safe, or complete. This remains the largest open item in the
  project and requires a disclosed independent-family judge and the manual
  review protocol in [EVALUATION.md](EVALUATION.md).
- **That routing improved as a ratio.** The suites are different populations.
  What is shown is case-level: seven previous failures closed, three persist,
  two new ones appeared.
- **Why three of the seven closures happened.**
- **Whether the two new false negatives are variance or regression.**
- **Whether `season-and-sensor-conflict` is a bad case or a leaking boundary.**
  It is now known not to be a shared pattern, which is less than an answer.

## Method and evidence

Each runtime received blind requests containing only `case_id` and prompt.
Expected routes, labels, rubrics, and case types stayed in the manifest. The
suite includes 40 ambiguous, 51 collision, and 48 artifact-correctness-tagged
cases; tags overlap. Scoring is deterministic and contains no model call.

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
  split into a 105-case development half and a 62-case held-out half
  (`evals/split.json`, assignment `b2ab0305ffc8…`); this card reports the full
  suite, and the split is a discipline commitment rather than an information
  barrier, since every prompt is readable in the public repository.
- The held-out half was already spent by the `f03e327a57d2…` run, so it can detect
  a regression but cannot confirm an improvement. Only the 24 blind-authored cases
  are independent in the usual sense.
- **Behavior quality is not evaluated in this release.** Same-family preliminary
  judgments are excluded from headline evidence. Behavior metrics require a
  disclosed independent-family judge and the manual review protocol in
  [EVALUATION.md](EVALUATION.md).
- Per-skill samples are small (8–14 cases), so use them as diagnostics rather than
  population estimates. A single miss moves a per-skill recall figure by 11–14
  points.
- Precision detects over-triggering only where the annexed skill's territory is
  covered by a negative case filed under the annexing skill. Where it is not, read
  the recall column. See *Per-skill diagnostic*.
- Cost and latency are recorded adapter totals, not guarantees for other accounts,
  regions, concurrency settings, or cache states.
- The prior 18-skill, 158-case card remains available as archived evidence for the
  suite it was computed against:
  [`benchmarks/claude-code-2.1.214--claude-sonnet-5--f03e327a57d2/`](benchmarks/claude-code-2.1.214--claude-sonnet-5--f03e327a57d2/).
  Do not pool the two.
- The 17-skill, 120-case card from before that remains archived at
  [`benchmarks/claude-code-2.1.214--claude-sonnet-5--d45ad2c82635/`](benchmarks/claude-code-2.1.214--claude-sonnet-5--d45ad2c82635/)
  and is likewise not poolable with either.

See [EVALUATION.md](EVALUATION.md) for the provider-neutral protocol and metric
definitions.
