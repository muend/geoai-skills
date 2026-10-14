# GeoAI Agents 0.1.0 preview — verification record

Date: 2026-10-14. Implementation is local; no release or repository push occurred.
Machine-readable identities and observations are in `verification.json`.

## Delivered

- A separately versioned, optional `agent-kit/` with six canonical roles, 18 skill
  bindings, explicit control ownership, and 12 generated native agent definitions.
- Versioned task, artifact, review, failure and run contracts; evidence-bound
  delivery decisions; no more than two repair rounds; local-only failure records.
- Preview-first project installation, conflicts without overwriting, independent
  runtime manifests, reproducible ZIP creation and unchanged legacy verifier copies.
- Six bounded executable checks, 18 synthetic pilot cases, 36 routing scenarios,
  isolated three-condition workspace preparation and evidence-aware comparison.
- A new `.github/workflows/agent-kit.yml` for offline validation on Windows/Linux.
  Existing workflows and all other pre-addon tracked files remain unchanged.

## Observed checks

| Check | Result |
|---|---|
| Captured pre-addon files | 308 unchanged |
| Frozen skill tree | runtime-v2, unchanged |
| Existing native benchmark gates | A/B/C pass, 167 cases |
| Addon tests | 69 pass |
| Reused legacy verifier regression tests | 130 pass |
| Six synthetic pilots | All 18 expected outcomes matched |
| Generated adapters | 6 Codex TOML and 6 Claude frontmatters parse; generation current |
| Lint | Pass |
| CI on GitHub | Added, not remotely executed |

The 18 pilot outcomes include intentional FAIL and ABSTAIN results. Matching those
outcomes is a validator test result, not successful geographic verification of
all fixtures. Old benchmark gates are integrity checks, not new model measurements.

The protected skill-tree identity remains:

```text
65023155d5324da86ce08f3aafadd9f52a3f9dc5fe7e3b0755aa4baef829a04e
```

The complete local inventory and exact committed-blob inventory are independently
pinned. Their skill bytes are identical; 148 non-skill files differ only in LF/CRLF
checkout representation. No native hash algorithm or frozen record was changed.

## Limits and remaining milestones

The Codex CLI smoke on a development snapshot returned ABSTAIN because the host's
read-only policy blocked required commands. It created no deliverable and delegated
no subagents. The trace identity and tested snapshot identity are recorded, and the
run is excluded from comparison. It is not proof of a successful native workflow.

The Claude live call was initially rejected by automatic approval review over
repository-content transmission scope. The user then explicitly declined live
Claude execution. No Claude model call was run. Offline format and installation
contracts were tested; native execution remains unverified.

Consequently, milestone 3 has a built and tested package but lacks successful
native end-to-end evidence. Milestone 4 has synthetic validator coverage, not six
completed agent field studies. Milestone 5 has evaluation infrastructure and a
protocol, but no eligible paired model results, performance gain or cost estimate.
Milestone 6 is a local preview, not a production-validated release.

Neither original PlaceTwin incident has been reproduced. The walking and line
fixtures are synthetic analogues. Resolving the actual incidents requires original
exports, location/data snapshots and the affected generation/rendering pipeline.

Use `python agent-kit/tools/validate.py` for the source release gate. Install both
runtime and development requirements first. Tests use a new owned scratch folder;
earlier Windows shared-temp/dependency ACL errors were not counted as passes.
