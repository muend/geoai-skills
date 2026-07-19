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

### Reproducible Claude Code adapter

The optional `tools/adapters/claude_code.py` adapter uses Claude Code print mode and its documented JSON output. It is resumable, captures actual `Skill` tool-use events for routing, hashes raw traces, and requires both per-case and total cost caps. See Anthropic's official [CLI reference](https://docs.anthropic.com/en/docs/claude-code/cli-usage) and [authentication options](https://docs.anthropic.com/en/docs/claude-code/getting-started).

Authenticate once outside the repository:

```bash
claude auth login
claude auth status
```

Prepare separate manifests with an exact runtime version and model ID:

```bash
claude --version
python tools/eval_runner.py prepare \
  --runtime claude-code-<exact-version> \
  --model <exact-model-id> \
  --condition skills-enabled
```

Inspect the command without a model call:

```bash
python tools/adapters/claude_code.py execute \
  --run-dir evals/runs/<run-id> \
  --max-case-cost-usd <cap> \
  --max-total-cost-usd <cap> \
  --dry-run
```

Run one bounded pilot before approving a full batch. The checkpoint is reused by the later full run:

```bash
python tools/adapters/claude_code.py execute \
  --run-dir evals/runs/<run-id> \
  --case-id terrain-hydrology/slope-4326-catch \
  --workers 1 \
  --max-case-cost-usd <approved-pilot-cap> \
  --max-total-cost-usd <approved-pilot-cap>
```

Execute after reviewing the declared caps:

```bash
python tools/adapters/claude_code.py execute \
  --run-dir evals/runs/<run-id> \
  --workers 4 \
  --max-case-cost-usd <approved-per-case-cap> \
  --max-total-cost-usd <approved-run-cap>

python tools/eval_runner.py ingest \
  --run-dir evals/runs/<run-id> \
  --input evals/runs/<run-id>/adapter/claude-code.responses.jsonl
```

For `skills-enabled`, the adapter creates a temporary plugin containing skill runtime assets but no `evals/` folders. It runs from an empty workspace, disables user-level settings and MCP servers, and permits only the `Skill` and `Read` tools. For `skills-disabled`, it enables Claude Code safe mode, disables slash commands, and exposes no tools. Prompts are passed over stdin rather than command-line arguments.

Raw execution traces and partial checkpoints stay under the ignored run directory. Interrupted runs resume from validated completed cases. Claude Code evaluates `--max-budget-usd` at runtime checkpoints, so a terminal in-flight turn can exceed the declared per-case value. The adapter records the actual terminal cost even when Claude exits at the budget guardrail. With multiple workers, the total can additionally exceed the batch limit by the other in-flight cases. Treat both values as guardrails, disclose observed overruns, and obtain approval with an explicit margin rather than describing either value as a hard cap.

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

The Claude Code adapter can produce a criterion-preserving model-judge file after responses are ingested:

```bash
python tools/adapters/claude_code.py judge \
  --run-dir evals/runs/<run-id> \
  --judge-model <exact-judge-model-id> \
  --workers 4 \
  --max-case-cost-usd <approved-per-case-cap> \
  --max-total-cost-usd <approved-judge-cap>
```

The judge receives rubric text only after execution. Its structured output contains decisions and evidence by array position; the adapter restores exact manifest criterion text, so the model cannot rewrite the scoring standard. Model judgments remain reviewable evidence, not ground truth. Manually review all critical failures and a stratified sample before publishing metrics.

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
