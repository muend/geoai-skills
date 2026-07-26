# `tools/verification` — executable checks for geospatial discipline

Eleven checks across seven modules, standard library only. A CLI front end lives
at `tools/verify.py` and runs as `python -m tools.verify`.

**Nothing calls this yet, and that is deliberate.** Tools land first and go green
with their tests; skill contracts bind to them afterwards. The reverse order
produces a `SKILL.md` citing a command that does not work.

## Why it exists

Measurement on the 57-case behaviour set said two things:

- the skills **fire** on 55 of 57 cases — routing is solved;
- only about **49%** of the expected content reaches the answer.

The criteria that go missing are not the methods. The model knows kriging, NDVI
and Moran's I. What it drops is the bookkeeping:

| Missing criterion class | Attainment |
|---|---|
| Provenance recorded | 0% |
| Parameters emitted into the output | 0% |
| Multiplicity correction before mapping | 0% |
| Privacy thresholds (k-anonymity, trip-end truncation) | 17% |
| Equity disaggregation | 17% |
| Cross-date comparability | 20% |

The diagnosis is structural rather than a knowledge gap: **prose is
compressible.** A model reading *"Verification protocol: test alternative
weights, correct local multiplicity, report uncertainty"* summarises it and drops
the dull clause. A command that returns a non-zero exit code cannot be summarised
away.

## The three outcomes

```
0  verified      — every check ran and found nothing disqualifying
1  FAILED        — at least one check found a specific, quotable violation
2  NOT VERIFIED  — nothing failed, but at least one check could not run
```

Exit code 2 carries the whole design. **An abstention must never become a pass.**
A tool that cannot see its input has verified nothing, and an analysis that
proceeds on an abstention is proceeding unverified. Malformed JSON, a missing
file, an unrecognised pipeline step: all abstain, none crash — a traceback exits
1, which this tool *defines* as "a violation was found", conflating the two
states the vocabulary exists to separate.

`PASS` is also narrower than it looks. It means "this check found no
disqualifying evidence", not "the work is correct".

## Checks

| Module | Check | What it refuses to let pass |
|---|---|---|
| `crs_units` | `check_planar_operation` | A metric operation on a geographic CRS — a 500 m buffer that is really 500 degrees |
| | `check_vertical_horizontal_units` | Vertical and horizontal units that disagree |
| `ordering` | `check_pipeline_order` | Correct steps in the wrong order |
| `parameters` | `check_parameters_emitted` | A result whose thresholds, radii or class edges never reached the metadata |
| `provenance` | `verify_manifest` | A manifest that cannot support reproduction |
| `multiplicity` | `check_correction_applied` | Hundreds of local tests with the survivors called significant |
| `comparability` | `compare_scenes` | Multi-date comparison across seasons, sensors or processing levels |
| | `check_shared_class_breaks` | A map series whose panels use different class breaks |
| `privacy` | `check_k_anonymity` | A release below the k threshold |
| | `check_trip_ends_truncated` | Individual traces published with their endpoints intact |
| `equity` | `check_disaggregation` | A single mean standing in for a group-level distribution |

## Usage

```bash
python -m tools.verify units buffer --crs EPSG:4326 --value 500
python -m tools.verify provenance --manifest outputs/manifest.json --strict
python -m tools.verify multiplicity --p-values outputs/p.json --reported 12
python -m tools.verify --json comparability --scenes outputs/scenes.json
```

Once Q1 judging closes and skill contracts may be edited, a skill's
`## Verification (Required)` section will be able to say:

```bash
python -m tools.verify parameters kriging --metadata outputs/metadata.json
# a non-zero exit means fix it before declaring success
```

That is the point of the whole layer: a prose instruction is compressible, an
exit code is not.

## Tests

`tests/test_geoverify_*.py`, 130 tests. The ones worth reading first are in
`test_geoverify_cli_robustness.py`: they exist because an earlier version of this
CLI crashed on malformed input and exited 1, violating its own central
distinction.
