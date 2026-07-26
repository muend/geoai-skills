# Claude Code 2.1.214 / Claude Sonnet 5 — routing, development half

Routing evidence for the 96-case development half of the suite, measured under
two conditions on the same cases. Behaviour is **not** evaluated here.

## Provenance

- Suite state: `current`
- Split scope: `dev` (96 of 158 cases)
- Evaluation scope: `all` (every case in the half; routing is observable on all of them)
- Runtime: `claude-code-2.1.214`
- Model: `claude-sonnet-5`
- Conditions: `skills-enabled` and `skills-disabled`
- Responses: 96/96 in each condition, 0 errors after documented retries
- Suite SHA-256: `25a2abef766472b7e8b60541de05cef3607e0ce5549b49465dc733b1c038915b`
- Split assignment SHA-256: `a82ce97903b20f7c…` (`evals/split.json`)
- Behavior judgments: none; behavior status is `not_evaluated`

The 62 held-out cases were **not** measured for this release, so no held-out
disclosure applies. They remain available as an independent check on a future
release candidate.

## Result

| | skills-disabled | skills-enabled |
|---|---:|---:|
| Trigger accuracy | 0.229 | **0.958** |
| Precision | — (no positives) | 0.986 |
| Recall | 0.000 | 0.959 |
| Expected-route accuracy | 0.000 | 0.958 |
| True positives | 0 | 71 |
| False negatives | 74 | 3 |
| True negatives | 22 | 21 |
| False positives | 0 | 1 |
| Cases with any activation | 0 | 96 |
| Cost (USD) | 6.04 | 13.04 |

The disabled arm is the floor by construction: with no skills loaded nothing can
activate, so it cannot score a true positive. Its value is as a control on the
case set and prompts, not as a competitive baseline.

## Reading `any_activation_cases: 96` correctly

Taken alone this number looks like the skills fire on everything, including the
22 negative cases. It does not mean that.

A negative case in this suite means **the request belongs to a different skill**,
paired with `should_trigger: false` for the skill under test. The desired
behaviour is that some other skill handles it. So `tn` means "the skill under
test stayed out of it", not "nothing activated" — and a negative case where a
neighbouring skill correctly takes over is a pass, with an activation recorded.

Concretely: all 22 negatives activated some skill, 21 scored `tn` because the
skill under test was not the one that fired.

Anyone quoting activation rate as an over-triggering figure would be quoting the
wrong number. The over-triggering figure is `fp`, and it is 1.

## The four routing failures, named

**One false positive** — a genuine over-trigger:

- `geoai-orchestrator/single-stage-routing` — activated `geoai-orchestrator` and
  `geo-data-engineering` on a single-stage task that needs no cross-specialist
  routing. The case exists to catch exactly this, and it caught it.

**Three false negatives** — none of them silence; each is a neighbour taking the
request:

| Case | Fired instead |
|---|---|
| `google-earth-engine/trend-map` | `change-detection` |
| `remote-sensing-analysis/mixed-level-trap` | `change-detection` |
| `swe-devops-standards/geospatial-etl-script` | `geo-data-engineering` |

"A plausible neighbour answered" is a different failure from "no skill engaged",
and the distinction matters for what a fix would look like: these are boundary
descriptions between adjacent skills, not missing coverage.

## Composition and the turn budget

Each condition is one primary run over all 96 cases, plus one documented retry
run:

| | Primary | Retry |
|---|---|---|
| `skills-disabled` | `disabled-dev-25a2abef-20260727` | `…-turns12-retry-1` (5 cases) |
| `skills-enabled` | `enabled-dev-25a2abef-20260727` | `…-turns12-retry-1` (5 cases) |

`compose` requires the primary to cover every case, so this is not a best-of
assembly across runs; `composed.provenance.json` records every source file hash
and which case came from where.

**Disclosed heterogeneity: 91 cases ran with a 4-turn budget, 5 with 12.** Those
five hit `error_max_turns` at 4 and were re-run **in both conditions** at 12, so
each case's two arms share a budget:

`arcgis-pro-automation/open-source-gdb-read` ·
`cartography-geoviz/choropleth-request` ·
`geoai-orchestrator/disaster-response-fusion` ·
`geoai-orchestrator/single-devops-task` ·
`swe-devops-standards/review-mode`

Why this was necessary, and what it costs in validity: with skills enabled the
model uses about 1.7× more turns per case (mean 3.68 vs 1.98), because reading a
skill and following its protocol consumes turns. A fixed turn cap therefore
censors the treatment arm more often — 5 cases against 2 at a 4-turn budget. The
turn budget is not visible to the model, so a per-case budget does not change the
prompt; but a case that finished *near* the cap may still have been shaped by it,
and that cannot be detected from these records. **The residual bias runs against
the skills, so the reported delta is conservative rather than flattering.** A
future release candidate should run the whole half at one uniform, higher budget.

## Retry policy

No failed record was deleted or overwritten. Retries live in separate run
directories and are named above. One retry attempt is recorded that did **not**
succeed — `disabled-dev-25a2abef-20260727-maxturns-retry-1`, which re-ran two
cases at the original 4-turn budget and failed again — and it is retained as
evidence that those failures were deterministic rather than transient.

## What this does not claim

- **No behaviour claim.** Whether a fired skill produced a better answer is
  unmeasured. `behavior.status` is `not_evaluated` for that reason, not as a
  placeholder.
- **No held-out claim.** These are development-half cases, 50 of which had their
  criteria read during earlier quality work. They cannot demonstrate that an
  improvement generalises.
- **No cross-suite comparison.** These numbers describe the 96-case population
  hashed above. Pooling them with any other population, including the full
  158-case suite, would be invalid.
