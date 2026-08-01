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
python tools/build_external_eval_freeze_v2.py --check
python tools/build_external_eval_freeze_v3.py --check
python tools/build_external_producer_interface.py --check
python tools/build_external_producer_interface_v2.py --check
python tools/build_external_producer_interface_v3.py --check
python tools/validate_external_evals.py
```

## Frozen v2 artifact contracts

[`contracts/v2/`](contracts/v2/) adds a machine-readable diagnostic layer over
the unchanged v1 cases. [`freeze-v2.json`](freeze-v2.json) pins the schema and
five case contracts under aggregate hash
`86170ae144092f1ae0f34124d85505f0d3507a19f04f2b71f2081c89d10de418`.
Each contract cross-pins the corresponding v1 `case.json` and strict-validator
hash, then divides required criteria into:

- **semantic** — whether the analytical decisions and values are correct;
- **evidence** — whether provenance, method, units, QA, and validation evidence
  are sufficient for the claim; and
- **representation** — whether the exact files, field names, schemas, geometry
  metadata, and accessibility requirements are satisfied.

These axes are diagnostic and must be reported separately when used. They do
not relax the strict gate: a case passes its artifact contract only when every
required criterion and the exact frozen inventory pass the original v1
validator. The v2 freeze contains no model outputs or results and does not
change the denominator, upstream attribution, native benchmark, or v1 bytes.

## Frozen answer-safe producer interface

[`producer-interfaces/v1/`](producer-interfaces/v1/) defines the artifact
shape a runtime is allowed to see. Its manifest,
[`producer-interface-v1.json`](producer-interface-v1.json), pins the five case
interfaces under aggregate hash
`8596ddfeac83679c9a7c0b5007e5c009a44559823d8e70903bf5c66fd4274962`.
The interface includes only artifact paths, formats, required field names, and
method-evidence requirements. It excludes reference outputs, expected
analytical values, and validator source.

[`producer-interfaces/v2/`](producer-interfaces/v2/) is a separately frozen,
answer-safe successor for new runs. Its manifest,
[`producer-interface-v2.json`](producer-interface-v2.json), pins aggregate hash
`7ebfc789c10e99e9b3ec012b6e1e5323dd374be2a961ae3a645c976c684a5647`.
V2 preserves the same source cases and strict artifact validators, but makes
previously ambiguous method conventions, CSV/null/path serialization, mask
semantics, UTF-8 output, and workspace-local execution explicit. These are
producer instructions, not result values. V1 remains immutable for historical
comparison.

[`freeze-v3.json`](freeze-v3.json) and
[`validators/v3/validate_artifacts.py`](validators/v3/validate_artifacts.py)
define a separately immutable semantic pass contract. It retains exact artifact
inventory, disclosed JSON/CSV/GeoJSON structures, analytical values, units,
evidence, and bounded numeric tolerance while accepting semantically equivalent
SVG serialization. It supersedes neither v1 nor v2 evidence.

[`producer-interfaces/v3/`](producer-interfaces/v3/) is the answer-safe producer
condition paired only with that semantic contract. Its manifest,
[`producer-interface-v3.json`](producer-interface-v3.json), pins aggregate hash
`f52aadf2bfc3db74e2e004f647696f1b0c9631154823ee02fb433e2daff6b754`.
It exposes nested field paths, serialization and threshold precision, declared
deterministic seeds, and performance-safe execution hints, but no expected
analytical values, reference outputs, or validator source.

Render the exact prompt for one case without invoking a model:

```bash
python tools/render_external_case_prompt.py \
  --case gab-38-travel-time \
  --output /path/to/evidence/gab-38-travel-time/prompt.txt

python tools/render_external_case_prompt.py \
  --case gab-38-travel-time \
  --interface-version 2 \
  --output /path/to/evidence/gab-38-travel-time/prompt.txt

python tools/render_external_case_prompt.py \
  --case gab-38-travel-time \
  --interface-version 3 \
  --output /path/to/evidence/gab-38-travel-time/prompt.txt
```

The renderer is deterministic. Run/result schema v3 records the producer
interface ID and hash, requires each rendered `prompt_path`, verifies its exact
bytes during preflight, and stores its SHA-256 in the result. A prior run that
used a different prompt remains valid historical evidence but is a different
experimental condition and must not be presented as a rerun of this interface.

## External run protocol

The repository does not contain an API or model runner for this suite.
[`tools/evaluate_external_run.py`](../../../tools/evaluate_external_run.py)
only performs two offline operations:

1. `--dry-run` validates the exact freeze and producer-interface hashes,
   deterministic prompt bytes, five-case denominator,
   runtime/model/package versions, explicit public/synthetic-data approval,
   one-call-per-case limit, zero-retry policy, timeout, five-second termination
   grace, cost cap, and external-only reporting boundary.
2. `--result` regenerates each deterministic fixture locally, applies the
   frozen artifact validator to outputs that already exist, hashes the prompt,
   response, and artifacts, and writes a machine-readable result. Artifact
   validation is attempted even when the runtime timed out or returned an
error. A runtime or validator failure remains in the five-case denominator.

Use [`run-template-v3.json`](run-template-v3.json) for new semantic-v3 runs or
[`run-template-v2.json`](run-template-v2.json) when reproducing v2.
The original [`run-template.json`](run-template.json) remains pinned to v1 so
past evidence can be reproduced byte-for-byte.

Run and result schema version 3 deliberately separates four questions:

- **Skill activation:** was applicable local skill use observed?
- **Runtime:** did the call finish within the bounded execution window?
- **Artifact contract:** do the produced files satisfy the frozen validator and
  exact artifact inventory?
- **Overall:** did both runtime and artifact checks pass?

Do not report one axis as another. A call may activate the right skill and
produce useful files while still failing the strict artifact contract. Likewise,
files left by a timed-out process are validated and preserved as evidence, but
the runtime and overall result remain failed. Elapsed time greater than the
configured timeout plus the five-second termination grace is recorded as a
protocol deviation and blocks an unqualified aggregate claim.

Copy [`run-template.json`](run-template.json) into a new, untracked evidence
directory. Replace every `replace-before-run` value and the all-zero archive
digest. Render each declared prompt before preflight, and keep prompt, response,
and artifact paths relative to the manifest:

```bash
python tools/evaluate_external_run.py \
  --manifest /path/to/evidence/run.json \
  --dry-run
```

A successful preflight makes **no** model, API, web, connector, fixture, or
artifact-validator call. It only proves that the proposed run is authorized
and bounded. Produce the five responses and artifacts through the separately
approved runtime, then evaluate them offline:

```bash
python tools/evaluate_external_run.py \
  --manifest /path/to/evidence/run.json \
  --result /path/to/evidence/result.json
```

The result follows [`result-schema.json`](result-schema.json). Use
[`RESULTS-TEMPLATE.md`](RESULTS-TEMPLATE.md) for a public result card, copying
values from the result JSON rather than hand-entering outcomes. Responses,
artifacts, run manifests, and results are evidence records; do not commit them
to the runtime skill package.

Runtime-specific manual profiles:

- [MiniMax Code / MiniMax-M3](MINIMAX-CODE.md) — two-call activation smoke test
  followed by the optional frozen five-case run. This is an application-surface
  profile, not an API adapter.

## Run one reference case locally

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
