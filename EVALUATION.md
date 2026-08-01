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

The canonical case definitions live outside the runtime skill trees in
`evals/cases/<name>/evals.json`. Keeping development-only cases and fixtures
outside `skills/<name>/` prevents repository installers from copying benchmark
material into end-user runtime directories. The shared contracts are:

- `evals/schema.json` — authoring schema for skill cases;
- `evals/run-schema.json` — manifests, requests, runtime responses, judgments, case results, and aggregate metrics.

Every case declares one or more `case_types`: `positive`, `negative`, `ambiguous`, `collision`, or `artifact-correctness`. Exactly one polarity (`positive` or `negative`) is required. CI enforces at least 120 total cases, at least seven per skill, balanced suite-level category floors, valid cross-skill routes, and at least one critical case per skill.

Behavior eligibility is separate from routing polarity. A case may declare:

- `routing-only` — contributes routing metrics but is not judged for behavior;
- `advisory` — the prompt is self-contained and response text is sufficient evidence;
- `fixture-backed` — immutable files are declared under `fixtures` and staged by content hash;
- `artifact-producing` — the runtime receives the `workspace-write` tool profile and must create declared `expected_artifacts`.

Omitted `behavior_class` defaults to `routing-only`. This fail-closed default prevents an underspecified routing prompt from silently lowering or inflating behavior metrics. Fixture sources must live below the case set's `evals/cases/<name>/fixtures/` directory, prompts must name their staged workspace paths, and fixture bytes participate in both case and suite hashes. Git normalizes `SKILL.md` files and text fixtures to LF at checkout through `.gitattributes`, so their byte-derived hashes are identical on Linux and Windows; binary fixtures remain unmodified. Artifact-producing prompts must name exact output paths; captured artifacts include media type, size, SHA-256, and a bounded text preview when applicable.

Normalized manifests retain `skills/<name>/evals/fixtures/...` as the stable
logical `source_path` identity used by already-published suite hashes. That
field is a compatibility identifier, not the current physical repository
location. Runtime adapters resolve it to `evals/cases/<name>/fixtures/...`
before verifying the declared size and SHA-256. Changing this logical identity
would invalidate otherwise byte-identical benchmark populations.

A case must remain `routing-only` when its rubric requires a tool or licensed runtime that the declared adapter does not expose. Such behavior belongs in a separately identified integration run with exact environment evidence; a textual promise or simulated tool call is not a substitute. The current generic Claude Code profile therefore does not behavior-score ArcGIS Pro bridge operations.

Every behavior-evaluable case must also declare one interaction contract:

- `clarify` — material facts or authorization are missing, so the response should ask only the necessary questions or stop unsafe action;
- `deliver` — enough information exists to provide the requested analysis, plan, code, or decision in the current response;
- `clarify_then_provisional` — the response must ask for missing facts and still provide a bounded conditional plan or answer with assumptions labeled.

The interaction contract participates in the case and suite hashes but remains absent from blind runtime requests. It is revealed to the judge only after execution. This prevents a delivery rubric from silently penalizing a clarification-only case, while still treating a promise to do later work as insufficient for `deliver` and `clarify_then_provisional` cases. Do not infer or rewrite interaction modes after reading model outputs.

Generated local runs live under `evals/runs/` and are ignored by Git. Deliberately reviewed benchmark artifacts can later be copied into a versioned benchmark-results location.

## External transfer suites

External benchmark adaptations live below `evals/external/` and are validated
separately from the canonical suite. They do not participate in the native
case count, suite hash, routing metrics, split assignment, regression baseline,
or published benchmark claims.

The first such suite is a GeoAnalystBench-derived transfer subset. It uses
independently authored prompts, deterministic synthetic fixtures, independent
executable references, and artifact validators. It does not copy or download
upstream datasets, reference implementations, or verbatim prompts. Its
provenance pins the exact upstream commit and preserves the upstream license.
Results must be reported under their external-suite identity and may not be
pooled with native routing or behavior results. See
`evals/external/geoanalystbench/README.md` for the reuse and reporting boundary.
The initial five-case population is frozen by
`evals/external/geoanalystbench/freeze-v1.json`; CI verifies its exact case
membership and source-file hashes. This freeze is an input-integrity record,
not a model result or performance claim. A changed case population must receive
a new freeze version rather than rewriting v1.

External model runs use a separate, fail-closed evidence contract:
`run-schema.json` records the runtime, returned model version, installed skill
package and digest, condition, authorization, call/retry/timeout limits, cost
cap, and one response/artifact location per frozen case. Run
`python tools/evaluate_external_run.py --manifest <run.json> --dry-run` before
any separately authorized model invocation. The command is offline and makes
no model, API, web, connector, fixture, or validator call.

