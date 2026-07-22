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

Behavior eligibility is separate from routing polarity. A case may declare:

- `routing-only` — contributes routing metrics but is not judged for behavior;
- `advisory` — the prompt is self-contained and response text is sufficient evidence;
- `fixture-backed` — immutable files are declared under `fixtures` and staged by content hash;
- `artifact-producing` — the runtime receives the `workspace-write` tool profile and must create declared `expected_artifacts`.

Omitted `behavior_class` defaults to `routing-only`. This fail-closed default prevents an underspecified routing prompt from silently lowering or inflating behavior metrics. Fixture sources must live below the skill's `evals/fixtures/` directory, prompts must name their staged workspace paths, and fixture bytes participate in both case and suite hashes. Artifact-producing prompts must name exact output paths; captured artifacts include media type, size, SHA-256, and a bounded text preview when applicable.

A case must remain `routing-only` when its rubric requires a tool or licensed runtime that the declared adapter does not expose. Such behavior belongs in a separately identified integration run with exact environment evidence; a textual promise or simulated tool call is not a substitute. The current generic Claude Code profile therefore does not behavior-score ArcGIS Pro bridge operations.

Every behavior-evaluable case must also declare one interaction contract:

- `clarify` — material facts or authorization are missing, so the response should ask only the necessary questions or stop unsafe action;
- `deliver` — enough information exists to provide the requested analysis, plan, code, or decision in the current response;
- `clarify_then_provisional` — the response must ask for missing facts and still provide a bounded conditional plan or answer with assumptions labeled.

The interaction contract participates in the case and suite hashes but remains absent from blind runtime requests. It is revealed to the judge only after execution. This prevents a delivery rubric from silently penalizing a clarification-only case, while still treating a promise to do later work as insufficient for `deliver` and `clarify_then_provisional` cases. Do not infer or rewrite interaction modes after reading model outputs.

Generated local runs live under `evals/runs/` and are ignored by Git. Deliberately reviewed benchmark artifacts can later be copied into a versioned benchmark-results location.

## 1. Prepare blind requests

```bash
python tools/eval_runner.py prepare \
  --runtime codex \
  --model <exact-model-id> \
  --condition skills-enabled \
  --scope routing
```

The command prints a deterministic run directory. Its name is derived from the runtime, model, condition, and suite hash. Running it again with identical inputs reuses identical files; conflicting content is never silently overwritten.

It creates:

- `manifest.json` — the complete hashed scoring rubric and run metadata;
- `requests.jsonl` — only `schema_version`, `case_id`, and `prompt`.

`requests.jsonl` intentionally excludes expected behavior, forbidden behavior, interaction mode, trigger labels, and expected routes. Give only this blind file to the runtime adapter.

Prepare a second run with `--condition skills-disabled --scope routing` for the routing baseline. In that condition the manifest declares no available skills.

Prepare behavior runs separately after cases have explicit behavior classes:

```bash
python tools/eval_runner.py prepare \
  --runtime codex \
  --model <exact-model-id> \
  --condition skills-enabled \
  --scope behavior
```

`--scope routing` keeps all suite cases and requires no criterion judgments. `--scope behavior` includes only explicitly behavior-evaluable cases and produces its own suite hash. `--scope all` retains the combined, backward-compatible workflow. Never pool routing and behavior metrics across different suite hashes.

## 2. Execute with any runtime adapter

An adapter reads each request, executes it once under the manifest's declared condition, and writes one response object per line:

```json
{"schema_version":1,"case_id":"terrain-hydrology/delineate-watershed","runtime":"codex","model":"<exact-model-id>","condition":"skills-enabled","response":"...","activated_skills":["terrain-hydrology"],"latency_ms":1234,"usage":{"input_tokens":800,"output_tokens":420}}
```

The required fields are defined by `#/$defs/response` in `evals/run-schema.json`. `latency_ms`, `usage`, `artifacts`, and `error` are optional. `activated_skills` must come from the evaluated suite and must reflect observed activation, not the expected route.

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
  --condition skills-enabled \
  --scope <routing-or-behavior>
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

