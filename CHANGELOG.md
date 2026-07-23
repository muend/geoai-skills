# Changelog

All notable changes to this repository are documented here.
Versioning follows [SemVer](https://semver.org). Each skill also carries its
own `metadata.version` in its frontmatter.

## [0.1.0] — Unreleased

Pre-release candidate. Behavior benchmarks and clean-install verification are
required before the first stable release.

### Added
- 12 core GeoAI skills: `geoai-orchestrator`, `geo-data-engineering`,
  `remote-sensing-analysis`, `geo-deep-learning`, `spatial-statistics`,
  `mcda-suitability-analysis`, `geostatistics-interpolation`,
  `terrain-hydrology`, `network-accessibility-analysis`, `change-detection`,
  `cartography-geoviz`, `postgis-spatial-sql`.
- 3 high-demand skills: `google-earth-engine`, `point-cloud-lidar`,
  `movement-trajectory`.
- 2 cross-cutting standards skills: `ml-experiment-standards` (canonical
  spatial CV protocol in `references/spatial-cv-protocol.md`),
  `swe-devops-standards`.
- A 131-case typed evaluation suite spanning positive, negative, ambiguous,
  collision, artifact-correctness, and critical spatial failure scenarios.
  These are evaluation definitions, not yet published benchmark results.
- Self-contained critical behavior fixtures for cartography, MCDA, network
  accessibility, spatial statistics, geospatial SWE/DevOps, and terrain:
  four artifact-producing cases and two read-only fixture-backed cases with
  content-addressed inputs and deterministic contract regression tests.
- Provider-neutral deterministic evaluation harness with blind request
  manifests, immutable raw-response caching, explicit criterion judgments,
  and machine-readable routing, behavior, critical-failure, and usage metrics.
- Explicit `clarify`, `deliver`, and `clarify_then_provisional` interaction
  contracts for behavior cases, mode-stratified results, and a zero-observed-
  failure critical gate with an exact one-sided 95% upper confidence bound.
- Resumable Claude Code execution and model-judge adapter with blind plugin
  staging, trace-based skill activation, raw-trace hashes, and mandatory cost
  guardrails, including bounded `--case-id` pilots that resume into full runs.
  Error traces retain their actual cost, usage, and activation evidence, and
  the evaluation guide discloses Claude Code's terminal-turn budget overrun.
- Independent Google Gemini REST judge adapter with strict structured output,
  exact provider model-version capture, explicit external-data acknowledgement,
  bounded request/RPM controls, no automatic retries, ignored local traces, and
  resumable criterion-preserving checkpoints shared with the Claude judge.
- Repo tooling: `tools/validate_skills.py` frontmatter/structure linter,
  GitHub Actions CI, plugin marketplace manifest.

### Fixed
- Claude Code fixture execution now pre-approves only the declared tool profile
  and stages temporary workspaces below ignored `evals/runs/`, avoiding Windows
  short-`TEMP` path permission mismatches while preserving enabled/disabled
  non-skill tool parity.
