# Routing Benchmark

GeoAI Skills reaches **100% routing precision**, **92.86% routing recall**, and
**92.5% full-route accuracy** on its frozen 120-case suite for the exact runtime/model
pair below. These are routing results, not claims about answer quality.

| Field | Value |
|---|---|
| Runtime | Claude Code `2.1.214` |
| Model | `claude-sonnet-5` |
| Skills | 17 |
| Suite | 120 cases: 84 positive, 36 negative |
| Suite SHA-256 | `d45ad2c8263584f21dd500bcd6c4e8cdeeb38ed9cd18205f66a4570224ff8801` |
| Judge | None; routing is derived deterministically from recorded activations |
| Judge prompt/schema | n/a for routing-only scoring; run/result schema version 1 |
| Retry policy | Primary records retained; no retry replacement |
| Human review | All 9 route mismatches and the single execution error inspected |
| Evidence | [Sanitized run package](benchmarks/claude-code-2.1.214--claude-sonnet-5--d45ad2c82635/) |

## Headline results

| Condition | TP | FN | FP | TN | Precision | Recall | Accuracy | Route accuracy |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Skills enabled | 78 | 6 | 0 | 36 | **100%** | **92.86%** | **95%** | **92.5%** |
| Skills disabled | 0 | 84 | 0 | 36 | n/a | 0% | 30% | 0% |

The disabled run is a control, not a competing configuration: the same runtime,
model, non-skill tools, prompts, and suite were used with all Agent Skills removed.
It produced zero recorded skill activations, confirming that the adapter did not
invent activation evidence.

Precision answers “when a target skill activated, how often was that activation
appropriate?” Recall answers “when a target skill should have activated, how often
did it?” Route accuracy is stricter: multi-skill and collision cases pass only when
the complete expected route is present, or the specified alternative route is used.

## Per-skill diagnostic

| Skill | Cases (+/-) | Precision | Recall | Route accuracy | Errors |
|---|---:|---:|---:|---:|---:|
| `cartography-geoviz` | 7 (5/2) | 100% | 100% | 100% | 0 |
| `change-detection` | 7 (5/2) | 100% | 100% | 100% | 0 |
| `geo-data-engineering` | 7 (5/2) | 100% | 100% | 100% | 0 |
| `geo-deep-learning` | 7 (5/2) | 100% | 100% | 100% | 0 |
| `geoai-orchestrator` | 8 (4/4) | 100% | 100% | 62.5% | 0 |
| `geostatistics-interpolation` | 7 (5/2) | 100% | 100% | 100% | 0 |
| `google-earth-engine` | 7 (5/2) | 100% | 80% | 85.71% | 0 |
| `mcda-suitability-analysis` | 7 (5/2) | 100% | 80% | 85.71% | 0 |
| `ml-experiment-standards` | 7 (5/2) | 100% | 80% | 85.71% | 0 |
| `movement-trajectory` | 7 (5/2) | 100% | 100% | 100% | 0 |
| `network-accessibility-analysis` | 7 (5/2) | 100% | 100% | 100% | 0 |
| `point-cloud-lidar` | 7 (5/2) | 100% | 100% | 100% | 1 |
| `postgis-spatial-sql` | 7 (5/2) | 100% | 100% | 100% | 0 |
| `remote-sensing-analysis` | 7 (5/2) | 100% | 80% | 85.71% | 0 |
| `spatial-statistics` | 7 (5/2) | 100% | 100% | 100% | 0 |
| `swe-devops-standards` | 7 (5/2) | 100% | 60% | 71.43% | 0 |
| `terrain-hydrology` | 7 (5/2) | 100% | 100% | 100% | 0 |

The six false negatives are preserved in `cases.jsonl`. Three additional cases
activated or withheld the target skill correctly but missed their specified full
route, explaining the difference between 95% target-decision accuracy and 92.5%
route accuracy.

One `point-cloud-lidar` case ended with `error_max_turns`. Its trace recorded the
correct target activation before termination, so it remains a routing true positive
and is separately counted as an execution error. No retry replaced the primary
record.

| Recorded usage | Skills enabled | Skills disabled |
|---|---:|---:|
| USD-equivalent cost | $11.264772 | $1.054765 |
| Aggregate per-case latency | 1,961.849 s | 670.257 s |
| Output tokens | 142,620 | 42,545 |

Latency is the sum of recorded case latencies, not elapsed wall-clock time.

## Method and evidence

Each runtime received blind requests containing only `case_id` and prompt. Expected
routes, labels, rubrics, and case types stayed in the manifest. The suite includes
27 ambiguous, 41 collision, and 35 artifact-correctness-tagged cases; tags overlap.
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
  set. They test documented routing boundaries and collision behavior.
- **Behavior quality is not evaluated in this release.** Same-family preliminary
  judgments are excluded from headline evidence. Behavior metrics require a
  disclosed independent-family judge and the manual review protocol in
  [EVALUATION.md](EVALUATION.md).
- Per-skill samples are small (7–8 cases), so use them as diagnostics rather than
  population estimates.
- Cost and latency are recorded adapter totals, not guarantees for other accounts,
  regions, concurrency settings, or cache states.

See [EVALUATION.md](EVALUATION.md) for the provider-neutral protocol and metric
definitions.