After all five attempts, pass the same manifest with `--result <result.json>`.
The tool regenerates only deterministic local fixtures, executes the frozen
artifact validators, retains failed cases in the denominator, and records
response, fixture, and artifact SHA-256 evidence. The resulting pass rate is
always labeled **GeoAnalystBench-derived external transfer results** and cannot
be pooled with the native 158-case metrics or represented as the upstream
50-task benchmark. See the suite README and `RESULTS-TEMPLATE.md` for the
operator and public-reporting protocol.

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

`--split {all,dev,holdout}` restricts a run to one half of `evals/split.json`. Use `dev` while iterating and `holdout` only for a release candidate; the two filters are independent, so `--scope behavior --split dev` is the 53-case behaviour development population. Each combination has its own suite hash, and the run directory name carries the half, so two halves cannot be pooled by accident. A missing or empty split half is an error rather than a silent fall back to the whole suite.

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

The judge receives rubric text and the immutable interaction contract only after
execution. `evals/judge-clauses.json` can decompose an exact manifest criterion
into ordered material clauses and declare whether the parent uses `all` or
`any`. The model returns evidence and a Boolean for every flattened atomic
clause; it never returns the parent decision. The adapter restores the exact
manifest criterion and computes the parent deterministically. Criteria absent
from the registry remain one atomic clause, so coverage can expand without
changing execution manifests or response hashes. This prevents a conjunctive
parent from passing when any model-supplied atom is false, but it does not prove
that the model judged each atom correctly; a candidate judge must still pass
the precommitted calibration gate before its decisions support a behavior
claim.

Claude, Gemini, and Codex resumable judge state is namespaced by provider,
judge model, and prompt version, preventing a changed judge contract from
silently resuming old partial decisions. The Codex namespace additionally
includes CLI version and reasoning effort because both can change local runtime
behavior. Changing either the prompt instructions or the atomic-clause registry
requires a new prompt version; never resume an existing namespace after either
input changes. Model judgments remain reviewable evidence, not ground truth.
Prefer a judge from a different model family than the executor.
Label same-family results preliminary, never use them as headline evidence, and
disclose judge provider, model, family, prompt/schema version, retries, and
missing/error cases. Manually review every critical case, every execution
error, and a stratified sample of at least 20% of the remainder before
publishing metrics.

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

The optional Codex CLI judge offers another independent-family candidate when
Codex is authenticated locally:

```bash
python tools/adapters/codex_cli.py judge \
  --run-dir evals/runs/<run-id> \
  --judge-model <requested-model-id> \
  --reasoning-effort low \
  --max-requests 2 \
  --case-id <case-id-1> \
  --case-id <case-id-2> \
  --acknowledge-external-data-use
```

