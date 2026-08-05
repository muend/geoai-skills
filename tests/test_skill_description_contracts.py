from __future__ import annotations

import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "skills"
CASES = ROOT / "evals" / "cases"
SWE_SKILL = SKILLS / "swe-devops-standards"
SWE_EVALS = CASES / "swe-devops-standards" / "evals.json"


def description_of(skill: str) -> str:
    return str(load_frontmatter(SKILLS / skill / "SKILL.md")["description"])


def case_ids(skill: str) -> set[str]:
    suite = json.loads((CASES / skill / "evals.json").read_text(encoding="utf-8"))
    return {case["id"] for case in suite["evals"]}


def load_frontmatter(skill_file: Path) -> dict[str, object]:
    text = skill_file.read_text(encoding="utf-8")
    frontmatter = text.split("\n---", 1)[0].removeprefix("---")
    metadata = yaml.safe_load(frontmatter)
    assert isinstance(metadata, dict)
    return metadata


def test_swe_description_front_loads_review_and_repair_intent() -> None:
    metadata = load_frontmatter(SWE_SKILL / "SKILL.md")
    description = str(metadata["description"])

    assert description.startswith(
        "Always invoke to review, repair, or deliver geospatial or GeoAI code"
    )
    assert "contract compliance" in description
    assert "tests" in description
    assert "even when deployment is not requested" in description


def test_swe_description_preserves_no_code_analysis_boundary() -> None:
    metadata = load_frontmatter(SWE_SKILL / "SKILL.md")
    description = str(metadata["description"])
    suite = json.loads(SWE_EVALS.read_text(encoding="utf-8"))
    cases = {case["id"]: case for case in suite["evals"]}

    assert "analysis requesting no code or repository artifact" in description
    assert cases["scientific-crs-choice"]["should_trigger"] is False
    assert cases["scientific-crs-choice"]["expected_route"] == ["geo-data-engineering"]
    assert cases["spatial-validation-design"]["should_trigger"] is False
    assert cases["spatial-validation-design"]["expected_route"] == [
        "ml-experiment-standards"
    ]


def test_every_skill_declares_mit_and_an_author_and_no_version() -> None:
    """Frontmatter contract for all 18 skills.

    `metadata.version` was removed rather than bumped. Nothing read it — the
    packaging manifests carry the release version and the OpenAI portal
    reported it as `skill_metadata_ignored` — so it was a field that could only
    ever drift, and it did: it sat at 0.1.0 across three releases. Keeping it
    out is cheaper than keeping it correct.
    """
    offenders: dict[str, list[str]] = {}

    for skill_md in sorted(SKILLS.glob("*/SKILL.md")):
        frontmatter = load_frontmatter(skill_md)
        metadata = frontmatter.get("metadata") or {}
        assert isinstance(metadata, dict)

        problems = []
        if frontmatter.get("license") != "MIT":
            problems.append(f"license is {frontmatter.get('license')!r}, expected 'MIT'")
        if "version" in metadata:
            problems.append("declares metadata.version, which was deliberately removed")
        if not metadata.get("author"):
            problems.append("missing metadata.author")
        if problems:
            offenders[skill_md.parent.name] = problems

    assert not offenders, offenders


