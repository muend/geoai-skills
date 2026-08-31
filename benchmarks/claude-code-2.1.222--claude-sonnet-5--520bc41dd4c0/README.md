# Claude Code 2.1.222 / Claude Sonnet 5 — behavior, full suite

Sanitized evidence package for the repository's **first behaviour measurement**.
Routing, measured separately in [BENCHMARK.md](../../BENCHMARK.md), records which
skill activated. This package records what the answer that followed contained,
scored criterion by criterion against criteria pinned before the run.

Behavior status: `judged_model_only_uncalibrated`. Criterion-level judgments come
from a single model judge of a **different family** from the evaluated model.
**There is no human verification, and the judge calibration gate recorded in the
project roadmap remains fail-closed.** Every figure below carries that limit.

## Headline

| Measure | Skills enabled | Control | Matched sign test |
|---|---:|---:|---|
| Criterion coverage | **145/302 (48.0%)** | **85/302 (28.1%)** | 65 W / 5 L / 232 T · n=70 · **p = 2.2e-14** |
| Cases meeting every criterion | 18/92 | 6/92 | 42 W / 3 L / 47 T · n=45 · **p = 8.7e-10** |
| Critical subset, case level | 17 W / 1 L / 15 T | — | n=18 · **p = 1.4e-4** |
| **Critical spatial failures** | **4/92 (4.3%)** | **13/92 (14.1%)** | — |
| Forbidden-behaviour violations | 0 | 0 | — |
| Skill activation | 92/92 | **0/92** | control arm clean |

Two things are true at once and both belong in any reading of this run.

**The effect is real.** At criterion level the enabled arm wins 65 discordant
comparisons and loses 5. Critical spatial failures — an area or distance measured
in an angular CRS, a generalisation claim from a random spatial split, a change
claim from non-comparable observations, a release of re-identifiable locations,
an unguarded destructive mutation — fall from 13 cases to 4.

**The absolute level is well short of the project's own bar.** The enabled arm
satisfies 48% of the criteria this repository wrote for itself, and meets every
criterion in 18 of 92 cases. The Phase 3 gate (>=85% pass rate, <2% critical
spatial failure) **fails on both conditions** and stays open. That is published
here rather than deferred until the number improves.

Note also that 232 of 302 criteria are ties. The measured difference rests on 70
discordant criteria, and 18 of the 93 cases carry only two criteria each and
cannot separate the arms by construction.

## Provenance

- Suite state: `current` — derived from the shipped 167-case suite via `--scope behavior`
- Judge: OpenAI Codex CLI 0.145.0, `gpt-5.6-sol`, reasoning effort `low`, prompt `geoai-behavior-judge-v6`
- Judge family: different from the evaluated model; **uncalibrated**, no human verification
- Evaluation scope: `behavior`
- Runtime: `claude-code-2.1.222`
- Model: `claude-sonnet-5`
- Conditions: `skills-enabled` and `skills-disabled`
- Responses: 93/93 in each condition
- Clean matched pairs: **92**
- Execution errors: 1 in each condition, the same case (see below)
- Suite SHA-256: `520bc41dd4c044d128407ff517f808ba4c39ed24d96898272e70326728082a4f`
- Run date: 2026-08-30
- Workers: 4 · `--max-turns` 6 · no per-case cost cap
- Cost: 18.80 USD-equivalent, subscription quota, `isUsingOverage` false in every trace, `apiKeySource: none`
- Retry policy: primary records retained; no error replaced by a retry
- Pre-registration: `behavior-run-preregistration-2026-08-29.md`, SHA-256
  `EA2D564FA9571196D8EDDD33ABD341E3BC939D9059E7744DDD2D09030EB1B21E`,
  sealed before the first model call; addenda 01 and 02 recorded separately

Held-out disclosure: b2ab0305ffc81a1989c327bda2ce8d20c5450170653e543f49ab5dbd73cc8b54

The run covers the full split. The held-out half was spent
once on the 2026-08-05 routing run; this run measures behavior, a dimension
never measured on these cases, and they will not be iterated against afterwards.

### Relationship to the routing card

The published [routing benchmark](../../BENCHMARK.md) was measured on Claude
Code `2.1.214`, suite `efe27d8c1736…`. This run is on `2.1.222`, suite
`520bc41dd4c0…`, because the CLI updated between the two and the adapter's
provenance gate refused to stamp responses with a version that did not produce
them. **The two are different runtime versions on different suites and must not
be pooled or read as continuous.** Both arms of *this* run are on `2.1.222`,
which is what a matched comparison requires.

## What the control arm did

The `skills-disabled` condition used the same model, runtime, prompts and
non-skill tool configuration, with every Agent Skill removed and the working
directory isolated so the `Read` tool could not reach `skills/*/SKILL.md`.

It recorded **zero activations across all 93 cases.** The pair is valid: the
adapter is not inventing activation evidence and no skill source leaked into
the control.

## What the enabled arm did

