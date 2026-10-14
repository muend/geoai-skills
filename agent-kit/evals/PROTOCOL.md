# Separate evaluation protocol, version 1

These are synthetic development cases. They are not a fresh hidden test set.
The 18 cases cover six families with valid, contradictory and missing evidence.
The 36 routing scenarios cover positive and negative use of all 18 skills.
Scenario text coverage does not claim that a model passed all routing scenarios.

## Conditions

1. skills-only: one agent, frozen skills, the matched input and tool payload.
2. structured-single: the same, plus the explicit recorded-check protocol.
3. agent-team: the same protocol and tools, plus separate native role contexts.

Do not give condition 3 exclusive tools. `prepare-evaluation` gives all conditions
the same executable checks and case bytes. Only condition 3 contains the common
role instructions and native agent definitions. Files with expected outcomes stay
in the development repository, outside all prepared workspaces.

For each runtime, pin the model version and configuration, inspect loaded project,
parent and global instructions, hooks, plugins and agents, and retain that inventory.
Use a separate clean runtime profile for each condition. Auth must be provided by
the host's supported flow; never copy credentials into a run or artifact.
If the runtime cannot establish its loaded context, exclude the run. Do not call
an unknown profile clean simply because the project folder looks clean.

Record counterbalanced execution order, fixed budgets and tool access, and use
the same original case for all three conditions. Retain interruptions and quota
failures. A later retry is a new run and must not erase the failed attempt.
Codex and Claude results must remain separate, also separated by model/version.

## Evidence and judgments

Each completed evaluation record follows `schemas/evaluation-run.schema.json`.
Keep its trace, output, runtime-inspection inventory and independent judgment next
to the record, using relative paths and SHA-256 values. `customization_inventory`
must equal the recorded inventory file. Known external instructions/plugins or
extra loaded agents invalidate the declared condition. Environment file changes
and new auto-loaded instructions exclude the affected runs during comparison.

The judgment file contains `output_sha256`, `reviewer_id`, `status: completed`, and
three separate fields, `calculation`, `evidence`, `presentation`. Each is `pass`,
`fail`, `abstain`, or `not-applicable`. Record the rationale and supporting files
alongside these fields; the reviewer must not be the producer. Assess whether the
model reached the appropriate bounded conclusion, not whether it merely echoed
the checker. A correct ABSTAIN on incomplete data can be a passing evaluation
criterion, while the underlying geographic claim remains unverified.

For walking, inspect network support, barrier intersections and access claims.
For line meaning, inspect continuity, visible legend and understandable wording.
For imagery, separate arithmetic from scene comparability and mask accounting.
For terrain, separate slope arithmetic from units, datum and NoData evidence.
For models, inspect split leakage and whether accuracy claims are warranted.
For suitability, assess weight reasoning separately from perturbation arithmetic.

Count valid cases rejected without reason as false rejections; count unsupported
physical or scientific claims as critical failures. Preserve this case-level
reasoning in judgments; do not replace it with one aggregate accuracy number.
`compare` emits complete case judgments, exclusions, missing-run counts and paired
summaries. Summaries include only cases with all three eligible conditions in the
same runtime/model/suite. Unknown cost is null, not zero. The first preview has no
eligible live comparison, so it makes no performance-improvement claim.

## PlaceTwin boundary

The walking and line-meaning fixtures are synthetic analogues. No original
PlaceTwin export, location, network snapshot or rendering pipeline was reproduced.
Obtain those inputs in a separately authorized project task, retain their sharing
status, and reproduce the incident before claiming that the original bug is fixed.
