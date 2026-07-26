"""Correct for multiplicity before anything is called significant.

Local spatial statistics — Getis-Ord Gi*, LISA, local Geary — produce one test
per feature. Run them on 800 census tracts at alpha 0.05 and roughly 40 tracts
light up by chance alone. Mapped without correction, those 40 look exactly like
a finding, and the map is persuasive precisely because it is spatial.

Two procedures, and the choice matters here more than in aspatial work:

* Benjamini-Hochberg controls the false discovery rate under independence or
  positive regression dependence.
* Benjamini-Yekutieli holds under arbitrary dependence at the cost of power.

Local statistics on contiguous units are *not* independent — that is the whole
premise of the analysis. When the caller does not choose, this module refuses
to pick silently: ``method="auto"`` selects BY and says so in the result, on
the principle that the conservative choice is the defensible default when
dependence is known to exist.

Pure standard library. No scipy, no numpy.
"""

from __future__ import annotations

from .result import Result, abstained, failed, passed

CHECK = "stats.multiplicity"


def _validate(p_values: list[float]) -> str | None:
    if not p_values:
        return "no p-values supplied"
    for index, value in enumerate(p_values):
        if not isinstance(value, (int, float)):
            return f"p-value at position {index} is not numeric: {value!r}"
        if value != value:  # NaN
            return f"p-value at position {index} is NaN"
        if not 0.0 <= float(value) <= 1.0:
            return f"p-value at position {index} is outside [0, 1]: {value}"
    return None


def benjamini_hochberg(p_values: list[float]) -> list[float]:
    """Return BH-adjusted p-values in the caller's original order."""
    n = len(p_values)
    order = sorted(range(n), key=lambda i: p_values[i])
    adjusted = [0.0] * n
    running = 1.0
    for rank, index in enumerate(reversed(order), start=1):
        position = n - rank + 1
        candidate = p_values[index] * n / position
        running = min(running, candidate)
        adjusted[index] = min(1.0, running)
    return adjusted


def benjamini_yekutieli(p_values: list[float]) -> list[float]:
    """BH scaled by the harmonic number; valid under arbitrary dependence."""
    n = len(p_values)
    harmonic = sum(1.0 / k for k in range(1, n + 1))
    return [min(1.0, value * harmonic) for value in benjamini_hochberg(p_values)]


def adjust(
    p_values: list[float],
    *,
    alpha: float = 0.05,
    method: str = "auto",
    dependent: bool = True,
) -> dict:
    """Adjust p-values and report which survive.

    ``method="auto"`` picks BY when ``dependent`` is true, which is the normal
    case for local spatial statistics on contiguous units.
    """
    problem = _validate(p_values)
    if problem:
        raise ValueError(problem)
    if not 0.0 < alpha < 1.0:
        raise ValueError(f"alpha must be in (0, 1); got {alpha}")

    chosen = method
    rationale = f"method={method} as requested"
    if method == "auto":
        chosen = "benjamini-yekutieli" if dependent else "benjamini-hochberg"
        rationale = (
            "auto selected Benjamini-Yekutieli because the tests were declared "
            "dependent; local spatial statistics on contiguous units are "
            "dependent by construction"
            if dependent
            else "auto selected Benjamini-Hochberg because independence was declared"
        )

    if chosen in ("bh", "benjamini-hochberg"):
        adjusted = benjamini_hochberg(list(p_values))
    elif chosen in ("by", "benjamini-yekutieli"):
        adjusted = benjamini_yekutieli(list(p_values))
    else:
        raise ValueError(f"unknown method: {method!r}")

    rejected = [value <= alpha for value in adjusted]
    naive = sum(1 for value in p_values if value <= alpha)
    return {
        "method": chosen,
        "rationale": rationale,
        "alpha": alpha,
        "n_tests": len(p_values),
        "adjusted": adjusted,
        "rejected": rejected,
        "n_rejected": sum(rejected),
        "n_rejected_uncorrected": naive,
        "n_false_positives_avoided": naive - sum(rejected),
        "expected_false_positives_uncorrected": round(alpha * len(p_values), 2),
    }


def check_correction_applied(
    reported_significant: int,
    p_values: list[float],
    *,
    alpha: float = 0.05,
    method: str = "auto",
    dependent: bool = True,
) -> Result:
    """Fail when the reported cluster count matches the uncorrected count.

    This is the check a skill contract runs before a cluster map is published:
    if the number of "significant" features equals the naive count, no
    correction was applied.
    """
    problem = _validate(p_values)
    if problem:
        return abstained(CHECK, problem)

    outcome = adjust(p_values, alpha=alpha, method=method, dependent=dependent)
    naive = outcome["n_rejected_uncorrected"]
    corrected = outcome["n_rejected"]

    if reported_significant == naive and naive != corrected:
        return failed(
            CHECK,
            f"{reported_significant} features reported significant, which is the "
            f"uncorrected count; {outcome['method']} leaves {corrected}",
            evidence=[
                f"n_tests={outcome['n_tests']}, alpha={alpha}",
                f"uncorrected rejections={naive}",
                f"{outcome['method']} rejections={corrected}",
                f"expected false positives without correction="
                f"{outcome['expected_false_positives_uncorrected']}",
            ],
            **{k: outcome[k] for k in ("method", "n_tests", "n_rejected")},
        )

    if reported_significant > corrected:
        return failed(
            CHECK,
            f"{reported_significant} reported but only {corrected} survive "
            f"{outcome['method']} at alpha={alpha}",
            evidence=[f"adjusted rejections={corrected}"],
            method=outcome["method"],
        )

    return passed(
        CHECK,
        f"{reported_significant} reported, consistent with {outcome['method']} "
        f"({corrected} survive at alpha={alpha})",
        method=outcome["method"],
        n_tests=outcome["n_tests"],
        n_rejected=corrected,
    )
