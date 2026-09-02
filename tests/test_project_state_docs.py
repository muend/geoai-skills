"""Keep public project-state documents aligned with repository evidence."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "skills"
EVAL_CASES = ROOT / "evals" / "cases"
EXTERNAL_CASES = ROOT / "evals" / "external" / "geoanalystbench" / "cases"
BEHAVIOR_PACKAGE = ROOT / "benchmarks" / "claude-code-2.1.222--claude-sonnet-5--520bc41dd4c0"


def read(path: Path) -> str:
    """Read a repository text document as UTF-8."""
    return path.read_text(encoding="utf-8")


def native_case_count() -> int:
    """Return the number of native evaluation cases in the canonical tree."""
    total = 0
    for path in sorted(EVAL_CASES.glob("*/evals.json")):
        payload = json.loads(read(path))
        total += len(payload["evals"])
    return total


def test_roadmap_matches_live_repository_counts() -> None:
    """The canonical roadmap must reflect generated repository counts."""
    roadmap = read(ROOT / "ROADMAP.md")
    skill_count = len([path for path in SKILLS.iterdir() if path.is_dir()])
    external_count = len([path for path in EXTERNAL_CASES.iterdir() if path.is_dir()])

    assert f"| Runtime skills | {skill_count} independently" in roadmap
    assert f"| Native routing suite | {native_case_count()} cases:" in roadmap
    assert f"| External transfer suite | {external_count} frozen" in roadmap


def test_public_status_documents_name_the_current_release() -> None:
    """README, roadmap, and citation metadata must agree on the release."""
    project = tomllib.loads(read(ROOT / "pyproject.toml"))
    version = project["project"]["version"]

    assert f"version `{version}`" in read(ROOT / "README.md")
    assert f"Stable at `v{version}`" in read(ROOT / "ROADMAP.md")
    assert f'version: "{version}"' in read(ROOT / "CITATION.cff")


def test_behavior_card_matches_published_machine_readable_evidence() -> None:
    """Headline behavior numbers must come from the immutable metrics file."""
    card = read(ROOT / "BEHAVIOR.md")
    metrics = json.loads(read(BEHAVIOR_PACKAGE / "metrics.json"))
    results = metrics["behavior"]["results"]

    assert metrics["behavior"]["status"] == "judged_model_only_uncalibrated"
    assert f"{metrics['pairing']['clean_matched_pairs']} clean matched" in card
    assert results["criterion_level"]["enabled_coverage"] in card
    assert results["criterion_level"]["disabled_coverage"] in card
    assert results["case_level"]["enabled_all_criteria_met"] in card
    assert results["case_level"]["disabled_all_criteria_met"] in card
    assert "not human-verified" in card


def test_readme_exposes_the_project_state_documents() -> None:
    """A new visitor must be able to find every current status boundary."""
    readme = read(ROOT / "README.md")

    for document in ("BEHAVIOR.md", "ROADMAP.md", "SUPPORT.md", "GOVERNANCE.md"):
        assert f"]({document})" in readme


def test_real_world_case_count_is_not_overstated() -> None:
    """The empty accepted-case section must remain explicit until populated."""
    case_studies = read(ROOT / "CASE_STUDIES.md")
    assert "Current accepted count: 0" in case_studies
