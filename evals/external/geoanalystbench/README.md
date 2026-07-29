# GeoAnalystBench-derived executable subset

This directory contains an independently authored, executable subset inspired
by task categories in
[GeoAnalystBench](https://github.com/GeoDS/GeoAnalystBench). It is an external
transfer suite, not part of the native GeoAI Skills routing or behavior
benchmark.

## Reuse boundary

- Upstream repository ref:
  `b5d8c40a8d23639ec77e9acb11f79fd033c07338`
- Upstream datasets: **not included or downloaded**
- Upstream reference implementations: **not copied or executed**
- Upstream prompts: **not copied verbatim**
- Fixtures, prompts, reference implementations, and validators in this
  directory: **independently authored**

The upstream repository is Apache-2.0 licensed. Its license is preserved in
`LICENSE-APACHE-2.0`, and attribution is recorded in `NOTICE` and
`provenance.json`. Linked datasets may have separate terms; this subset does
not use them.

## Reporting boundary

Results from this directory must be labeled **GeoAnalystBench-derived external
transfer results**. Do not:

- pool them with the native 158-case suite;
- compare their pass rate directly with native routing accuracy;
- imply that this five-case target subset reproduces the upstream 50-task
  benchmark; or
- claim compatibility with upstream data or reference code.

## Current coverage

| Case | Upstream task | Status | What it tests |
| --- | ---: | --- | --- |
| `gab-38-travel-time` | 38 | executable | directed travel time, forbidden turns, unreachable destinations, and route artifacts |

The planned subset has five tasks. Cases are added only when they have
deterministic synthetic fixtures, an independent executable reference, and
artifact-level validation.

## Run the current case

From the repository root:

```bash
python tools/validate_external_evals.py
python evals/external/geoanalystbench/cases/gab-38-travel-time/generate_fixture.py \
  --output-dir .tmp/gab-38/fixtures
python evals/external/geoanalystbench/cases/gab-38-travel-time/reference.py \
  --input .tmp/gab-38/fixtures/network.json \
  --output-dir .tmp/gab-38/outputs
python evals/external/geoanalystbench/cases/gab-38-travel-time/validate_artifacts.py \
  --input .tmp/gab-38/fixtures/network.json \
  --output-dir .tmp/gab-38/outputs
```

The repository tests run the same pipeline in temporary directories and also
prove that corrupted or incomplete artifacts fail validation.
