"""Regression tests for the point-cloud-lidar vertical datum recording contract.

Review of the `vertical-datum-audit` case found that the criterion "Records the
verified vertical datum and transformation in output metadata" went unsatisfied
even when the datum itself was correctly resolved: a response could diagnose
the ellipsoidal/orthometric mix, build a per-tile offset table and reproject to
a consistent vertical CRS, then persist none of it into an output product.

The root cause was an omission in SKILL.md, not a model failure — the
verification protocol asked only that the datum be *reported* in the answer.
These tests keep the resolve/transform/record obligation explicit and keep
recording distinct from reporting.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "point-cloud-lidar" / "SKILL.md"
EVALS = ROOT / "skills" / "point-cloud-lidar" / "evals" / "evals.json"


def _skill_text() -> str:
    return SKILL.read_text(encoding="utf-8")


def _normalized_skill_text() -> str:
    return " ".join(_skill_text().split())


def _case(case_id: str) -> dict:
    suite = json.loads(EVALS.read_text(encoding="utf-8"))
    return next(case for case in suite["evals"] if case["id"] == case_id)


def test_datum_section_separates_recording_from_reporting() -> None:
    """The observed failure was reporting-instead-of-recording; name it."""
    normalized = _normalized_skill_text()

    assert "## Vertical datum: resolve, transform, record" in _skill_text()
    assert "**Stating the datum in your answer is not recording it.**" in normalized
    assert "Record it into the output, not just the reply" in normalized


def test_datum_section_states_all_three_obligations() -> None:
    normalized = _normalized_skill_text()

    for obligation in ("**Resolve.**", "**Transform.**"):
        assert obligation in normalized
    assert "Never infer a datum from elevation magnitude alone" in normalized


def test_recorded_metadata_fields_are_enumerated() -> None:
    """Recording is only actionable if the required fields are concrete."""
    normalized = _normalized_skill_text()

    for field in (
        "the compound or vertical CRS written into the file itself",
        "geoid model name and version",
        "transformation pipeline or EPSG operation code",
        "per-tile offsets applied",
        "the source of truth used to resolve an originally missing datum",
        "residual strip-edge disagreement after correction",
    ):
        assert field in normalized


def test_unresolvable_datum_still_requires_a_recorded_metadata_block() -> None:
    """Silence must not be an escape hatch when the datum cannot be resolved."""
    normalized = _normalized_skill_text()

    assert (
        "never publish a height product whose vertical datum is unresolved"
        in normalized
    )
    assert "labelled provisional with the unresolved datum recorded" in normalized
    assert "silence is not an option" in normalized


def test_verification_protocol_requires_persistence_not_just_a_report() -> None:
    normalized = _normalized_skill_text()

    assert (
        "confirm the verified vertical datum, geoid model, and transformation "
        "were written into the output metadata before the product is considered delivered"
        in normalized
    )


def test_pitfalls_checklist_names_the_resolved_but_unrecorded_case() -> None:
    normalized = _normalized_skill_text()

    assert (
        "Vertical datum resolved during the audit but never written into the "
        "delivered product's metadata" in normalized
    )


def test_execution_contract_carries_the_recording_obligation() -> None:
    normalized = _normalized_skill_text()

    assert (
        "Never resolve a vertical datum and then ship the product without that "
        "datum and its transformation recorded in the output metadata" in normalized
    )
    assert "not only into the answer text" in normalized


def test_vertical_datum_audit_forbids_reporting_in_place_of_recording() -> None:
    forbidden = _case("vertical-datum-audit")["forbidden_behavior"]

    assert any(
        "stating the vertical datum in the answer as satisfying" in item
        for item in forbidden
    )
    assert any(
        "without the applied geoid model, transformation, and any per-tile offsets"
        in item
        for item in forbidden
    )


def test_expected_criteria_were_not_relaxed() -> None:
    """Hardening must be additive; the original criteria stay verbatim."""
    case = _case("vertical-datum-audit")

    assert case["expected_behavior"] == [
        (
            "Stops height comparison until horizontal and vertical CRS and geoid "
            "transformations are resolved"
        ),
        "Checks overlapping strips and tile seams numerically and with cross-sections",
        "Records the verified vertical datum and transformation in output metadata",
    ]


def test_sfm_boundary_survives_the_datum_hardening() -> None:
    """The adjacent critical SfM case must keep its canopy-penetration guard."""
    normalized = _normalized_skill_text()
    sfm = _case("sfm-not-lidar")

    assert sfm["critical"] is True
    assert 'A "DTM" from SfM over forest is a canopy model.' in normalized
    assert "no canopy penetration" in normalized