- Activation: 92/92 clean pairs.
- Expected route satisfied: 92/92.
- All 18 skills activated on every one of their own cases.
- Responses were longer: median 1656 characters against 836 in the control, a
  factor of 1.98; mean output 2334 tokens against 1285.

Longer is not better. It is reported because it is measured, and because a
judge scoring these responses should know the two corpora differ in length
before scoring them.

## The one error — and it is not symmetric

`swe-devops-standards/review-mode` failed in both conditions of the primary run.
It was retried once, in a separately suffixed directory, under the same frozen
parameters. Across the two attempts:

| Attempt | skills-enabled | skills-disabled |
|---|---|---|
| Primary | exit `3221226505` (`0xC0000409`), empty stream, $0.0000 | `max_turns`, 151 s, $0.3699 |
| Retry 1 | `max_turns`, 191.4 s, $0.5615, 19 701 output tokens, 3 artifacts, **final response empty** | **completed**, 96.5 s, $0.2785, 1 611 characters, 3 artifacts |

**The skills-enabled arm has not delivered a final answer for this case in two
attempts. The control arm delivered one on its second.**

An earlier version of this file called the primary enabled failure "an
infrastructure failure, not model behavior." That reading is withdrawn. Two
attempts produced two different failure modes in the same arm while the other
arm went from failure to success, and on this prompt the enabled arm produced
1.85× the output tokens and took 1.98× the wall time of the control before
running out of turns. Load is at least as plausible an explanation as the
runtime.

A diagnostic at `--max-turns 12`, **outside the frozen parameters and therefore
excluded from every metric here**, hit `max_turns` again: 262.4 s, $0.8563,
27 605 output tokens, `num_turns` 13, `stop_reason: tool_use`.

The artifact records settle what the response field alone suggested wrongly.
**Every run produced all three required artifacts**, content captured and
hashed:

| Run | `review.md` | `ingest_fixed.py` | `test_ingest_fixed.py` | final response |
|---|---:|---:|---:|---|
| enabled, 12 turns (diagnostic) | 7 099 B | 4 488 B | 5 458 B | empty |
| enabled, 6 turns (retry) | 6 133 B | 3 193 B | 3 466 B | empty |
| disabled, 6 turns (retry) | 5 396 B | 2 033 B | 2 937 B | 1 611 chars |

This is an `artifact-producing` case whose required-artifact contract names
exactly those three paths and whose criteria describe their content. The enabled
arm is not failing to produce the deliverable. **It produces the deliverable and
then does not stop.** The failure is termination, not work.

The extra turns accumulate rather than repeat — every artifact grew between the
6- and 12-turn runs (+16%, +40%, +57%) — and the enabled artifacts are 1.14–2.21×
the control's at both budgets. Whether larger is better is a judging question;
the hashes are on record for it. Routing was correct: the case is a PostGIS
ingest review and both activated skills, `postgis-spatial-sql` and
`swe-devops-standards`, are in scope.

What is established, and belongs in any reading of this run: on the one case
that failed, the arm that failed to terminate is the skills-enabled arm, and it
cost 3.1× the control and ran 2.7× as long to reach that state.

Both primary records are preserved unchanged. Per the pre-registration a failure
is never replaced by a retry; the retry lives in its own directory. The case is
excluded from the 92 matched pairs.

The overall execution error rate is 1/93 = 1.1% per condition in the primary
run. The comparable routing run recorded 9/167 and 2/167.

## Files

| File | Contents |
|---|---|
| `cases.jsonl` | One row per case per condition: activation, route match, cost, tokens, latency, error, `response_sha256`, `trace_sha256` |
| `metrics.json` | Case mix, per-condition totals, pairing, control-arm cleanliness |
| `per-skill.json` | Per-skill counts, errors, activation, cost and tokens in each condition |

**Response text is not published here.** Only its SHA-256 and length. The raw
responses stay in the gitignored run directory until the blind human review is
complete — publishing the corpus first would let a reviewer read it outside the
protocol. The hashes are sufficient to prove that whatever is judged later is
what was produced now.

## What this package does not support

- Any claim about answer quality, in either condition.
- Any comparison with the routing card's numbers.
- Any model-independent claim: one runtime, one model, one run.
- Any claim about the three behavior-classed negative cases as a population.

## What this package does not support — restated because the numbers are strong

- **No human verification.** A model judged these responses. Agreement with human
  judgment has not been measured, so the coverage figures carry an unquantified
  judge error term.
- **The judge calibration gate is still fail-closed.** This run did not attempt
  to pass it and does not.
- **One runtime, one model, one run.** Nothing here is model-independent, and
  run-to-run variance on this suite is unmeasured.
- **No claim that the Phase 3 gate is met.** It is not.

Human blind adjudication of 47 cases (33 critical + 14 stratified, arm-blinded)
is prepared and pending reviewers. When it lands, per-criterion agreement with
this model pass is computed and published whatever it shows; where the two
differ, human adjudication governs, and if agreement is poor this package is
marked superseded rather than quietly kept. That commitment was made in
pre-registration addendum 03, before any judgment existed.