For `skills-enabled`, the adapter creates a temporary plugin containing skill runtime assets but no `evals/` folders. Every case receives a separate temporary workspace. Declared fixtures are verified by size and SHA-256 before execution, and any mutation or removal is recorded as an execution error. User-level settings and MCP servers are excluded.

Enabled and disabled conditions receive identical non-skill tools; the only declared tool difference is `Skill`. The `read-only` profile exposes `Read`, while `workspace-write` exposes `Read`, `Write`, and `Edit`. The enabled condition adds `Skill` and the blind plugin. Exact expected output paths are captured after execution; arbitrary workspace files are not swept into evidence. Prompts are passed over stdin rather than command-line arguments.

Raw execution traces and partial checkpoints stay under the ignored run directory. Interrupted runs resume from validated completed cases. Claude Code evaluates `--max-budget-usd` at runtime checkpoints, so a terminal in-flight turn can exceed the declared per-case value. The adapter records the actual terminal cost even when Claude exits at the budget guardrail. With multiple workers, the total can additionally exceed the batch limit by the other in-flight cases. Treat both values as guardrails, disclose observed overruns, and obtain approval with an explicit margin rather than describing either value as a hard cap.

## 3. Judge explicit criteria

Judging may be human, model-assisted, or deterministic rules, but it must produce one criterion-preserving judgment for every behavior-eligible case. Routing-only cases require no judgment and carry `behavior_evaluated: false` in case results. A judgment set follows `#/$defs/judgmentSet`:

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

Criterion text and order must exactly match the manifest. This prevents a judge or later edit from weakening the rubric after seeing outputs. The canonical case result is always derived by the scorer: every expected criterion must be met, no forbidden criterion may be observed, no critical failure may occur, and the response must complete without error. A separately collected holistic human case decision is calibration evidence only and must not replace this deterministic result.

For human and model review alike, `critical_failure` is not a synonym for any missed criterion. Mark it true only for a severe spatial safety or validity failure, when a response error prevents a critical case from being answered, or when the critical case's core safety or validity risk is completely omitted and the user is left able to proceed under the invalid premise. Record the response-grounded reason whenever reviewers disagree on this flag.

The Claude Code adapter can produce a criterion-preserving model-judge file after responses are ingested:

```bash
python tools/adapters/claude_code.py judge \
  --run-dir evals/runs/<run-id> \
  --judge-model <exact-judge-model-id> \
  --workers 4 \
  --max-case-cost-usd <approved-per-case-cap> \
  --max-total-cost-usd <approved-judge-cap>
```

The judge receives rubric text and the immutable interaction contract only after execution. Its structured output contains decisions and evidence by array position; the adapter restores exact manifest criterion text, so the model cannot rewrite the scoring standard. Claude and Gemini resumable judge state is namespaced by provider, exact judge model, and prompt version, preventing a changed judge contract from silently resuming old partial decisions. Model judgments remain reviewable evidence, not ground truth. Prefer a judge from a different model family than the executor. Label same-family results preliminary, never use them as headline evidence, and disclose judge provider, model, family, prompt/schema version, retries, and missing/error cases. Manually review every critical case, every execution error, and a stratified sample of at least 20% of the remainder before publishing metrics.

For an independent-family judgment through the Google Gemini REST API, set the
key in `GEMINI_API_KEY` and run a bounded pilot first:

```bash
python tools/adapters/gemini_api.py judge \
  --run-dir evals/runs/<run-id> \
  --judge-model <exact-model-id> \
  --requests-per-minute <current-model-rpm> \
  --max-requests 5 \
  --case-id <case-id-1> \
  --case-id <case-id-2> \
  --acknowledge-external-data-use
```

Repeat without `--case-id` only after the calibration gate passes, setting
`--max-requests` to the number of still-pending cases. Check the active model
limits in AI Studio before every run; RPM, TPM, and RPD limits vary by model and
project. The adapter spaces calls at the declared RPM, performs no automatic
retries, stops before the invocation request cap, records the requested model
and provider-returned `modelVersion`, and fails if that version changes within a
run. A dry run needs neither a key nor the external-data acknowledgement.

