# MiniMax Code / MiniMax-M3 manual run profile

Status: supported as a **manual evidence-producing surface**, not as an
automated API adapter.

MiniMax documents MiniMax-M3 and MiniMax Code as its current model-and-agent
pair, and MiniMax Code can import Agent Skills from GitHub. The public API
reference may lag the product surface, so this profile records what the
application actually displays and does not infer an API model identifier.

Official references:

- [MiniMax-M3 model page](https://www.minimax.io/models/text/m3)
- [MiniMax-M3 release and MiniMax Code overview](https://www.minimax.io/blog/minimax-m3)
- [MiniMax Code download](https://agent.minimax.io/download)
- [MiniMax Agent Skills directory](https://agent.minimax.io/skills)
- [MiniMax API model list](https://platform.minimax.io/docs/api-reference/models/openai/list-models)

## Record the installed surface

Before testing, capture a screenshot or export that shows the imported skills.
Record the following in a copy of [`run-template.json`](run-template.json):

```json
{
  "condition": "skills-enabled",
  "runtime": {
    "provider": "MiniMax",
    "product": "MiniMax Code",
    "product_version": "<application build shown in About/Settings>",
    "model": "MiniMax-M3",
    "model_version": "<returned build, or UI-declared M3; exact build unreported>"
  },
  "skill_package": {
    "source": "https://github.com/muend/geoai-skills",
    "version": "<installed package version>",
    "revision": "<exact imported Git commit SHA or tag>",
    "archive_sha256": "<SHA-256 of the imported archive or recorded bundle>"
  }
}
```

Do not claim an exact model build if the UI exposes only `MiniMax-M3`. Use the
literal value `UI-declared M3; exact build unreported` and disclose the limit in
the public result card. If the GitHub import does not expose a revision, reinstall
from a release tag or archive whose SHA-256 can be recorded before a formal run.

## Phase A: two-call activation smoke test

Use two separate new tasks. Keep memory, web search, MCPs/connectors, agent teams,
and unrelated skills disabled where the application exposes those controls. Do
not press regenerate or retry. These smoke calls are packaging evidence, not
benchmark scores.

Positive prompt:

```text
Plan a defensible two-date Sentinel-2 forest-loss workflow. One scene is from
May 2024 and the other from September 2025. Decide whether this comparison can
support a changed-hectares claim and state the evidence required before
reporting it. Do not use web search, MCPs, connectors, or external tools.
```

Pass conditions:

- `change-detection` or `remote-sensing-analysis` visibly activates, if the UI
  exposes activation;
- the response rejects an unqualified changed-hectares claim because of the
  phenology mismatch;
- it requires matched phenology or a season-aware time series, co-registration,
  intersected cloud/shadow masks, threshold sensitivity, and area uncertainty.

Negative prompt:

```text
Give me three conventional commit messages for renaming variable x to
pixel_count. Do not use web search, MCPs, connectors, or external tools.
```

Pass conditions:

- no GeoAI skill activates; and
- the response only supplies commit-message suggestions.

Save each exact prompt, final response, activation evidence, product/model label,
timestamp, and screenshot in an untracked evidence directory.

## Phase B: frozen five-case external run

Proceed only after both smoke tests pass and the public/synthetic transfer run is
explicitly approved. Copy `run-template.json`, replace every placeholder, and set:

```json
{
  "execution_policy": {
    "automatic_retries": 0,
    "connectors_enabled": false,
    "max_calls": 5,
    "max_calls_per_case": 1,
    "max_cost_usd": "<approved numeric cap>",
    "network_scope": "provider-only",
    "retry_observability": "platform-internal-not-observable",
    "timeout_seconds_per_case": 300,
    "web_access": false
  }
}
```

`automatic_retries: 0` means the operator does not regenerate or rerun a case.
When MiniMax Code does not expose transport-level retry telemetry, retain
`platform-internal-not-observable` and disclose that limitation; do not describe
the run as proving zero provider-internal retries.

Run the offline preflight before opening the five tasks:

```bash
python tools/evaluate_external_run.py \
  --manifest /path/to/minimax-m3/run.json \
  --dry-run
```

For each frozen case, start one new task, provide only its generated synthetic
fixture and exact `case.json` prompt, and download the requested artifacts into
the manifest's case directory. Do not repair a failed artifact by rerunning the
model. After all five attempts, execute the offline evaluator and build the
public card from its machine-readable result:

```bash
python tools/evaluate_external_run.py \
  --manifest /path/to/minimax-m3/run.json \
  --result /path/to/minimax-m3/result.json
```

MiniMax results remain a distinct runtime condition. Never pool them with the
native 158-case suite, the upstream GeoAnalystBench benchmark, or another
provider's result.
