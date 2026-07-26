"""Right steps, wrong order, still wrong.

Measured behaviour: ``before`` was the most frequently missed word across all
failed criteria (7 occurrences), ``after`` the fourth (4). The model reliably
lists the correct operations and reliably gets their sequence wrong. Some of
these orderings are not stylistic — reversing them invalidates the result:

* correct for multiplicity **before** mapping clusters, or the map shows noise;
* split spatially **before** fitting any preprocessing, or the fold leaks;
* mask cloud **before** compositing, or the composite bakes in cloud;
* reproject **before** measuring, or the measurement is in degrees;
* touch the held-out set **after** model selection, once.

This module holds a small registry of such constraints and checks an observed
pipeline against it. It is a graph check, not a text check: it takes the list
of steps a pipeline actually ran.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .result import Result, abstained, failed, passed

CHECK = "pipeline.ordering"


@dataclass(frozen=True)
class OrderingRule:
    earlier: str
    later: str
    because: str
    severity: str = "invalidating"


REGISTRY: tuple[OrderingRule, ...] = (
    OrderingRule(
        "multiplicity_correction",
        "cluster_map",
        "an uncorrected local statistic maps chance as a cluster",
    ),
    OrderingRule(
        "spatial_split",
        "fit_preprocessing",
        "preprocessing fitted on all data leaks the test fold's distribution",
    ),
    OrderingRule(
        "spatial_split",
        "hyperparameter_search",
        "tuning against spatially adjacent folds reports optimistic scores",
    ),
    OrderingRule(
        "cloud_mask",
        "composite",
        "compositing before masking bakes cloud into the output",
    ),
    OrderingRule(
        "reproject",
        "measure",
        "measuring before reprojecting returns degrees, not metres",
    ),
    OrderingRule(
        "fill_sinks",
        "flow_direction",
        "undrained depressions terminate flow paths",
    ),
    OrderingRule(
        "model_selection",
        "touch_holdout",
        "the held-out set is consumed by the first look at it",
    ),
    OrderingRule(
        "geometry_validity_check",
        "spatial_join",
        "invalid geometry silently drops or duplicates join results",
    ),
    OrderingRule(
        "harmonise_processing_level",
        "difference_scenes",
        "differencing across processing levels measures the correction",
    ),
    OrderingRule(
        "declare_class_breaks",
        "render_map_series",
        "per-date breaks make panels incomparable",
    ),
)


def check_pipeline_order(
    steps: Sequence[str],
    *,
    rules: Sequence[OrderingRule] = REGISTRY,
) -> Result:
    """Fail when an observed pipeline violates a registered ordering rule.

    Steps not mentioned in any rule are ignored. A rule whose two steps are not
    both present is not applicable — absence is a coverage question, not an
    ordering violation, and this check does not conflate them.
    """
    if not steps:
        return abstained(CHECK, "no pipeline steps supplied")

    position: dict[str, int] = {}
    for index, step in enumerate(steps):
        key = step.strip().lower()
        position.setdefault(key, index)

    applicable = [r for r in rules if r.earlier in position and r.later in position]
    if not applicable:
        return abstained(
            CHECK,
            "no registered ordering rule applies to these steps",
            steps=list(position),
        )

    violations = [r for r in applicable if position[r.earlier] > position[r.later]]

    if violations:
        return failed(
            CHECK,
            f"{len(violations)} ordering violation(s) out of {len(applicable)} "
            f"applicable rule(s)",
            evidence=[
                f"{r.later} (step {position[r.later] + 1}) precedes {r.earlier} "
                f"(step {position[r.earlier] + 1}): {r.because}"
                for r in violations
            ],
            n_applicable=len(applicable),
            n_violations=len(violations),
        )

    return passed(
        CHECK,
        f"all {len(applicable)} applicable ordering rule(s) hold",
        n_applicable=len(applicable),
    )


def explain(step: str) -> list[str]:
    """Return the ordering obligations attached to a step, for skill authors."""
    key = step.strip().lower()
    lines: list[str] = []
    for rule in REGISTRY:
        if rule.earlier == key:
            lines.append(f"must run BEFORE {rule.later}: {rule.because}")
        if rule.later == key:
            lines.append(f"must run AFTER {rule.earlier}: {rule.because}")
    return lines
