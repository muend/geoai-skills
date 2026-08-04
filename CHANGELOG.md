# Changelog

All notable changes to this repository are documented here.
Versioning follows [SemVer](https://semver.org). Each skill also carries its
own `metadata.version` in its frontmatter.

## [Unreleased]

### Changed
- Replaced the demo animation. Its fourth frame previously showed
  `change-detection` and `remote-sensing-analysis` activating together on a
  multi-date prompt — a routing behaviour the 2026-08-04 benchmark disproved in
  this same repository, where `change-detection` takes those prompts alone. The
  frame now lists what the method requires (matched phenology, consistent
  processing level, shared valid-pixel mask, registration evidence) and makes no
  claim about which skills activate. A new frame reports the current routing
  figures with the qualifier "Routing only. Answer quality is not claimed."
- Added `assets/demo/asset-manifest.json` recording what the frames assert, and
  a test pinning those assertions to `BENCHMARK.md`. A future benchmark run can
  no longer leave stale numbers animating at the top of the README.

## [0.3.0] — 2026-08-04

### Changed
- Published a current 18-skill, 158-case routing result measured on
  2026-08-04 under Claude Code `2.1.214` with `claude-sonnet-5`: **100%
  precision, 92.37% recall, 93.67% full-route accuracy**, suite
  `f03e327a57d2…`. The paired skills-disabled control recorded zero
  activations across all 158 cases. This replaces the `superseded` state that
  `BENCHMARK.md` and the README had carried since `arcgis-pro-automation` was
  added; the archived 120-case package remains available as evidence for its
  own suite and must not be pooled with this one.
- Disclosed that this run spent the 62-case held-out half
  (assignment `a82ce97903b2…`). Gate C's disclosure line is recorded in the
  published package README. Subsequent changes that improve a held-out case
  must be justified on their own merits and cannot be presented as independent
  confirmation.
- Recorded the first measured `skills-enabled` routing cost rate, 0.1279
  USD-equivalent per case over 158 cases. The previous 0.0939 figure was an
  unmeasured estimate of the same class that had already proven 6.3x low for
  disabled routing.
- Documented a routing boundary defect found during the mandatory manual
  review: `change-detection` absorbs four multi-date comparability cases that
  belong to `remote-sensing-analysis`, `point-cloud-lidar`, and
  `google-earth-engine`. It scores 100% on its own nine cases while causing
  four other skills' misses, which the precision metric structurally cannot
  detect. `BENCHMARK.md` now states that per-skill recall, not precision, is
  the boundary-health signal.
- Reframed the README around the repository's differentiator—guarding
  geospatial claims against silent CRS, leakage, validity, unit, phenology,
  overlap, and uncertainty failures—with the quick start and evidence boundary
  moved ahead of the full catalog.
- Added a lightweight deterministic GIF, MP4, and static frame demonstrating
  how a season-mismatched Sentinel-2 request is intercepted before an
  unsupported changed-hectares claim is reported.
- Corrected the README's current evaluation inventory to 158 native cases plus
  five separately reported executable GeoAnalystBench-derived transfer cases,
  and clearly labeled the archived 17-skill routing result as superseded.

### Added
- A separately immutable `geoanalystbench-derived-contracts-v3` semantic
  validator and paired `geoanalystbench-producer-interface-v3`. The new
  condition preserves the five-case v1 population and all historical v1/v2
  evidence while replacing hidden byte-for-byte reference coupling with
  disclosed semantic structures, bounded numeric tolerance, exact artifact
  inventory, and representation-independent SVG checks. Run/result schemas,
  deterministic prompt rendering, offline evaluation, and a v3 run template
  now fail closed on the paired v3 hashes.
- A separately frozen `geoanalystbench-producer-interface-v2` condition that
  keeps the five external cases and strict validators unchanged while adding
  answer-safe method conventions, exact path/null/mask serialization, UTF-8
  output guidance, and workspace-local execution hints. Run/result schemas now
  accept only correctly paired v1 or v2 interface IDs and hashes, and a v2 run
  template supports future evidence collection without rewriting v1 history.
- A frozen, answer-safe `geoanalystbench-producer-interface-v1` layer that
  exposes only artifact paths, field names, formats, and method evidence to a
  model. It excludes reference outputs, expected analytical values, and
  validator source. Run/result schema v3 records the exact interface hash and
  a deterministic prompt SHA-256 for every case, so prompt drift fails before
  invocation and historical results remain distinguishable by condition.
- A separately frozen `geoanalystbench-derived-contracts-v2` artifact-contract
  layer for the unchanged five-case v1 population. Each case now separates
  semantic correctness, evidence sufficiency, and representation/schema
  compliance while preserving the original strict validator and exact
  inventory as the pass gate. Cross-hash validation prevents the v2 taxonomy
  from drifting away from the immutable v1 case and validator bytes.
- An immutable `geoanalystbench-derived-v1` source manifest that pins the five
  external case IDs, upstream task IDs and commit, reporting boundary, and
  SHA-256 digest of every governed suite source file, with fail-closed CI tests
  for changed bytes and unregistered case-local files.
- A model-neutral external-run manifest, offline preflight, artifact evaluator,
  machine-readable result schema, and public result-card template. The protocol
  pins runtime/model/package versions and the v1 freeze hash, enforces five
  one-shot calls with zero automatic retries and an explicit cost cap, records
  response and artifact hashes, and prevents external results from being pooled
  with the native 158-case suite. Schema v2 separates observed activation,
  bounded runtime completion, strict artifact-contract compliance, and overall
  success; it still validates artifacts left by failed or timed-out runtimes and
  flags calls exceeding the timeout plus five-second termination grace.
- A MiniMax Code / MiniMax-M3 manual runtime profile with reproducible import
  metadata, two-call skill-activation smoke tests, explicit provider-internal
  retry observability, and a gated path into the frozen five-case run. No
  MiniMax API adapter or model call is included.

## [0.2.0] — 2026-07-28

Initial public plugin release. The OpenAI Plugins Directory release is live;
the independent Claude Code marketplace package is ready for clean-install
verification and community-directory review.

### Added
- An isolated GeoAnalystBench-derived external transfer-suite scaffold and its
  five planned executable cases: deterministic synthetic directed travel-time
  routing with forbidden-turn validation, plus demand-weighted facility
  coverage with network barriers, overlap deduplication, and unreachable
  demand, plus masked SAVI vegetation change with scale, threshold
  sensitivity, pixel-area, phenology, registration, and provenance controls,
  plus projected ordinary kriging with variogram diagnostics, spatial-block
  validation, uncertainty-gated vulnerability, and accessible map checks,
  plus OLS-first spatial regression with residual Moran diagnostics, blocked
  model selection, VIF exclusion, FDR uncertainty, and unstable-region
  warnings.
  External results remain separate from native benchmark hashes and claims.
- A non-publishing, manually dispatchable release-candidate workflow that
  builds and checksum-verifies all 18 archives on a GitHub runner, retains the
  result for seven days, and cannot create tags or release assets.
- A public release runbook with clean-install evidence gates for Skills CLI,
  Claude, Codex, OpenAI, GitHub Copilot, individual ZIP files, and generic
  Agent Skills runtimes, plus explicit failure and rollback rules.
- GitHub Copilot installation instructions using both the official `gh skill`
  preview/install flow and the Skills CLI `github-copilot` target.
- Deterministic, individually uploadable ZIP archives for all 18 skills, an
  ordered `SHA256SUMS` manifest, fail-closed runtime-file selection, and a
  release-only workflow that builds from the exact tag and attaches generated
  files without committing them as source.
- Claude Code marketplace and plugin discovery metadata, stable `geoai`
  namespace documentation, terminal and interactive installation commands,
  and contract tests that keep the Claude, OpenAI, and Python package versions
  aligned.
- A validated skills-only OpenAI plugin manifest, public privacy and terms
  pages, and a deterministic upload-bundle builder that includes the 18 runtime
  skill trees while excluding evals, benchmark evidence, and development files.
- A square, small-size-safe GeoAI brand asset wired as both the OpenAI plugin
  logo and composer icon, with package tests for PNG dimensions and inclusion.
- A read-only, weekly and manually dispatchable external HTTPS link monitor
  with immutable action/tool pins, bounded retries, and non-blocking reports.
- Deterministic CI validation for repository-local Markdown paths, exact path
  casing, repository boundaries, and heading anchors.
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
- OpenAI Codex CLI judge adapter with read-only ephemeral isolation, stdin-only
  private prompts, strict structured output, tool-use rejection, bounded
  non-retrying invocations, resumable traces, and explicit disclosure that
  subscription cost and resolved provider model version are not observable.
- Provider-neutral atomic-clause judging: exact registered criteria can be
  flattened into material clauses, model evidence is collected per atom, and
  parent `all`/`any` decisions are derived deterministically. Unregistered
  criteria remain backwards-compatible single clauses; candidate models still
  require independent calibration before their judgments support a claim.
- Repo tooling: `tools/validate_skills.py` frontmatter/structure linter,
  GitHub Actions CI, plugin marketplace manifest.

### Fixed
- Moved all canonical evaluation definitions and fixtures from runtime skill
  directories to `evals/cases/<skill>/`, preventing repository-based Skills
  CLI installs from copying development-only rubric and fixture material into Claude,
  Codex, Copilot, or other agent runtime directories.
- Replaced four retired documentation URLs with their current official Codex,
  JRC, r5py, and ASPRS LAS targets after the external-link monitor identified
  persistent 404 responses.
- Codex CLI judge subprocess capture now decodes stdout and stderr explicitly as
  UTF-8 instead of inheriting the Windows locale code page, and normalizes
  missing streams so capture failures produce an auditable failed trace rather
  than an unexpected exception.
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

- `tools/check_regression_gates.py` adds two CI gates that need no model budget.
  Gate A pins every expected and forbidden criterion against
  `evals/rubric-baseline.json`, so a criterion can be added or decomposed into
  declared finer criteria but never silently deleted or reworded away — the
  cheapest way to make a failing score improve. Gate B recomputes the current
  suite hash and requires every published benchmark to declare itself `current`
  or `superseded`, failing when that declaration disagrees with the computed
  truth. Neither gate asserts that quality is good; they prevent a requirement
  from disappearing and a stale number from presenting itself as current.
- The published routing benchmark now declares itself `superseded` in both
  `BENCHMARK.md` and its evidence-package README, naming the six skills revised
  since it was frozen. Its figures remain valid and reproducible for the suite
  they were computed against, and are no longer presented as describing the
  skills shipped today.

- `movement-trajectory` no longer treats an unknown CRS or timezone as grounds to
  withhold the method. The earlier rule — "an unknown input CRS or timezone is a
  question to ask, not a default to assume" — read as licence to stop: a measured
  run showed two delivery cases collapse into bare requests for the file, one of
  them despite a prompt that stated every defect explicitly. The assumption must
  now be declared and named alongside the delivered cleaning steps, parameters,
  and sensitivity check. Asking in place of answering is now an explicit failure;
  silent UTC coercion remains prohibited.
- `google-earth-engine` now documents the local-versus-Earth-Engine decision its
  own description already claimed to cover but the body omitted entirely. The new
  section precedes the implementation guidance and turns on archive extent,
  algorithm expressibility, data locality, interactive-versus-batch limits, export
  volume, and reproducibility cost — the last of which now links the provenance
  record, so choosing Earth Engine surfaces the obligation rather than leaving it
  in an unreferenced later section.

- The Claude Code adapter no longer creates execution workspaces inside the
  repository. They had been placed under `evals/runs/` to dodge a Windows 8.3
  short `TEMP` path that made in-scope writes look out of scope. That leaked
  exactly what the disabled condition exists to hide: with the working directory
  inside the repository, the `Read` tool granted to **both** conditions could
  open `skills/*/SKILL.md`, so `skills-disabled` measured "skill not
  auto-invoked" rather than "skill unavailable". Disabling the `Skill` tool
  prevents invocation, not reading. The short-path problem is now solved at
  source by expanding the Windows long path name, the workspace returns to system
  temp, and a runtime assertion plus regression tests fail loudly if a workspace
  ever resolves inside the repository again.

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