Run first with `--dry-run`, which makes no model call. Real calls require the
external-data acknowledgement and a positive invocation cap. Each invocation
uses an empty temporary working directory, `--sandbox read-only`,
`--ephemeral`, `--ignore-user-config`, stdin prompt delivery, JSONL events, and
a strict `--output-schema`. The adapter performs no automatic retries and
fails closed if the judge uses shell, file-change, MCP, or web-search tools.
It records the requested model, Codex CLI version, reasoning effort, complete
event trace, and token usage. Subprocess stdout and stderr are decoded
explicitly as UTF-8 with replacement for malformed bytes, rather than inheriting
the host Windows code page; absent streams fail closed and still produce an
attempt trace. The documented Codex JSONL stream does not expose
a resolved provider model version, so reports preserve
`provider_reported_model: null` instead of presenting the requested model as a
provider-observed identity. ChatGPT subscription runs do not expose per-call
USD cost; metrics therefore record the billing mode and leave
`provider_cost_usd` null. These limitations must be disclosed with any
calibration result. Review OpenAI's official
[non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode)
and [Codex authentication](https://learn.chatgpt.com/docs/auth)
documentation before running a pilot.

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

JSON and JSONL inputs accept UTF-8 with or without a byte-order mark, including
PowerShell-generated files on Windows. The mark is removed during decoding;
canonical hashes and normalized result bytes therefore remain identical.

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

## Regression gates in CI

Behaviour and routing quality can only be measured by paid model runs, so CI
cannot re-measure them on every pull request. `tools/check_regression_gates.py`
blocks the three ways quality degrades silently between runs:

```bash
python tools/check_regression_gates.py                  # run all three gates
python tools/check_regression_gates.py --write-baseline  # seed/refresh Gate A
```

**Gate A — rubric non-weakening.** The cheapest way to make a failing score
improve is to delete the criterion that was failing. Every expected and
forbidden criterion is pinned in `evals/rubric-baseline.json`. Criteria may be
added freely. An expected criterion may be *decomposed* into finer criteria when
the decomposition is declared in the baseline's `decompositions` block, naming
the replaced text and at least two replacements, all of which must be present —
a one-to-one "decomposition" is a rewording and is rejected. Forbidden criteria
are prohibitions and are never decomposed away.

When a split is intended, add the declaration and then refresh the baseline:

```json
"decompositions": {
  "<skill>/<case>": [
    {"replaced": "<the old single criterion>", "with": ["<part 1>", "<part 2>"]}
  ]
}
```

Note that decomposition changes what criterion-attainment rates mean. Strict case
pass rates are unaffected, but a response meeting two of four requirements scores
2/4 where it previously scored 0/1, so attainment figures across a decomposition
boundary are not comparable and must name the rubric version they were computed
under.

The baseline is forward-looking: it constrains changes made after it was seeded
and makes no claim about the history before that point.

**Gate B — benchmark currency.** Published benchmark artefacts are computed
against one immutable suite hash. When a skill or eval changes, that hash changes
and the published numbers stop describing the current repository. This gate
recomputes the hash of the population the benchmark declares — from its `scope`
and `evaluation_scope` — and requires every directory under `benchmarks/` to state
`Suite state: current` or `Suite state: superseded` in its README, failing when
the declaration disagrees with the computed truth.

The comparison is against the declared population, not always the whole suite,
and that distinction was measured rather than assumed. A narrow run records the
hash of the cases it covered, so comparing every benchmark against the full-suite
hash forced a behaviour benchmark computed today to declare `superseded` — false
in the opposite direction, since the 84-case behaviour population still exists
and its numbers do describe the current skills. A benchmark that declares no
scope is still judged against the full suite, which is the pre-split shape. A superseded benchmark
stays published — its evidence remains valid for the suite it was computed
against — but it may not present itself as describing the current skills.

**Gate C — held-out containment.** A held-out case stops measuring anything the
moment someone tunes against it.

The split lives in `evals/split.json`, keyed by `case_id` and stored outside the
eval files so that revising it never changes the suite hash. It is generated, not
hand-written:

```bash
python tools/build_split.py            # verify the committed split is current
python tools/build_split.py --write    # regenerate it after adding cases
```

Two assignments are forced, and they are declared in `evals/split-inputs.json`:

| Input | Assignment | Why |
|---|---|---|
| `analysed_before_split` | dev | Its criteria were read during quality work. It cannot test an improvement made while looking at it. |
| `written_blind` | held-out | Authored against a sanitised brief by an author with no access to any result, and never inspected since. |

Everything else is stratified by (skill, primary case type) under a fixed seed, so
re-running produces a byte-identical file. Every skill is required to keep at
least one held-out case; a skill whose every case was analysed is a hard error,
because the repair is to write a blind case, not to promote a contaminated one.

**This is a discipline commitment, not an information barrier.** The suite is a
public repository: every held-out prompt and criterion is readable by anyone
editing the skills. Nothing here prevents that. What is enforced is the reporting
side — a benchmark must declare, in `metrics.json`, which population it measured:

| `scope` | Meaning |
|---|---|
| `dev` | Measured the development half only. |
| `holdout` | Measured the held-out half. Requires disclosure. |
| `full` | Measured everything. Requires disclosure. |
| `pre-split` | Finished before the split existed. Legal only on a superseded suite. |

`scope` alone does not determine the population, because a benchmark also runs
some subset of case classes, and the two cut the suite along different axes. The
field that says which cases ran is `evaluation_scope`, copied from the run
manifest, and the expected count is the intersection:

| | `routing` | `behavior` | `all` |
|---|---:|---:|---:|
| `dev` | 96 | 53 | 96 |
| `holdout` | 62 | 31 | 62 |
| `full` | 158 | 84 | 158 |

`routing` and `all` cover the same cases, and that is deliberate. A routing run
keeps every case because activation is observable on all of them — a behaviour
case still tells you whether the right skill fired. `routing-only` marks a case
as not behaviour-judged; it does not mark the population routing is measured on.
Only `behavior` narrows, to the cases that carry criteria.

`evaluation_scope` is also not the same as `kind`. `kind` says which *metrics*
are reported, which is why the first published benchmark here carries
`kind: "routing"` with a `case_mix.total` of 120 — the whole suite of its era.

The gate then checks the declaration against arithmetic rather than intent: when
the suite is current, `case_mix.total` must equal
`population[(scope, evaluation_scope)]`. A run labelled `dev` that reports every
case has spent the held-out set and mislabelled it, and the numbers say so
without needing per-case rows. A current benchmark that declares no
`evaluation_scope` is rejected: without it the population is undecidable rather
than merely unknown, and defaulting to `all` would silently excuse every partial
run.

Reporting held-out results is allowed — once — and has to be visible. A `holdout`
or `full` benchmark must carry in its README:

```
- Held-out disclosure: <the assignment_sha256 from evals/split.json>
```

A disclosure naming a different assignment is rejected, so one disclosure cannot
license every later run.

The honest limit: cases held out *by choice* are a weaker check than cases
*written blind*, because we could in principle have chosen them conveniently.
`split.json` records the two groups separately so a reader can weigh them
differently, and a test requires every skill to have at least one genuinely blind
case.
