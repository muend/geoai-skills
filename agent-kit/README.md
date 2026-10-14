# GeoAI Agents — optional frozen-core addon

Preview 0.1.0 adds six reusable roles around the unchanged 18 GeoAI Skills.
It is a project-scoped Codex/Claude agent kit, not a hosted application.
The supported base is GeoAI Skills 0.4.1, runtime-v2, tree
`65023155d5324da86ce08f3aafadd9f52a3f9dc5fe7e3b0755aa4baef829a04e`.

## Start

Python 3.12+ is required. Install the pinned dependencies in a virtual environment:

```powershell
python -m venv .venv-agent-kit
.venv-agent-kit\Scripts\python -m pip install -r agent-kit/requirements.txt
.venv-agent-kit\Scripts\python agent-kit/geoai_agents.py verify-base --root .
.venv-agent-kit\Scripts\python agent-kit/geoai_agents.py install --runtime codex --skills-root skills --target C:\path\to\project
```

The install command is a read-only preview. Add `--apply` to install. Use
`--runtime claude` for Claude Code. The target gets six native definitions and
`.geoai-agent-kit/`; existing differing files cause a conflict, never an overwrite.
The supported base skills must already exist and are verified byte for byte.
No global configuration, AGENTS.md, CLAUDE.md or existing skill is rewritten.

