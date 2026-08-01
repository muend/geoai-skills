# GeoAnalystBench-derived external transfer result

> Replace every placeholder from the machine-readable result JSON. Do not
> publish this template or hand-enter pass/fail values.

## Run identity

- Run ID: `<run_id>`
- Condition: `<skills-enabled | skills-disabled | unassisted>`
- Freeze: `geoanalystbench-derived-v1`
- Suite SHA-256:
  `c99563100cacc1e03234edd82ec64f4f47dc9479ca2ca4f9aabe84a1d5373f12`
- Result JSON SHA-256: `<sha256>`
- Date: `<ISO-8601>`

## Runtime

- Provider / product: `<provider>` / `<product>`
- Product version: `<version>`
- Model / returned model version: `<model>` / `<model_version>`
- Skill package source, version, revision: `<source>`, `<version>`, `<revision>`
- Skill archive SHA-256: `<sha256>`

## Execution controls

- Public/synthetic data only: yes
- Calls: `5` maximum, `1` per case
- Automatic retries: `0`
- Retry observability: `<operator-controlled | platform-internal-not-observable>`
- Timeout: `<seconds>` per case
- Maximum authorized cost: `<USD>`
- Web access / connectors: disabled / disabled

## Results

| Case | Skill activation | Artifact validator | Evidence |
| --- | --- | --- | --- |
| `gab-01-urban-heat` | `<state>` | `<pass/fail>` | `<response/artifact hashes>` |
| `gab-08-facility-coverage` | `<state>` | `<pass/fail>` | `<response/artifact hashes>` |
| `gab-36-vegetation-change` | `<state>` | `<pass/fail>` | `<response/artifact hashes>` |
| `gab-38-travel-time` | `<state>` | `<pass/fail>` | `<response/artifact hashes>` |
| `gab-39-spatial-regression` | `<state>` | `<pass/fail>` | `<response/artifact hashes>` |

**External transfer pass rate:** `<passed>/5 (<percent>%)`

## Required claim boundary

These are **GeoAnalystBench-derived external transfer results** for five
independently authored cases with deterministic synthetic fixtures. They are
not pooled with the native 158-case GeoAI Skills suite, do not reproduce the
upstream 50-task benchmark, and do not establish compatibility with upstream
datasets or reference code.

## Failures and limitations

List every validator failure, runtime error, refusal, unobservable activation,
missing artifact, unexpected artifact, and protocol deviation. A failed case
remains part of the denominator.
