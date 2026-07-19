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
- A 120-case typed evaluation suite spanning positive, negative, ambiguous,
  collision, artifact-correctness, and critical spatial failure scenarios.
  These are evaluation definitions, not yet published benchmark results.
- Provider-neutral deterministic evaluation harness with blind request
  manifests, immutable raw-response caching, explicit criterion judgments,
  and machine-readable routing, behavior, critical-failure, and usage metrics.
- Resumable Claude Code execution and model-judge adapter with blind plugin
  staging, trace-based skill activation, raw-trace hashes, and mandatory cost
  caps.
- Repo tooling: `tools/validate_skills.py` frontmatter/structure linter,
  GitHub Actions CI, plugin marketplace manifest.
