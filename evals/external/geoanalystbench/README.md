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
| `gab-01-urban-heat` | 1 | executable | projected ordinary kriging, variogram diagnostics, spatial block validation, rate-based vulnerability, uncertainty gating, and accessible mapping |
| `gab-08-facility-coverage` | 8 | executable | network-time coverage, weighted demand, overlap deduplication, barriers, and unreachable demand |
| `gab-36-vegetation-change` | 36 | executable | scaled SAVI change, intersected quality masks, threshold sensitivity, pixel area, and provenance |
| `gab-38-travel-time` | 38 | executable | directed travel time, forbidden turns, unreachable destinations, and route artifacts |
| `gab-39-spatial-regression` | 39 | executable | OLS-first diagnostics, queen/rook residual Moran inference, blocked model comparison, VIF exclusion, FDR uncertainty, and unstable-region warnings |

The planned subset has five tasks. Cases are added only when they have
deterministic synthetic fixtures, an independent executable reference, and
artifact-level validation.

## Frozen v1 source boundary

[`freeze-v1.json`](freeze-v1.json) fixes the exact five case IDs, upstream task
IDs, upstream commit, reporting boundary, and SHA-256 digest of every governed
suite source file. Its aggregate `suite_sha256` is
`c99563100cacc1e03234edd82ec64f4f47dc9479ca2ca4f9aabe84a1d5373f12`,
computed from sorted
`<file-sha256><two spaces><POSIX-path>` records, so it is stable across Windows,
macOS, and Linux checkouts.

The freeze covers provenance, schema, attribution/license files, and every file
inside the five case directories. It contains no model outputs or benchmark
results. Any byte change or new case-local file makes validation fail. Do not
rewrite `freeze-v1.json`; create a new freeze version for a changed source
population.

Verify the boundary from the repository root:

```bash
python tools/build_external_eval_freeze.py --check
python tools/validate_external_evals.py
```

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