Start a fresh session in the target and ask it to follow
`.geoai-agent-kit/START.md` as coordinator. The main conversation selects the
needed roles; simple explanations do not require a full team. See [START.md](START.md).
Runtime-native agent definitions alone do not guarantee their activation.
Adapter formats follow the [Codex subagent contract](https://learn.chatgpt.com/docs/agent-configuration/subagents)
and [Claude Code subagent contract](https://code.claude.com/docs/en/sub-agents).

## Roles and evidence

Coordinator, specialist, reality reviewer, method reviewer, presentation reviewer,
and skill maintainer share [COMMON.md](COMMON.md). Canonical instructions live in
`roles.json`; `render` generates both adapter formats. Models inherit the host.
Every skill has a positive/negative scenario and required checks in `bindings.json`.
`controls.json` assigns each check to its responsible independent reviewer.
Some required checks need specialist/manual evidence: an unregistered executable
check returns ABSTAIN, never PASS.

Create records using `schemas/records.schema.json` and the task example in
`examples/task.json`. The delivery command checks output identity, required reviews,
review independence, completion and evidence. It allows at most two repair rounds.
Review citations must resolve to files in the artifact inventory or the review's
`evidence_files` inventory; both size and SHA-256 are checked at delivery time.
JSON serializes PASS/FAIL/ABSTAIN as `pass`/`fail`/`abstain`, retaining their meaning.
A review instruction does not create an OS-level read-only sandbox.

PASS is limited to the named check; FAIL is a demonstrated contradiction; ABSTAIN
means the input, tool or evidence was insufficient. Geometry checks are not field
verification; structural SVG checks are not proof of human comprehension.

## Protection and distribution

`base.lock.json` inventories all 308 pre-addon tracked files. Its digest is pinned
in `package.json`; it must not be regenerated to hide a core change. Closed skill,
evaluation, benchmark, tool and plugin directories also reject new runtime inputs.
`source.lock.json` separately pins the exact committed source blobs at the same
commit. All skill bytes agree; 148 other files differ only in checkout line endings.
The guard accepts a complete match to either approved inventory and reports which
one matched. It does not normalize files or accept arbitrary mixtures. Addon files
use LF through their own .gitattributes. The new agent-kit CI workflow runs on
Windows and Linux without modifying the existing core workflow.
Existing runtime manifests and native hash algorithms remain unchanged. Source
archive builds also run the frozen-repository guard; installed packages check
their own manifest before redistribution. Compatibility is exact, not a version range.

```powershell
python agent-kit/geoai_agents.py render --check
python agent-kit/geoai_agents.py build --output agent-kit/artifacts/geoai-agents-0.1.0.zip
```

The archive includes native definitions, schemas, scripts, license and unchanged
legacy verification modules. It excludes tests, fixture answers, evaluation runs,
private data and credentials. Its manifest has a separate runtime digest. Extract
it and use `verify-package --root PATH` before installing. Archives are deterministic
and existing output archives are not replaced. SHA-256 records identity, not trust
in the publisher or scientific correctness.

## Verification and pilot scope

```powershell
python -m pytest agent-kit/tests -q -p no:cacheprovider
python agent-kit/geoai_agents.py evaluate-pilots --output agent-kit/artifacts/pilots.json
python tools/build_runtime_hash_registry.py --check
python tools/check_regression_gates.py
python agent-kit/tools/validate.py
```

For that development gate also install `agent-kit/requirements-dev.txt`. CI only
runs offline validators and tests; it never starts a paid model run.
Development and evaluation commands require the source checkout; the runtime ZIP
intentionally contains no development suite. In an extracted ZIP, run
`python geoai_agents.py verify-package --root .` and the `install` command from its
`geoai-agent-kit` directory, using the same `--skills-root` and `--target` options.

Six independent synthetic pilots each include valid, faulty and missing evidence:
walking network/barriers; line-width and discontinuity semantics; image comparability
and common masks; elevation units/NoData; spatial train/test separation; suitability
weights/sensitivity. The fixtures are intentionally small and validator scope is
reported. They are not real-world PlaceTwin reproductions or an agent-quality score.

The walkability validator supports projected metre LineStrings, explicit network
foot access, levels and barrier polygons. It recognizes explicit same-network bridges
over water. It does not infer unrecorded gates, current access or pedestrian safety.
The SVG check handles explicitly marked polylines without CSS style resolution;
unsupported graphics abstain. Terrain checks a one-dimensional east-slope diagnostic.
Model split checks point distances/groups, not chip footprint overlap. MCDA checks
normalized benefit scores and a declared +/-0.1 perturbation experiment.

## Comparative model evaluation

```powershell
python agent-kit/geoai_agents.py prepare-evaluation --destination agent-kit/artifacts/codex-eval --skills-root skills --runtime codex
```

This stages 18 tasks in three matched conditions, with identical input/tool bytes:
skills-only, structured-single, agent-team. Repeat for Claude. No model calls are
started by preparation. Producer workspaces contain no expected verdicts or validator
test fixtures. Current source `evals/` is authoring material, not an untouched holdout.

Use isolated runtime profiles with only the staged skills and condition-specific
agents. Record the actual model/version, trace hash, loaded customization inventory,
status and observed usage; unknown usage remains null. A normal shell exit does not
prove isolation. Missing inventory, external instructions/plugins, role contamination,
quota interruption and absent trace evidence exclude a run. `compare` keeps exclusions
and reports runtime/model/suite groups separately; it never pools a headline.
Trace, output, runtime profile inventory and independent judgment files must be
present with matching hashes. Judgment separates calculation, evidence sufficiency,
and presentation meaning. Aggregate summaries use only cases with all three
conditions present for the same runtime/model/suite. Profile inspection remains an
attestation; a self-reported inventory is not proof of OS isolation.

`tools/smoke.py` previews a bounded native model call; only `--run` calls a model.
It is development tooling and is excluded from runtime archives. A CLI returning
success is not a completed workflow: inspect the delivery record and native
delegation trace. This preview has no completed live comparative evaluation.

Deterministic pilot success is separate from live model validation and human review.
Do not publish agent superiority until eligible matched runs and independent judgments
exist. The historical native benchmark remains about its original runtime/model.

## Improvement and rollback

Record failures only in a project-local directory using `record-failure`. Start the
skill-maintainer explicitly in a later session. It may fix addon tools/contracts,
but core deficiencies produce proposals only. Do not edit tests to fit a fix.
Do not automatically upload cases, share memory, publish, or update installations.

To stop using the addon, stop invoking START.md. To uninstall, inspect the installation
manifest and remove only its unchanged project-local files; preserve user-modified
definitions and project evidence. No core rollback is necessary because it was not changed.
