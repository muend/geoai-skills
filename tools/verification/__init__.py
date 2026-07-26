"""geoverify — executable checks for the seven disciplines models skip.

Measured motivation. Across 57 behaviour cases the skills fired 96% of the time
but only ~49% of the expected content reached the answer. The criteria that
went missing were not the methods — the model knows kriging, NDVI and Moran's I
— they were the bookkeeping: provenance, ordering, parameter emission,
multiplicity, comparability, privacy and equity thresholds.

Prose contracts are compressible. A model reading "Verification protocol: test
alternative weights, correct local multiplicity, report uncertainty" summarises
it and drops the dull clause. A command that returns a non-zero exit code
cannot be summarised away.

This package is that mechanism. Every check returns the same ``Result`` type
with three outcomes, and the third one is the reason the package exists:

    PASS     no disqualifying evidence found by this check
    FAIL     a specific, quotable violation
    ABSTAIN  the check could not run — never silently a pass

Standard library only. A verification tool that needs a heavy optional
dependency is a verification tool that gets skipped.
"""

from __future__ import annotations

from .comparability import (
    Scene,
    check_shared_class_breaks,
    compare_scenes,
)
from .crs_units import (
    axis_unit,
    check_planar_operation,
    check_vertical_horizontal_units,
    parse_epsg,
)
from .equity import (
    GroupSummary,
    check_disaggregation,
    disparity_ratio,
    summarise_by_group,
)
from .multiplicity import (
    adjust,
    benjamini_hochberg,
    benjamini_yekutieli,
    check_correction_applied,
)
from .ordering import OrderingRule, check_pipeline_order, explain
from .parameters import (
    ParameterLog,
    REQUIRED_BY_OPERATION,
    check_parameters_emitted,
)
from .privacy import (
    check_k_anonymity,
    check_trip_ends_truncated,
    haversine_m,
    suppress_small_counts,
    truncate_trip_ends,
)
from .provenance import (
    Source,
    build_manifest,
    diff_manifests,
    verify_manifest,
)
from .result import Outcome, Report, Result, abstained, failed, passed

__all__ = [
    # result vocabulary
    "Outcome", "Report", "Result", "passed", "failed", "abstained",
    # crs and units
    "parse_epsg", "axis_unit", "check_planar_operation",
    "check_vertical_horizontal_units",
    # multiplicity
    "benjamini_hochberg", "benjamini_yekutieli", "adjust",
    "check_correction_applied",
    # provenance
    "Source", "build_manifest", "verify_manifest", "diff_manifests",
    # comparability
    "Scene", "compare_scenes", "check_shared_class_breaks",
    # privacy
    "haversine_m", "suppress_small_counts", "check_k_anonymity",
    "truncate_trip_ends", "check_trip_ends_truncated",
    # equity
    "GroupSummary", "summarise_by_group", "disparity_ratio",
    "check_disaggregation",
    # parameters
    "ParameterLog", "REQUIRED_BY_OPERATION", "check_parameters_emitted",
    # ordering
    "OrderingRule", "check_pipeline_order", "explain",
]

__version__ = "0.1.0-prototype"
