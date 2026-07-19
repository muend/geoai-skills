# Evaluation Protocol

GeoAI Skills uses a provider-neutral, deterministic harness. It separates model execution from scoring so raw evidence stays auditable and no API credential or vendor SDK is required by this repository.

The harness measures:

- target-skill trigger precision, recall, and accuracy;
- expected-route accuracy, including negative routing cases;
- criterion-level behavior pass rate and forbidden-behavior violations;
- critical spatial failure rate for cases explicitly marked `critical`;
- aggregate token usage and latency when an adapter reports them.

No benchmark claim should be published without the raw response cache, the exact suite hash, the runtime and model identifiers, the run condition, and the judge identity.

## Contract

The canonical case definitions live beside each skill in `skills/<name>/evals/evals.json`. The shared contracts are:

- `evals/schema.json` — authoring schema for skill cases;
- `evals/run-schema.json` — manifests, requests, runtime responses, judgments, case results, and aggregate metrics.

Every case declares one or more `case_types`: `positive`, `negative`, `ambiguous`, `collision`, or `artifact-correctness`. Exactly one polarity (`positive` or `negative`) is required. CI enforces at least 120 total cases, at least seven per skill, balanced suite-level category floors, valid cross-skill routes, and at least one critical case per skill.

Generated local runs live under `evals/runs/` and are ignored by Git. Deliberately reviewed benchmark artifacts can later be copied into a versioned benchmark-results location.

## 1. Prepare blind requests

```bash
python tools/eval_runner.py prepare \
  --runtime codex \
  --model <exact-model-id> \
  --condition skills-enabled
```

The command prints a deterministic run directory. Its name is derived from the runtime, model, condition, and suite hash. Running it again with identical inputs reuses identical files; conflicting content is never silently overwritten.

It creates:

- `manifest.json` — the complete hashed scoring rubric and run metadata;
- `requests.jsonl` — only `schema_version`, `case_id`, and `prompt`.

`requests.jsonl` intentionally excludes expected behavior, forbidden behavior, trigger labels, and expected routes. Give only this blind file to the runtime adapter.

Prepare a second run with `--condition skills-disabled` for a baseline. In that condition the manifest declares no available skills.

## 2. Execute with any runtime adapter

An adapter reads each request, executes it once under the manifest's declared condition, and writes one response object per line:

```json
{"schema_version":1,"case_id":"terrain-hydrology/delineate-watershed","runtime":"codex","model":"<exact-model-id>","condition":"skills-enabled","response":"...","activated_skills":["terrain-hydrology"],"latency_ms":1234,"usage":{"input_tokens":800,"output_tokens":420}}
```

The required fields are defined by `#/$defs/response` in `evals/run-schema.json`. `latency_ms`, `usage`, and `error` are optional. `activated_skills` must come from the evaluated suite and must reflect observed activation, not the expected route.

Ingest and cache the complete adapter output:

```bash
python tools/eval_runner.py ingest \
  --run-dir evals/runs/<run-id> \
  --input /path/to/responses.jsonl
```

Ingestion requires exactly one valid response for every manifest case. It rejects missing, extra, duplicate, mismatched-runtime, and unknown-skill rows. The normalized batch is stored at `raw/responses.jsonl`; every case is also cached by its content hash under `cache/`.

## 3. Judge explicit criteria

Judging may be human, model-assisted, or deterministic rules, but it must produce one criterion-preserving judgment for every case. A judgment set follows `#/$defs/judgmentSet`:

```json
{
  "schema_version": 1,
  "suite_sha256": "<64-character manifest suite hash>",
  "judge": {"kind": "human", "name": "reviewer-handle", "version": "rubric-v1"},
  "judgments": [
    {
      "case_id": "terrain-hydrology/delineate-watershed",
      "expected_behavior": [
        {"criterion": "<exact manifest criterion>", "met": true, "evidence": "Short response-grounded reason"}
      ],
      "forbidden_behavior": [],
      "critical_failure": false,
      "notes": "Optional"
    }
  ]
}
```

Criterion text and order must exactly match the manifest. This prevents a judge or later edit from weakening the rubric after seeing outputs.

## 4. Score deterministically

```bash
python tools/eval_runner.py score \
  --run-dir evals/runs/<run-id> \
  --judgments /path/to/judgments.json
```

The command writes:

- `results/cases.jsonl` — one routing and behavior result per case;
- `results/metrics.json` — aggregate coverage, routing, behavior, critical-failure, usage, and latency metrics.

Scoring contains no model call, timestamps, random sampling, or hidden heuristic. Given the same manifest, raw responses, and judgments, it emits byte-identical results. Different existing content is refused unless `--force` is explicitly supplied.

## Reproducibility checklist

- [ ] Record the exact runtime and model identifiers.
- [ ] Keep skills-enabled and skills-disabled runs separate.
- [ ] Run the blind `requests.jsonl`, never `manifest.json`, through the evaluated model.
- [ ] Preserve observed skill activations and raw response text.
- [ ] Use exact manifest criteria when judging.
- [ ] Review all `critical_failure` decisions manually before publication.
- [ ] Publish suite hash, judge identity, sample size, and missing/error counts with every metric.
- [ ] Never compare runs whose suite hashes differ without disclosing the suite change.
