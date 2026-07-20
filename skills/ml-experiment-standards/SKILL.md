---
name: ml-experiment-standards
description: >-
  Always invoke for training, validating, tuning, benchmarking, or claiming
  readiness of a predictive model. Covers leakage audits, spatial and grouped
  splits, metrics, reproducibility, and honest reporting. Invoke especially
  when spatial dependence, split design, or deployment geography is unknown;
  uncertainty is a reason to use this skill. Do not trigger for descriptive
  EDA or non-predictive statistical inference.
license: MIT
metadata:
  version: "0.1.0"
  author: Muhammed Enes Duran
---

# ML Experiment Standards

Purpose: every ML job (quick prototypes included) is reproducible,
leakage-free, and metric-justified. These are not optional polish; every
skipped item typically returns as "the model collapsed in production" or
"the result didn't replicate".

## 1. EDA comes first

Before any model, produce and show: distributions, missingness rates,
outliers, target balance, salient correlations. Metric and loss choice
depend on this information; a model recommendation without EDA is a guess.

## 2. Leakage audit

At every split decision, answer explicitly (and write the answer as a code
comment): "Does the training set contain indirect information about any
test sample?"

| Data type | Correct split | Why |
|---|---|---|
| Independent samples | Stratified k-fold | Preserves class ratios |
| Time series | TimeSeriesSplit / walk-forward | Future must not leak into past |
| **Spatial data** | Spatial block CV — see `references/spatial-cv-protocol.md` | Neighbors are near-duplicates |
| Grouped data (patient, parcel, scene) | GroupKFold | A group must not straddle the split |

- Scalers/encoders/imputers are **fit on train only**; the clean path is
  `sklearn.pipeline.Pipeline` — CV then fits correctly by construction.
- Target-derived features (target encoding etc.) must be computed
  out-of-fold, and shown to be.

The spatial protocol in `references/spatial-cv-protocol.md` is the single
canonical source for this repo — other skills link here; do not restate it.

## 3. Metric selection — justified

Never choose a metric by default; write a one-sentence rationale:

- Imbalanced classes → **F1 / AUC-PR**, not accuracy (accuracy rewards
  majority-class memorization).
- Segmentation → **IoU/Dice** (pixel accuracy is inflated by background).
- Regression → RMSE (sensitive to large errors) vs MAE (robust) vs R²
  (variance explained) — justify from the use case.
- Every point estimate gets uncertainty: bootstrap CI or mean ± std across
  CV folds. A single number hides whether a difference is signal or noise.

## 4. Reproducibility skeleton

Every training script follows this shape (script-first; no notebook magic):

```python
"""Experiment: <name>. Goal and success criterion: <one sentence>."""
from dataclasses import dataclass, asdict
import json, random
import numpy as np

@dataclass
class Config:
    seed: int = 42
    lr: float = 1e-3
    batch_size: int = 32
    epochs: int = 100
    patience: int = 10  # early stopping

def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    # if torch: torch.manual_seed(seed); torch.cuda.manual_seed_all(seed)

def main(cfg: Config) -> None:
    set_seed(cfg.seed)
    ...  # data -> split -> pipeline -> train -> evaluate
    with open("runs/run_meta.json", "w", encoding="utf-8") as f:
        json.dump({"config": asdict(cfg), "metrics": metrics}, f, indent=2)

if __name__ == "__main__":
    main(Config())
```

- Config lives in a dataclass/YAML, never hardcoded — sweeps and run
  comparison depend on it.
- Pin library versions (`pip freeze > requirements.txt`).
- Use MLflow/W&B when available; the JSON log above is the minimum.

## 5. Deep learning extras

- **Loss rationale**: Dice/Dice+CE for imbalanced segmentation; write why.
  Focal only after comparison — not a free win.
- **Augmentation rationale**: state which transforms respect the physics
  of the problem (orientation-dependent tasks forbid some rotations;
  multispectral forbids naive color jitter).
- **Overfitting control**: early stopping with patience + a train/val
  curve in the report; no curve, no "the model is good".
- **Capacity order**: small model + simple baseline first (logistic
  regression, RF); a deep model that can't beat the baseline is a data
  problem, not an architecture problem.
- EO-specific chipping/inference details → `geo-deep-learning`.

## 6. System context (MLOps)

Position every model in its chain in one paragraph: data source →
cleaning → features/versioning → training → evaluation → deployment
(batch/real-time) → monitoring (data/model drift). Even for a prototype,
note "what this step becomes in production".

## 7. Report format

```
## Experiment: <name>
- Data: n=<>, split: <strategy + rationale>
- Baseline: <model> → <metric ± CI>
- Model: <model> → <metric ± CI>
- Leakage audit: <what was checked>
- Next step: <single recommendation>
```

When reporting differences, respect statistical honesty: if the gap
doesn't exceed the across-fold std, say "no clear difference" — no
p-hacking, no selective reporting.

## Execution contract

- **Workflow:** define prediction target and decision use; establish a baseline; audit leakage; create spatially valid splits; train reproducibly; quantify uncertainty; inspect errors and deployment fit.
- **Decision rules:** apply this skill only to predictive model experiments; use spatial statistics for inference, geostatistics for sampled-surface estimation, and descriptive analysis without forcing a model.
- **Verification protocol:** reproduce from a clean environment, compare against baseline across folds or seeds, inspect spatial residuals, verify split independence, and test the final decision threshold.
- **Failure modes:** invalidate uplift claims for leakage, post-split preprocessing, inappropriate metrics, non-independent test units, selective runs, or train-serving skew.
- **Deliverables:** experiment configuration, split and seed manifest, baseline and model metrics with uncertainty, leakage audit, error analysis, artifacts, and deployment caveats.
- **Source freshness:** consult [the authoritative source registry](references/authoritative-sources.md) before using version-sensitive split, metric, or reproducibility APIs.
