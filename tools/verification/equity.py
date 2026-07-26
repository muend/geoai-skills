"""A city mean is not an access finding.

Measured behaviour: "Reports per-group distributions for equity, not just city
means" scored 17%. The model computes average travel time to the nearest
hospital, reports one number, and the number is true and useless: it is
compatible with universal adequate access and with one district having none.

This module produces the disaggregated view and refuses the aggregate-only
report. It also computes the two summary statistics that survive scrutiny —
the ratio between the worst-served and best-served group, and the share of each
group beyond a policy threshold — because "the mean is 18 minutes" answers no
question anyone actually asked.

Pure standard library; ``statistics`` only.
"""

from __future__ import annotations

import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .result import Result, abstained, failed, passed

CHECK = "equity.disaggregated"


@dataclass(frozen=True)
class GroupSummary:
    group: str
    n: int
    mean: float
    median: float
    p90: float
    share_beyond_threshold: float | None


def _percentile(values: Sequence[float], q: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    position = q * (len(ordered) - 1)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return float(ordered[lower] * (1 - weight) + ordered[upper] * weight)


def summarise_by_group(
    values_by_group: Mapping[str, Sequence[float]],
    *,
    threshold: float | None = None,
) -> list[GroupSummary]:
    """Per-group mean, median, p90 and share beyond a policy threshold."""
    summaries: list[GroupSummary] = []
    for group in sorted(values_by_group):
        values = [float(v) for v in values_by_group[group]]
        if not values:
            continue
        beyond = (
            sum(1 for v in values if v > threshold) / len(values)
            if threshold is not None
            else None
        )
        summaries.append(
            GroupSummary(
                group=group,
                n=len(values),
                mean=statistics.fmean(values),
                median=statistics.median(values),
                p90=_percentile(values, 0.90),
                share_beyond_threshold=beyond,
            )
        )
    return summaries


def disparity_ratio(summaries: Sequence[GroupSummary]) -> float | None:
    """Worst group mean divided by best group mean. 1.0 means parity."""
    if len(summaries) < 2:
        return None
    means = [s.mean for s in summaries if s.mean > 0]
    if len(means) < 2:
        return None
    return max(means) / min(means)


def check_disaggregation(
    values_by_group: Mapping[str, Sequence[float]],
    *,
    threshold: float | None = None,
    reported_groups: Sequence[str] | None = None,
    disparity_alarm: float = 1.25,
) -> Result:
    """Fail when a report collapses groups, or hides a large disparity.

    Two distinct failures are caught here. The first is procedural: fewer
    groups were reported than exist. The second is substantive: the groups were
    reported but the spread between them is large enough that presenting a
    pooled figure alongside them would mislead.
    """
    if not values_by_group:
        return abstained(CHECK, "no grouped values supplied")
    if len(values_by_group) < 2:
        return abstained(
            CHECK, "only one group supplied; disaggregation cannot be assessed"
        )

    summaries = summarise_by_group(values_by_group, threshold=threshold)
    if len(summaries) < 2:
        return abstained(CHECK, "fewer than two non-empty groups")

    if reported_groups is not None:
        missing = sorted(set(values_by_group) - set(reported_groups))
        if missing:
            return failed(
                CHECK,
                f"{len(missing)} group(s) present in the data but absent from the "
                f"report",
                evidence=[f"unreported: {g}" for g in missing],
                n_groups=len(summaries),
            )

    ratio = disparity_ratio(summaries)
    rows = [
        f"{s.group}: n={s.n} mean={s.mean:.1f} median={s.median:.1f} p90={s.p90:.1f}"
        + (
            f" beyond={s.share_beyond_threshold:.0%}"
            if s.share_beyond_threshold is not None
            else ""
        )
        for s in summaries
    ]

    if ratio is not None and ratio >= disparity_alarm:
        worst = max(summaries, key=lambda s: s.mean)
        best = min(summaries, key=lambda s: s.mean)
        return failed(
            CHECK,
            f"disparity ratio {ratio:.2f} between {worst.group} and {best.group}; "
            f"a pooled mean would conceal it",
            evidence=rows
            + [
                f"{worst.group} mean={worst.mean:.1f} vs {best.group} "
                f"mean={best.mean:.1f}",
                "report per-group distributions, not the pooled figure",
            ],
            disparity_ratio=ratio,
            n_groups=len(summaries),
        )

    return passed(
        CHECK,
        f"{len(summaries)} groups reported"
        + (f", disparity ratio {ratio:.2f}" if ratio is not None else ""),
        disparity_ratio=ratio,
        n_groups=len(summaries),
    )
