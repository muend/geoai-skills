# Claude Code 2.1.214 / Claude Sonnet 5 — routing, full suite

Sanitized evidence package for the current routing result reported in the
repository [benchmark card](../../BENCHMARK.md). Behaviour is **not** evaluated
here.

## Provenance

- Suite state: `current`
- Split scope: `full` (all 167 cases: 105 dev + 62 held-out)
- Evaluation scope: `routing`
- Runtime: `claude-code-2.1.214`
- Model: `claude-sonnet-5`
- Conditions: `skills-enabled` and `skills-disabled`
- Responses: 167/167 in each condition
- Execution errors: 9 enabled, 2 disabled — all `max_turns`, none retried;
  every activation recovered from the pre-parse trace, none lost
- Suite SHA-256: `efe27d8c1736c80fd001cfd1e037c8fe5d6f013767d0c710a151250ffeeb8e77`
- Run date: 2026-08-05
- Behavior judgments: none; behavior status is `not_evaluated`
- Retry policy: primary records retained; no error was replaced by a retry

Held-out disclosure: b2ab0305ffc81a1989c327bda2ce8d20c5450170653e543f49ab5dbd73cc8b54

### What `current` means here

The suite hash above matches the shipped 18-skill source tree at the time of the
run. `tools/check_regression_gates.py` recomputes the current suite hash on every
CI run and fails if this line claims currency it does not have. When the skills
or cases change, this card becomes `superseded` and a new pair must be published.

The disabled control used the same model, runtime, prompts, and non-skill tool
configuration while exposing no Agent Skills. It recorded **zero** activations
across all 167 cases.

### What this run was for

The [previous package](../claude-code-2.1.214--claude-sonnet-5--f03e327a57d2/)
recorded nine false negatives and attributed four of them to one clause in the
`change-detection` description, which claimed prompts whose blocker was sensor
or processing-level comparability. Three skills were edited in response, nine
adversarial boundary probes were added, and the split was rebuilt. Those edits
were published as **hypotheses**. This run tests them.

Result, stated against the three checks written before the run:

1. The control arm is clean — zero activations in 167 cases, so the pair is
   valid.
2. All four annexed cases returned to their own skills:
   `remote-sensing-analysis/mixed-level-trap` and
   `remote-sensing-analysis/cross-sensor-drought-comparability` to
   `remote-sensing-analysis`, `point-cloud-lidar/mixed-datum-subsidence-refusal`
   to `point-cloud-lidar`, `google-earth-engine/trend-map` to
   `google-earth-engine`.
3. Both over-correction guards stayed put:
   `change-detection/documented-datum-elevation-change` and
   `change-detection/short-series-small-area-breakpoints` still route to
   `change-detection`. The boundary was not cut too deep.

### The held-out half was spent here

This run measured the **full** suite, which includes the 62 held-out cases
recorded in `evals/split.json` under assignment `b2ab0305ffc8…`. This file is
the disclosure Gate C requires.

Read the held-out numbers with the limitation `evals/split-inputs.json` already
states: the `f03e327a57d2…` run measured the full previous suite, so the outcome
of every case carried over into this held-out half was already known before the
edits were made. That makes this half able to **detect a regression** but not
able to **confirm an improvement** — a case whose result you already knew cannot
surprise you.

The exception is the 24 cases written blind, after the split, by an author who
had seen no measurement result and has not inspected them since. Those are the
strongest evidence in the package, and they are the only part of it that is
independent in the sense the word usually implies. They scored 23 of 24; the one
miss is `swe-devops-standards/concurrent-production-overwrite-refusal`, which
was already failing in the previous run and was not a target of these edits.

The nine new boundary probes are **not** independent evidence and are not
presented as such. They were written by the same author who diagnosed the defect
and made the fix, were declared `analysed_before_split`, and were forced into
dev.

## Reviewed failures

All four false negatives, the one false positive, the one incomplete-route true
negative, and all nine execution errors were individually inspected. See the
[benchmark card](../../BENCHMARK.md#reviewed-failures) for the case-by-case
table.

Three findings worth reading before the numbers:

- **Seven of the previous nine false negatives closed.** Four were the targeted
  annexation cases. The other three —
  `arcgis-pro-automation/live-parcel-repair-refusal`,
  `cartography-geoviz/map-series`, and
  `geoai-orchestrator/ambulance-siting-equity-scope` — were not targets, and
  **why they closed was not measured.**
- **Two cases moved from `tp` to `fn`**: `geo-data-engineering/scale-strategy`
  and `postgis-spatial-sql/predicate-audit`. Neither can be attributed to an
  edit. The descriptions of `geo-data-engineering`, `postgis-spatial-sql` and
  `swe-devops-standards` are byte-identical to the previous run apart from a
  removed `metadata.version` line, which routing does not read. Run-to-run
  variance and a real regression are indistinguishable from a single run; a
  replicate run is what would separate them, and it has not been done.
- **One false positive**: `change-detection/season-and-sensor-conflict`, a new
  boundary probe. `change-detection` fires alongside the correct
  `remote-sensing-analysis` route on a prompt carrying both a cross-sensor
  blocker and a July-to-October phenology confounder. The pre-run hypothesis
  was that this might be a shared boundary pattern, testable against
  `remote-sensing-analysis/cross-sensor-drought-comparability`, which has the
  same shape. That case passed cleanly, so **the shared-pattern hypothesis is
  not supported.** Whether the case is too strict or the boundary still leaks
  remains open; it was deliberately not tuned.

## Reproduce the published package

After generating and ingesting the two private raw runs according to
[`EVALUATION.md`](../../EVALUATION.md):

```bash
python tools/eval_runner.py score \
  --routing-only \
  --run-dir evals/runs/<enabled-run> \
  --judgments /path/to/empty-routing-judgments.json

python tools/eval_runner.py score \
  --routing-only \
  --run-dir evals/runs/<disabled-run> \
  --judgments /path/to/empty-routing-judgments.json
```

Then regenerate the public evidence:

```bash
python tools/publish_routing_benchmark.py \
  --enabled-run evals/runs/<enabled-run> \
  --disabled-run evals/runs/<disabled-run> \
  --output-dir benchmarks/claude-code-2.1.214--claude-sonnet-5--efe27d8c1736
```

The publisher refuses changed existing content unless `--force` is explicit. It
also rejects missing cases, mixed suites, enabled/disabled configuration errors,
aggregate mismatches, and any run containing behavior judgments.

## Privacy boundary

`cases.jsonl` contains only routing evidence required to recompute the report:
case identity/type, expected and activated skills, routing outcome, error code,
latency, recorded usage, and the private trace hash. It deliberately excludes raw
prompts, responses, traces, workspace artifacts, and private review notes.