The acknowledgement is intentionally mandatory for real calls. Only public or
sanitized prompts, responses, artifacts, and criteria may be sent to an
external judge. The API key is transmitted in the `x-goog-api-key` header and
is never written to the request body, URL, checkpoint, metrics, or local trace.
Provider responses and resumable partial judgments remain below a
model-and-prompt-version namespace in the ignored `evals/runs/` directory, so
different judge configurations cannot overwrite or resume from one another.
Review Google's official
[structured-output](https://ai.google.dev/gemini-api/docs/structured-output),
[generateContent](https://ai.google.dev/api/generate-content), and
[rate-limit](https://ai.google.dev/gemini-api/docs/rate-limits) documentation
before choosing a model or quota cap.

## 4. Score deterministically

```bash
python tools/eval_runner.py score \
  --run-dir evals/runs/<run-id> \
  --judgments /path/to/judgments.json
```

For a routing-scoped run, or a legacy combined manifest that must be published
without behavior claims, use an empty schema-valid judgment set and opt in
explicitly:

```bash
python tools/eval_runner.py score \
  --routing-only \
  --run-dir evals/runs/<run-id> \
  --judgments /path/to/empty-routing-judgments.json
```

`--routing-only` sets behavior coverage to zero and behavior rates to `null`; it
does not infer, waive, or fabricate behavior judgments.

The command writes:

- `results/cases.jsonl` — one routing and behavior result per case;
- `results/metrics.json` — aggregate coverage, routing, behavior, critical-failure, usage, and latency metrics.

Scoring contains no model call, timestamps, random sampling, or hidden heuristic. Given the same manifest, raw responses, and judgments, it emits byte-identical results. Different existing content is refused unless `--force` is explicitly supplied.

Behavior metrics are also partitioned by interaction mode; do not hide a weak mode inside a pooled pass rate. The critical gate passes only when at least one critical case was evaluated and zero critical failures were observed. When the observed count is zero, `zero_failure_upper_bound_95` reports the exact one-sided 95% Clopper-Pearson upper bound, `1 - 0.05^(1/n)`. This bound must be disclosed with `n`; zero observed failures is not evidence that the true failure rate is zero. No `<2%` critical-failure claim is permitted unless this upper bound is below 0.02, which requires at least 149 independent critical cases with zero observed failures.

To publish an enabled run and its disabled-skills control without exposing raw
responses or traces:

```bash
python tools/publish_routing_benchmark.py \
  --enabled-run evals/runs/<enabled-run-id> \
  --disabled-run evals/runs/<disabled-run-id> \
  --output-dir benchmarks/<runtime-model-suite-id>
```

The publisher recomputes routing aggregates, verifies exact runtime/model/suite
parity and complete coverage, and emits only sanitized `metrics.json`,
`per-skill.json`, and `cases.jsonl` evidence. It rejects behavior-scored runs so
routing and behavior claims cannot be accidentally conflated.

## Reproducibility checklist

- [ ] Record the exact runtime and model identifiers.
- [ ] Keep skills-enabled and skills-disabled runs separate.
- [ ] Keep non-skill tools identical across enabled and disabled conditions.
- [ ] Run the blind `requests.jsonl`, never `manifest.json`, through the evaluated model.
- [ ] Use per-case isolated workspaces and verify every fixture hash before and after execution.
- [ ] Preserve observed skill activations and raw response text.
- [ ] Judge only explicitly answerable behavior classes; do not score routing-only prompts as failed behavior.
- [ ] Freeze interaction modes before execution and report behavior results by mode.
- [ ] Use exact manifest criteria when judging.
- [ ] Prefer an independent model family and label any same-family judgment preliminary.
- [ ] Review every critical/error case and at least 20% of the remaining judgments manually.
- [ ] Publish suite hash, judge identity, sample size, and missing/error counts with every metric.
- [ ] Require zero observed critical failures and disclose the exact one-sided 95% upper bound with its evaluated case count.
- [ ] Never compare runs whose suite hashes differ without disclosing the suite change.
