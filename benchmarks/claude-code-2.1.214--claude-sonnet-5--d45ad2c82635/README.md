# Claude Code 2.1.214 / Claude Sonnet 5 routing run

This directory is the sanitized evidence package for the routing baseline reported
in the repository [benchmark card](../../BENCHMARK.md).

## Provenance

- Runtime: `claude-code-2.1.214`
- Model: `claude-sonnet-5`
- Conditions: `skills-enabled` and `skills-disabled`
- Responses: 120/120 in each condition
- Suite SHA-256: `d45ad2c8263584f21dd500bcd6c4e8cdeeb38ed9cd18205f66a4570224ff8801`
- Behavior judgments: none; behavior status is `not_evaluated`
- Retry policy: primary records retained; no error was replaced by a retry

The disabled control used the same model, runtime, prompts, and non-skill tool
configuration while exposing no Agent Skills.

## Reproduce the published package

After generating and ingesting the two private raw runs according to
[`EVALUATION.md`](../../EVALUATION.md), score legacy combined manifests as routing
only:

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
  --output-dir benchmarks/claude-code-2.1.214--claude-sonnet-5--d45ad2c82635
```

The publisher refuses changed existing content unless `--force` is explicit. It
also rejects missing cases, mixed suites, enabled/disabled configuration errors,
aggregate mismatches, and any run containing behavior judgments.

## Privacy boundary

`cases.jsonl` contains only routing evidence required to recompute the report:
case identity/type, expected and activated skills, routing outcome, error code,
latency, recorded usage, and the private trace hash. It deliberately excludes raw
prompts, responses, traces, workspace artifacts, and private review notes.
