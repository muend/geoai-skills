# Governance

GeoAI Skills is currently maintainer-led. The maintainer is responsible for
scope, releases, evidence publication, security response, and the final merge
decision. Contributions and independent criticism are welcome; a benchmark
claim does not become true by maintainer preference.

## Decision principles

Decisions are made in this order:

1. geographic and scientific correctness;
2. user and data safety;
3. reproducibility and inspectable evidence;
4. cross-runtime portability;
5. usability and maintenance cost; and
6. collection breadth.

A lower item cannot overrule a higher one. In particular, a shorter answer,
cleaner headline, or larger skill count does not justify hiding a failed gate or
weakening a safety criterion.

## Evidence hierarchy

From strongest to weakest for project claims:

1. independently reproducible artifacts with human-adjudicated results;
2. preregistered paired measurements with immutable machine-readable evidence;
3. deterministic validators and regression tests;
4. model-judged or single-runtime observations with disclosed limitations;
5. illustrative examples and maintainer opinion.

Lower layers remain useful, but must be labelled and cannot be promoted by
wording. Published packages are append-only in meaning: corrections create a
new record and mark the old one superseded.

## Skill and evaluation changes

- One specialist owns each primary methodological decision; cross-skill
  coordination does not erase specialist boundaries.
- A new or materially changed skill requires positive and negative coverage,
  collision coverage where relevant, verification and failure behavior.
- Results already observed cannot be treated as fresh independent evidence.
- Criteria may be decomposed or strengthened with an explicit migration, but
  not silently weakened to improve a score.
- Runtime packages must not contain benchmark cases, private planning material,
  or evaluation answers.

## Releases

The maintainer cuts releases only after the checks in [RELEASING.md](RELEASING.md)
and the applicable gate in [ROADMAP.md](ROADMAP.md) pass. Tag protection,
deterministic per-skill archives, `SHA256SUMS`, clean-install checks, and rollback
instructions are part of the release contract.

## Changes to this governance

Governance changes use a pull request and explain why the previous rule no
longer fits. Changes that weaken evidence or security boundaries require an
explicit migration note and may not rewrite historical results.
