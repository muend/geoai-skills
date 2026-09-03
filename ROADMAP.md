# GeoAI Skills roadmap

Status date: **2026-09-02**

This is the canonical statement of current priorities. Published measurements
remain immutable in their evidence packages; this roadmap describes what they
support, what they do not support, and what must happen next.

## Current state

| Layer | Shipped evidence | Status |
|---|---|---|
| Runtime skills | 18 independently installable Agent Skills | Stable at `v0.4.1`; no new skill is required for the next release |
| Native routing suite | 167 cases: 124 positive, 43 negative, 40 ambiguous, 51 collision-tagged | Current suite validates with zero errors; dev 105 / held-out 62 |
| Routing measurement | Claude Code `2.1.214`, `claude-sonnet-5`, suite `efe27d8c1736…` | 99.17% precision, 96.77% recall, 96.41% route accuracy; one runtime/model pair only |
| Paired behavior measurement | 92 clean pairs and 302 pinned criteria, suite `520bc41dd4c0…` | Skills improved the measured run, but the project quality gate failed; model-judged and not human-verified |
| External transfer suite | 5 frozen GeoAnalystBench-derived synthetic cases | Deterministic fixtures and artifact validators; reported separately from native metrics |
| Packaging | Codex, Claude, GitHub Copilot, Skills CLI, per-skill release ZIPs | Windows, macOS, and Linux CI; deterministic archives and checksum manifest |
| Runtime integrity | Immutable schema-v2 full-tree registry | `runtime-v1` covers all packaged skill bytes while retaining the legacy native suite SHA unchanged |
| Real-world evidence | No accepted reproducible case | Open gap; illustrative examples are not testimonials |

Routing and behavior are different measurements on different runtime versions
and suite hashes. They must not be pooled. Read [BENCHMARK.md](BENCHMARK.md) and
[BEHAVIOR.md](BEHAVIOR.md) before quoting either.

## Now — evidence closure

The next release is an evidence and reliability release, not a collection-size
release.

- [x] Freeze the complete runtime skill tree independently of the legacy native
  suite identity; future skill changes append a parent-linked freeze rather
  than rewriting earlier SHA-256 evidence.
- [ ] Complete the arm-blinded human review and adjudication of the prepared
  47-case behavior sample. Publish agreement and disagreements, not only a
  corrected headline.
- [ ] Classify the unmet behavior criteria by skill and root cause, then fix the
  smallest high-impact set without tuning against the spent held-out outcomes.
- [ ] Resolve or explicitly retain the `swe-devops-standards/review-mode`
  termination defect: all required artifacts were produced, but the enabled arm
  did not stop within the frozen turn budget.
- [ ] Measure the revised behavior on a newly preregistered case set or other
  unspent evidence. Do not relabel the existing model-judged package as human
  verified.
- [ ] Add at least one privacy-safe, reproducible real-world case with inputs,
  before/after behavior, verification artifacts, environment, and limitations.
- [ ] Replicate a bounded public/synthetic subset on a second runtime or model;
  publish it as a separate card rather than pooling results.

## Next — adoption and independent scrutiny

- [ ] Publish a citable technical report and archive a release on Zenodo or an
  equivalent DOI-bearing repository.
- [ ] Open contribution-sized issues for independent negative cases, real-world
  reproducers, runtime replication, and documentation corrections.
- [ ] Add a small executable hero workflow whose output can be reproduced from
  public data and checked without a proprietary account.
- [ ] Add a full-history secret scan and an OpenSSF Scorecard workflow or record
  a documented reason not to enable them.
- [ ] Refactor the large runtime adapters after the evidence cycle is stable;
  preserve trace and provenance contracts with tests before splitting them.

## Later — new specialist skills

New skills increase collision surface and evaluation cost. They are deferred
until the behavior remediation cycle and human adjudication are complete.
Candidate order:

1. `qgis-python-automation`
2. `cloud-native-geospatial`
3. `responsible-geoai`
4. `geospatial-foundation-models`

Every added specialist must ship positive, negative, ambiguous, and collision
coverage where applicable; executable evidence; a failure contract; and a
clean-install check.

## Candidate `v0.5.0` gate

`v0.5.0` is ready only when:

1. the human-review state is published accurately, including unresolved
   disagreement;
2. the targeted behavior remediation has a preregistered verification result;
3. routing, behavior, external-transfer, and real-world evidence remain
   separate and discoverable;
4. at least one reproducible real-world case is accepted, or the release notes
   explicitly retain this as an open gap;
5. all structural validators, regression gates, link checks, lint, type checks,
   tests, archive builds, and clean-install checks pass; and
6. release notes state the exact runtime, model, suite, retry, error, cost, and
   human-review boundaries of every reported measurement.

## Deliberate non-goals for the next release

- maximizing the number of skills;
- presenting public eval prompts as an untouched hidden test set;
- treating routing accuracy as answer quality;
- converting model judgment into a human-verified claim by wording;
- hiding failed gates, execution errors, or superseded evidence.

See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution rules,
[SUPPORT.md](SUPPORT.md) for the correct reporting channel, and
[GOVERNANCE.md](GOVERNANCE.md) for evidence and release decisions.
