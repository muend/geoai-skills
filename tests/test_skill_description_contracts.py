from __future__ import annotations

import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parent.parent
SWE_SKILL = ROOT / "skills" / "swe-devops-standards"


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
    suite = json.loads((SWE_SKILL / "evals" / "evals.json").read_text(encoding="utf-8"))
    cases = {case["id"]: case for case in suite["evals"]}

    assert "analysis requesting no code or repository artifact" in description
    assert cases["scientific-crs-choice"]["should_trigger"] is False
    assert cases["scientific-crs-choice"]["expected_route"] == ["geo-data-engineering"]
    assert cases["spatial-validation-design"]["should_trigger"] is False
    assert cases["spatial-validation-design"]["expected_route"] == [
        "ml-experiment-standards"
    ]
