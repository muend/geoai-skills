"""Contract tests for the v0.5 behavior-remediation candidate.

These assertions encode general safeguards exposed by the frozen v1 behavior
run. They do not change or rescore the published cases. The candidate must be
measured later on newly preregistered, unspent evidence.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _skill(name: str) -> str:
    text = (ROOT / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
    return " ".join(text.split())


def test_comparative_maps_reject_incomparable_breaks() -> None:
    skill = _skill("cartography-geoviz")

    assert "## Comparative maps are one measurement scale" in skill
    assert "explicitly reject that comparison design" in skill
    for requirement in (
        "shared set of fixed class edges",
        "identical units",
        "same ramp",
        "same NoData treatment",
        "machine-readable metadata",
    ):
        assert requirement in skill


def test_conversion_ledger_reconciles_every_stage() -> None:
    skill = _skill("geo-data-engineering")

    assert "## Every conversion needs a stage ledger" in skill
    for requirement in (
        "row or feature count in and out",
        "null and empty geometry counts",
        "valid and invalid geometry counts",
        "CRS identifier and coordinate units",
        "numeric extent in that CRS",
    ):
        assert requirement in skill
    assert "Never infer a CRS from coordinate ranges alone" in skill
    assert "Reopen the final artifact" in skill


def test_sensitive_attributes_are_not_inferred_from_detected_objects() -> None:
    skill = _skill("geo-deep-learning")

    assert "## Privacy and unsupported inference" in skill
    assert "establish structures; they do **not** establish household occupancy" in skill
    assert "Refuse to assign or publish" in skill
    assert "at least 10 dwellings per released cell" in skill
    for requirement in ("imagery source", "acquisition date", "licence"):
        assert requirement in skill


def test_mcda_cannot_hide_community_burden() -> None:
    skill = _skill("mcda-suitability-analysis")

    assert "## Equity evidence belongs in the decision record" in skill
    assert "Refuse the requested omission" in skill
    assert "burden distributions separately" in skill
    assert "non-compensatory constraints before weighted aggregation" in skill
    assert "test plausible alternatives" in skill


def test_repeated_local_statistics_define_one_multiplicity_family() -> None:
    skill = _skill("spatial-statistics")

    assert "define the complete family of claims before correction" in skill
    assert "space × time × variable family" in skill
    assert "do not correct each day separately" in skill
    for requirement in (
        "effect magnitude",
        "spatial weights definition",
        "permutation count",
        "family size",
        "correction method",
        "q-values",
    ):
        assert requirement in skill


def test_code_delivery_has_a_bounded_termination_contract() -> None:
    skill = _skill("swe-devops-standards")

    assert "## Completion and termination budget" in skill
    assert "Once every required artifact exists, is reopened" in skill
    assert "stop expanding the implementation" in skill
    assert "Finish with one concise response" in skill
    assert "continued calling tools until the runtime stopped" in skill
    assert "terminate instead of looping" in skill
