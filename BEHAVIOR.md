# Behavior evidence

Status date: **2026-09-02**

Current status: **model-judged only, uncalibrated, not human-verified**

Routing answers whether the intended specialist activated. This card answers a
different question: what happened to pinned answer criteria when the skills
were present under one matched runtime/model experiment?

## Current measurement

The current package contains 93 responses in each arm and 92 clean matched
pairs on Claude Code `2.1.222` with `claude-sonnet-5`. The judge was a different
model family: Codex CLI `0.145.0`, `gpt-5.6-sol`, low reasoning, prompt
`geoai-behavior-judge-v6`.

| Measure | Skills enabled | Skills disabled |
|---|---:|---:|
| Criterion coverage | **145/302 (48.0%)** | **85/302 (28.1%)** |
| Cases meeting every criterion | **18/92 (19.6%)** | **6/92 (6.5%)** |
| Critical spatial failures | **4/92 (4.3%)** | **13/92 (14.1%)** |
| Forbidden-behavior violations | **0** | **0** |
| Recorded skill activation | **92/92** | **0/92** |

The enabled arm won 65 and lost 5 of the 70 discordant criterion comparisons
(`p = 2.2e-14`, exact two-sided sign test). This is evidence of a measured
effect in this run. It is not evidence that the absolute quality bar was met.

## Gate result

The project gate requires both:

- at least **85%** of cases meeting every pinned criterion; and
- less than **2%** critical spatial failures.

The enabled arm reached **19.6%** and **4.3%** respectively. The gate therefore
**fails on both conditions** and remains open.

## Human-review boundary

Forty-seven arm-blinded cases (33 critical and 14 stratified) have been prepared
for human review. The current public evidence does not contain completed
adjudication for that sample. Until it does:

- do not call these results human verified;
- do not use the judge as a calibrated gold standard;
- do not publish raw response text that could contaminate the blind review; and
- retain response hashes and sizes so the reviewed material remains
  identifiable.

## Known execution defect

`swe-devops-standards/review-mode` is excluded from the 92 clean pairs. The
enabled arm produced all three required artifacts but did not terminate within
the frozen six-turn budget; a 12-turn diagnostic also failed to terminate. This
is a delivery/termination defect, not missing artifact production, and remains
open.

## What this supports

- A paired improvement was measured for one runtime, model, suite, and run.
- The skills-disabled control recorded no activations.
- Critical failures were observed less often with skills in this run.
- The absolute behavior bar remains unmet.

## What this does not support

- model-independent or runtime-independent quality claims;
- a human-verified answer-quality claim;
- pooling with the routing benchmark;
- a claim that every critical failure class improved;
- a before/after claim against a future suite with a different population.

The immutable evidence, provenance, cost, token counts, excluded case, hashes,
and limitations are in the
[full behavior package](benchmarks/claude-code-2.1.222--claude-sonnet-5--520bc41dd4c0/README.md).
The next steps and release gate are in [ROADMAP.md](ROADMAP.md).
