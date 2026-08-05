# Claude Code 2.1.214 / Claude Sonnet 5 — routing, full suite

Sanitized evidence package for the current routing result reported in the
repository [benchmark card](../../BENCHMARK.md). Behaviour is **not** evaluated
here.

## Provenance

- Suite state: `superseded`
- Split scope: `full` (all 158 cases: 96 dev + 62 held-out)
- Evaluation scope: `routing`
- Runtime: `claude-code-2.1.214`
- Model: `claude-sonnet-5`
- Conditions: `skills-enabled` and `skills-disabled`
- Responses: 158/158 in each condition
- Execution errors: 4 enabled, 3 disabled — all `max_turns`, none retried
- Suite SHA-256: `f03e327a57d2faa70ed31f0b3920355f31527991626992b5fc0add3edbace7f9`
- Run date: 2026-08-04
- Behavior judgments: none; behavior status is `not_evaluated`
- Retry policy: primary records retained; no error was replaced by a retry

Held-out disclosure: a82ce97903b20f7c6e8fa998afbac564069077fbc115846f10d03c04b7ca2301

### What `superseded` means here

This run described suite `f03e327a57d2…`. Every `SKILL.md` in the repository has
since been edited, so the current suite is `76eaab51b3e3…` and this package no
longer describes the skills that ship here. The figures remain valid evidence
**for the suite they were computed against** and remain reproducible from the
recorded hash, but they must not be cited as if they described the current tree.

The edits that retired it were deliberate, and one of them targets a defect this
very run exposed:

- `change-detection` no longer claims prompts whose blocker is sensor or
  processing-level comparability. That clause caused four of the nine false
  negatives recorded here.
- `point-cloud-lidar` now owns cross-acquisition vertical datum comparability,
  which previously had no owner.
- `remote-sensing-analysis` now encodes the Sentinel-2 Baseline 04.00
  `BOA_ADD_OFFSET` discontinuity.
- `metadata.version` was removed from every skill and `arcgis-pro-automation`
  gained its missing `license` field.

**None of that has been measured.** The boundary fix is a hypothesis until a
fresh run tests it, and it cannot honestly be tested against the cases in this
package: this run spent the held-out half, so re-scoring the same 158 cases
after editing the descriptions they exposed would be iteration presented as
confirmation. The v0.4 run requires cases written for the boundary, and a fresh
dev / held-out split.

### The held-out half was spent here

This run measured the **full** suite, which includes the 62 held-out cases
recorded in `evals/split.json` under assignment `a82ce97903b2…`. That is the one
permitted spend of the held-out half, and this file is the disclosure Gate C
requires.

What that costs, stated plainly: those 62 cases are no longer an untouched
independent check. The split was always a discipline commitment rather than an
information barrier — every prompt is readable in the public repository — but the
commitment was specifically *not to iterate against these cases*, and that
commitment now has a visible starting point. Any skill or description change made
after 2026-08-04 that improves a held-out case must be justified on its own merits
and disclosed, not presented as an independent confirmation.

The 27 cases written blind after the split by an author who had seen no result
remain the strongest evidence in the set; the rest were held out by choice, which
is weaker, and `evals/split.json` records that distinction.

### What `current` means here

The suite hash above matches the shipped 18-skill source tree at the time of the
run. `tools/check_regression_gates.py` recomputes the current suite hash on every
CI run and fails if this line claims currency it does not have. When the skills or
cases change, this card becomes `superseded` and a new pair must be published.

The disabled control used the same model, runtime, prompts, and non-skill tool
configuration while exposing no Agent Skills. It recorded **zero** activations
across all 158 cases.

## Reviewed failures

All nine false negatives, the one incomplete-route true negative, and all seven
execution errors were individually inspected. The largest single cause is
`change-detection` absorbing four multi-date comparability cases that belong to
`remote-sensing-analysis`, `point-cloud-lidar`, and `google-earth-engine`. See
the [benchmark card](../../BENCHMARK.md#reviewed-failures) for the case-by-case
table and the note on why precision cannot detect this class of defect.

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
  --output-dir benchmarks/claude-code-2.1.214--claude-sonnet-5--f03e327a57d2
```

The publisher refuses changed existing content unless `--force` is explicit. It
also rejects missing cases, mixed suites, enabled/disabled configuration errors,
aggregate mismatches, and any run containing behavior judgments.

## Privacy boundary

`cases.jsonl` contains only routing evidence required to recompute the report:
case identity/type, expected and activated skills, routing outcome, error code,
latency, recorded usage, and the private trace hash. It deliberately excludes raw
prompts, responses, traces, workspace artifacts, and private review notes.
