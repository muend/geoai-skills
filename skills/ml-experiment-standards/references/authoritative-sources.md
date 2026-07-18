# Authoritative sources

- Last verified: 2026-07-19
- Review cadence: every 3 months
- Refresh triggers: scikit-learn or PyTorch major release; metric or split API change

## Canonical sources

- [scikit-learn cross-validation guide](https://scikit-learn.org/stable/modules/cross_validation.html) — split and evaluation APIs.
- [scikit-learn common pitfalls](https://scikit-learn.org/stable/common_pitfalls.html) — leakage, preprocessing, and reproducibility risks.
- [PyTorch reproducibility notes](https://docs.pytorch.org/docs/stable/notes/randomness.html) — deterministic execution limits.

Pin implementations and record split units, seeds, preprocessing fit scope, metric definitions, and dependency versions. Re-run baselines after dependency upgrades.