def test_change_detection_yields_comparability_but_keeps_phenology() -> None:
    """The boundary that produced four of nine false negatives.

    The retired description said "Invoke even when seasons, sensors, or
    processing levels are not comparable". That single conjunction is the
    defect: it lumped three unrelated axes together and claimed all of them.
    Seasonal mismatch genuinely belongs here — it is one of this skill's four
    named impostors, and two of its own critical cases are season traps. Sensor
    and processing-level mismatch never did.
    """
    description = description_of("change-detection")

    assert "not comparable" not in description, (
        "the retired clause that annexed remote-sensing-analysis has returned"
    )

    # Ordering is part of the contract, not style. The first attempt at this
    # boundary put the hand-off last, behind a long list of positive triggers,
    # and the 2026-08-05 pilot showed the router matching the triggers and never
    # reaching the exclusion: change-detection fired on both negative probes.
    # The precondition now leads, and this assertion is what keeps it there.
    head = description[:120]
    assert "comparab" in head, (
        "the comparability precondition must lead; burying it behind the "
        f"positive triggers is what failed in the pilot. Head was: {head!r}"
    )

    assert (
        "mixed sensors, product levels or processing baselines "
        "to remote-sensing-analysis"
    ) in description
    assert "undocumented vertical datums to point-cloud-lidar" in description
    assert "multi-decade archive trends over large areas to google-earth-engine" in description
    assert "Matching product level does not prove comparability" in description

    # Both halves of the phenology carve-out: season stays, and a settled datum
    # stays too. The second half exists because narrowing the boundary cost this
    # skill a case it should have kept.
    assert "Seasonal mismatch is this skill's own confounder" in description
    assert (
        "a documented datum with a stated accuracy budget is settled comparability"
    ) in description


def test_change_detection_keeps_its_season_cases_and_claims_no_others() -> None:
    """Ties the boundary above to the cases on both sides of it."""
    own = case_ids("change-detection")

    assert {"season-trap", "season-confounded-fire-attribution"} <= own, (
        "the season traps are this skill's own positives; narrowing the "
        "boundary must not push them away"
    )

    annexed = {
        "remote-sensing-analysis": {
            "mixed-level-trap",
            "cross-sensor-drought-comparability",
        },
        "point-cloud-lidar": {"mixed-datum-subsidence-refusal"},
        "google-earth-engine": {"trend-map"},
    }
    for owner, ids in annexed.items():
        assert ids <= case_ids(owner), f"{ids} must stay owned by {owner}"
        assert not (ids & own), f"change-detection must not claim {ids & own}"


def test_point_cloud_lidar_owns_cross_acquisition_vertical_comparability() -> None:
    """The datum axis had no owner, so change-detection took it by default.

    The scope clause matters as much as the claim. The first version read
    "whenever two acquisitions are differenced", which swept up cases where the
    datum, geoid and accuracy budget were all stated — the pilot showed this
    skill taking a case that was pure change estimation. Ownership is now bound
    to *unestablished* comparability and hands back once it is documented.
    """
    description = description_of("point-cloud-lidar")

    assert "vertical datum agreement" in description
    assert "differenced" in description
    assert "subsidence" in description
    assert "comparability not yet established" in description, (
        "unscoped ownership is what caused the over-correction"
    )
    assert "is change-detection's" in description, (
        "the hand-back has to be explicit or the boundary only works one way"
    )


def test_remote_sensing_analysis_description_carries_the_baseline_signal() -> None:
    """Routing sees descriptions, not bodies.

    The baseline discontinuity was documented in the body and left out of the
    description on the grounds that no case needed it yet. A case was then
    written for it, and the pilot showed why that was wrong: the prompt says
    "same tile, same month, both L2A" and carries no surface mismatch at all, so
    nothing in any description matched and change-detection took it on the
    strength of "two scenes". A blocker the router cannot see is not a boundary.
    """
    description = description_of("remote-sensing-analysis")

    assert "processing-baseline" in description
    assert "Processing Baseline 04.00" in description
    assert "January 2022" in description
    assert "same product level are not" in description


def test_remote_sensing_analysis_encodes_the_baseline_discontinuity() -> None:
    """Two L2A scenes across 2022-01-25 are not comparable.

    This trap passes the skill's own L1C/L2A table — both scenes are L2A — so
    the level check reports nothing while the digital numbers sit 1000 apart.
    The double-correction half matters just as much: harmonised collections
    have already removed the offset, and applying it again inverts the error
    instead of removing it.
    """
    body = (SKILLS / "remote-sensing-analysis" / "SKILL.md").read_text(encoding="utf-8")

    assert "BOA_ADD_OFFSET" in body
    assert "25 January 2022" in body
    assert "QUANTIFICATION_VALUE" in body
    assert "Do not correct twice" in body
    assert "S2_SR_HARMONIZED" in body
