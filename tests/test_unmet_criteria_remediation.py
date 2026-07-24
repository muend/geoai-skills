"""Contract tests for the second remediation round.

Review of the unmet criteria on the audited behaviour subset separated genuine
product gaps from conjunctive-rubric artefacts. This module locks both outcomes:

* the four skill contracts added to close real gaps
  (geo-deep-learning label characterisation, movement-trajectory CRS/UTC
  declaration, postgis typed stored column, google-earth-engine provenance);
* the three criterion splits, asserting that decomposition preserved every
  original requirement rather than dropping or softening any of them.

The split assertions matter more than they look: a conjunctive row can always be
made to "pass" by quietly deleting one of its conjuncts, and these tests make
that visible.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _skill(name: str) -> str:
    text = (ROOT / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
    return " ".join(text.split())


def _case(skill: str, case_id: str) -> dict:
    path = ROOT / "skills" / skill / "evals" / "evals.json"
    suite = json.loads(path.read_text(encoding="utf-8"))
    return next(case for case in suite["evals"] if case["id"] == case_id)


# --------------------------------------------------------------------------
# Product gap 1 — geo-deep-learning must characterise labels before advising
# --------------------------------------------------------------------------


def test_label_characterisation_precedes_architecture_table() -> None:
    text = (ROOT / "skills" / "geo-deep-learning" / "SKILL.md").read_text(
        encoding="utf-8"
    )

    assert text.index(
        "## Characterise the label set before naming an architecture"
    ) < text.index("## Problem framing first")


def test_label_characterisation_enumerates_what_to_establish() -> None:
    skill = _skill("geo-deep-learning")

    for requirement in (
        "**Label count and labelled area**",
        "**Geographic spread**",
        "**Class balance and minority-class pixel fraction**",
        "**Deployment geography**",
    ):
        assert requirement in skill


def test_unconditional_architecture_recommendation_is_forbidden() -> None:
    skill = _skill("geo-deep-learning")

    assert (
        'Do not answer "fine-tune a large model or use a simpler approach" '
        "before these are known" in skill
    )
    assert "never a single unconditional recommendation" in skill


# --------------------------------------------------------------------------
# Product gap 2 — movement-trajectory must declare CRS and UTC before thresholds
# --------------------------------------------------------------------------


def test_crs_and_time_base_are_declared_before_any_threshold() -> None:
    skill = _skill("movement-trajectory")

    assert "### Declare CRS and time base before any threshold" in skill
    assert "**The projected CRS**" in skill
    assert "**The timestamp base**, normalised to timezone-aware UTC" in skill
    assert (
        "State both before proposing a radius or duration, not afterwards as a caveat"
        in skill
    )


def test_unknown_crs_or_timezone_is_a_question_not_a_default() -> None:
    skill = _skill("movement-trajectory")

    assert "that is a question to ask, not a default to assume" in skill
    assert "never silently treat naive timestamps as UTC" in skill


# --------------------------------------------------------------------------
# Product gap 3 — postgis stored geometry columns must be typed with an SRID
# --------------------------------------------------------------------------


def test_recommended_stored_column_must_be_typed_with_srid() -> None:
    skill = _skill("postgis-spatial-sql")

    assert (
        "**Any stored geometry column you recommend must be typed with its SRID.**"
        in skill
    )
    assert "geometry(MultiPolygon, 32633)" in skill
    assert "ST_Transform(geom, 32633)" in skill
    assert "reintroduces the mixed-SRID problem it was meant to solve" in skill


# --------------------------------------------------------------------------
# Product gap 4 — google-earth-engine must ship a provenance record
# --------------------------------------------------------------------------


def test_provenance_record_is_a_named_deliverable() -> None:
    skill = _skill("google-earth-engine")

    assert "## Provenance record" in skill
    assert "emitted as a sidecar JSON next to the export" in skill
    assert "not left in the notebook" in skill


def test_provenance_record_fields_are_enumerated() -> None:
    skill = _skill("google-earth-engine")

    for field in (
        "**Catalog asset IDs with their version suffix**",
        "**Mask method and thresholds**",
        "**Reducers and their arguments**",
        "**Export parameters**",
        "**Run date and the `ee.__version__` / API client version**",
    ):
        assert field in skill


def test_platform_recommendation_must_address_reproducibility_cost() -> None:
    skill = _skill("google-earth-engine")

    assert (
        "Recommending Earth Engine over a local workflow is incomplete without this"
        in skill
    )


# --------------------------------------------------------------------------
# Criterion splits — decomposition must preserve every original requirement
# --------------------------------------------------------------------------


def test_leakage_audit_split_preserves_all_four_requirements() -> None:
    criteria = _case("ml-experiment-standards", "leakage-pipeline-audit")[
        "expected_behavior"
    ]
    joined = " ".join(criteria).lower()

    assert "requires all-fold metrics, uncertainty, overlap checks" not in joined
    assert any("across all folds" in c and "uncertainty" in c for c in criteria)
    assert any("overlap check" in c.lower() for c in criteria)
    assert any("held-out final test policy" in c for c in criteria)
    assert len(criteria) == 5


def test_crs_loss_audit_split_preserves_all_four_accountings() -> None:
    criteria = _case("geo-data-engineering", "crs-loss-audit")["expected_behavior"]
    joined = " ".join(criteria).lower()

    assert "row, null-geometry, validity, and extent accounting" not in joined
    for accounting in ("row-count", "null-geometry", "validity", "extent"):
        assert accounting in joined
    assert len(criteria) == 4


def test_platform_choice_split_separates_quota_from_provenance() -> None:
    criteria = _case("google-earth-engine", "unclear-platform-choice")[
        "expected_behavior"
    ]
    joined = " ".join(criteria).lower()

    assert "quota-aware batching and provenance plan" not in joined
    assert any("quota-aware batching" in c for c in criteria)
    assert any("provenance record" in c for c in criteria)
    assert len(criteria) == 4
