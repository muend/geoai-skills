# GeoAI Agent Skills — Accelerated Execution Roadmap

Last updated: 2026-07-19

## Objective

Build the strongest vendor-neutral, English-first GeoAI Agent Skills repository: executable, benchmarked, portable across major agent runtimes, scientifically defensible, and positioned for 1,000+ GitHub stars.

## Operating rules

- Treat `skills/` as the only canonical source of skill content.
- Mark a task complete only when its artifact exists and its verification passes.
- Update this file after every completed task.
- Prefer measurable skill uplift over adding more untested skills.
- Keep `SKILL.md` concise; move deterministic work to `scripts/` and detailed material to `references/`.
- Do not publish unverifiable claims, trophy cases, benchmark numbers, or compatibility badges.

## Responsibility split

| Workstream | Codex direct role | User role |
|---|---:|---:|
| Repository restructuring, code, skills, tests, CI, docs | 95% | 5% approvals |
| Eval harness and local benchmarks | 90% | 10% model credentials/compute if required |
| Packaging and release preparation | 90% | 10% account authorization |
| GitHub publication and marketplace submission | 75% | 25% authentication/final approval |
| Community growth and real-world proof | 55% | 45% identity, posting, relationships, user evidence |
| **Whole project** | **85%** | **15%** |

Codex can prepare every file, command, release note, benchmark, demo, issue, PR, and launch post. The user remains responsible for irreversible/public account actions, ownership decisions, credentials, and confirming that real-world claims are genuine.

## Current progress

**31 / 49 tasks complete — 63%**

### Phase 0 — Audit and direction

- [x] Inventory all 17 published skills, scripts, references, evals, manifests, and repository documents.
- [x] Run the local validator: 17 skills, 0 errors, 0 warnings.
- [x] Identify duplicate and divergent skill sources outside the canonical repository folder.
- [x] Inspect direct and adjacent competitors: Mapbox Agent Skills, Scientific Agent Skills/GeoMaster, OpenGeo GeoAI Skills, GeoAgent, and GeoSkills.
- [x] Score current content and repository maturity using a 100-point rubric.
- [x] Identify high-demand gaps: foundation models, QGIS automation, cloud-native delivery, responsible GeoAI, and behavioral benchmarking.
- [x] Create this accelerated, checkbox-based execution roadmap.

### Phase 1 — Canonicalize and make claims honest

- [x] **USER CHECKPOINT:** Keep the public repository name `geoai-skills` and the plugin name `geoai`.
- [x] Establish `geoai-skills/` as the single canonical Git repository root.
- [x] Archive 23 divergent root-level legacy items in `../legacy-pre-rebuild-2026-07-19/` after confirming `skills/` as canonical.
- [x] Stop tracking generated `.pyc`, `__pycache__`, and `.skill` build outputs; add a complete `.gitignore`.
- [x] Change the pre-proof release state from `1.0.0` to the honest pre-release version `0.1.0`.
- [x] Reconcile README, CHANGELOG, manifests, badges, URLs, skill count, and release claims.
- [x] Replace unverifiable trophy entries with clearly labeled illustrative failure cases and an evidence contract for real cases.
- [x] Define the core installation profile and standalone fallback policy so cherry-picked skills do not silently assume sibling skills.
- [x] Add repository governance: `SECURITY.md`, `CODE_OF_CONDUCT.md`, `CITATION.cff`, issue templates, PR template, and `CODEOWNERS`.

**Phase 1 gate:** one canonical source tree; no generated artifacts; every public claim is machine-verifiable or evidence-linked.

### Phase 2 — Repair and harden the existing 17 skills

- [x] Audit all descriptions for over-triggering, overlap, negative boundaries, and universal English.
- [x] Narrow `geoai-orchestrator` to ambiguous or multi-stage workflows.
- [x] Narrow `swe-devops-standards` to a geospatial delivery scope.
- [x] Narrow `ml-experiment-standards` so it does not hijack generic EDA/statistics tasks.
- [x] Add explicit selection boundaries between remote sensing, change detection, deep learning, and Earth Engine.
- [x] Standardize every skill on: workflow, decision rules, verification protocol, failure modes, and deliverables.
- [x] Add authoritative references and freshness metadata for time-sensitive APIs/methods.
- [x] Fix `clean_vector.py` so deduplication cannot remove distinct geometries with identical attributes.
- [x] Harden `ahp_weights.py` for shape, positivity, finiteness, diagonal, reciprocity, and supported matrix sizes.
- [x] Add pytest coverage for every bundled script, including edge and failure cases (13 tests passing).
- [x] Add `agents/openai.yaml` metadata for all skills and validate it against each `SKILL.md`.
- [x] Run official Agent Skills validation in addition to the repository linter.

