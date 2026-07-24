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
- The SWE/DevOps skill now front-loads geospatial code-review and repair intent
  while retaining explicit no-code analysis boundaries and regression coverage.
- `geoai-orchestrator` now routes by invoking rather than by naming. A new
  routing gate precedes and explicitly overrides the pipeline template, which
  previously told the model to publish a plan and wait for confirmation; that
  document-order contradiction let the skill identify the correct specialists
  and then offer to hand off later instead of doing so. The gate requires every
  finding to be routed, forbids making routing conditional on permission,
  states that clarification never substitutes for routing, and treats audit
  requests as delivery requests. The single-specialist negative boundary is
  unchanged and regression-locked.
- `point-cloud-lidar` now treats recording the vertical datum as an obligation
  distinct from reporting it. The verification protocol previously asked only
  that the datum be reported in the answer, so a resolved datum, its geoid
  model, its transformation, and any per-tile offsets were never persisted into
  the delivered product. A new resolve/transform/record section enumerates the
  required machine-readable metadata fields, and an unresolvable datum must ship
  as a labelled provisional product rather than silently.
- `geo-deep-learning` now requires the label set to be characterised — count,
  labelled area, geographic spread, class balance, and deployment geography —
  before any architecture is recommended, and requires recommendations to be
  conditioned on those answers when they are unknown rather than issued
  unconditionally.
- `movement-trajectory` now requires the projected CRS and the UTC-normalised
  timestamp base to be declared before any distance radius, speed limit, or
  dwell duration is proposed. An unknown input CRS or timezone is a question,
  not a default; naive timestamps are never silently treated as UTC.
- `postgis-spatial-sql` now requires any recommended stored geometry column to
  be typed with its SRID, with the index and populating `ST_Transform` shown.
  An untyped column offered as a fix reintroduces the mixed-SRID problem it was
  meant to solve.
- `google-earth-engine` now defines a provenance record as a named deliverable
  emitted beside the export — catalog asset IDs with version, date ranges and
  filters, mask method and thresholds, reducer arguments, export parameters,
  and the run date and API client version.

### Changed
- Three evaluation criteria that bundled several independent requirements into
  one pass/fail row were decomposed so partial delivery is distinguishable from
  none: the leakage-audit fold/uncertainty/overlap/held-out row, the CRS-loss
  row/null-geometry/validity/extent accounting row, and the Earth Engine
  quota-and-provenance row. No requirement was removed, weakened, or reworded,
  and tests assert that each original conjunct still appears. Note that
  criterion-attainment rates computed before and after this decomposition are
  **not comparable** — strict case pass rates are unaffected, but a response
  satisfying two of four requirements now scores 2/4 on rows where it
  previously scored 0/1.