**Phase 2 gate:** all 17 skills pass structural validation, script tests, reference checks, and trigger-overlap review.

### Phase 3 — Build measurable skill quality

- [x] Define and validate a strict eval JSON schema.
- [x] Build a deterministic eval runner with cached raw outputs and machine-readable results.
- [x] Expand the suite to at least 120 cases: positive, negative, ambiguous/collision, and artifact correctness.
- [ ] Measure trigger precision, trigger recall, behavior pass rate, and critical spatial failure rate.
- [ ] Run skill-enabled versus skill-disabled baselines on supported agent runtimes.
- [ ] Adapt a license-compatible subset of GeoAnalystBench as end-to-end tasks.
- [ ] Generate `BENCHMARK.md`, `metrics.json`, and per-skill result summaries from raw results.
- [ ] Add CI regression thresholds so a skill change cannot silently reduce routing or behavior quality.

**Phase 3 gate:** at least 90% trigger precision/recall, at least 85% behavior pass rate, and under 2% critical spatial failure rate on the declared benchmark.

### Phase 4 — Add executable, high-demand differentiation

- [ ] Create `geospatial-foundation-models` with TorchGeo/SamGeo/Earth-embedding decision and validation workflows.
- [ ] Create `qgis-python-automation` with safe PyQGIS inspection, processing, styling, export, and mutation gates.
- [ ] Create or extract `cloud-native-geospatial` for STAC, COG, GeoParquet, Zarr, DuckDB Spatial, H3/S2, PMTiles, and cost/performance decisions.
- [ ] Create `responsible-geoai` for spatial privacy, sampling bias, geographic transfer, uncertainty, and release safety.
- [ ] Add at least five small, reproducible hero demos with open data and expected artifacts.
- [ ] Add visual before/after evidence for CRS safety, leakage prevention, change detection, foundation-model inference, and QGIS automation.

**Phase 4 gate:** each new skill has executable evidence, tests, negative evals, a verification protocol, and a demo artifact.

### Phase 5 — Package, publish, and launch

- [ ] Support and smoke-test Claude plugin, Codex plugin, Open Plugins, Skills CLI, and documented GitHub Copilot installation.
- [ ] Run CI on Linux, Windows, and macOS; add lint, tests, links, manifests, packaging, and security scans.
- [ ] Produce reproducible `.skill` archives and checksums during releases rather than committing them as sources.
- [ ] Create a release candidate and install it into clean environments using every documented installation method.
- [ ] Prepare the GitHub description, topics, social preview, release notes, demo GIF, launch post, and contribution backlog.
- [ ] **USER CHECKPOINT:** Approve repository identity, authorship, real case-study claims, and public release text.
- [ ] **USER CHECKPOINT:** Authorize or perform GitHub push, marketplace submissions, and public announcements.

**Phase 5 gate:** a clean user can install, trigger, execute, and verify the suite from the public repository without undocumented local state.

## Compressed schedule

| Sprint | Target | Primary output |
|---|---|---|
| Sprint 1 | 1 focused workday | Canonical repo, honest metadata, repaired scripts, stronger CI |
| Sprint 2 | 1–2 focused workdays | Trigger rewrite, standardized skill contracts, complete tests |
| Sprint 3 | 2–3 focused workdays | Eval runner, 120+ cases, baseline comparison, benchmark report |
| Sprint 4 | 2–3 focused workdays | High-demand skills, hero demos, multi-runtime packaging |
| Launch | 1 focused workday | Release candidate, clean-install checks, launch assets |

The implementation can be compressed to roughly **7–10 focused working days**, subject to model/API credentials, benchmark runtime, and user approval at public checkpoints. Elapsed calendar time is not required to be 90 days.

## Immediate next action

Measure trigger precision, trigger recall, behavior pass rate, and critical spatial failure rate on declared runtime/model pairs.

Runtime adapter status: Claude Code execution and criterion-preserving judging are prepared; real runs require an authenticated Claude Code session and an explicitly approved cost cap.
