"""Keep development-only evaluation material out of runtime skill trees."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "skills"
EVAL_CASES = ROOT / "evals" / "cases"


def test_runtime_skill_directories_exclude_evaluation_material() -> None:
    """Repository installers recursively copy skill directories."""
    leaked = sorted(
        path.relative_to(ROOT).as_posix()
        for path in SKILLS.glob("*/evals")
        if path.exists()
    )

    assert leaked == [], (
        "runtime skill directories must not contain evals; repository installers "
        f"would copy development material: {leaked}"
    )


def test_external_eval_tree_matches_runtime_skill_set() -> None:
    """Every runtime skill has exactly one external canonical case set."""
    skill_names = {
        path.name
        for path in SKILLS.iterdir()
        if path.is_dir() and (path / "SKILL.md").is_file()
    }
    eval_names = {
        path.name
        for path in EVAL_CASES.iterdir()
        if path.is_dir() and (path / "evals.json").is_file()
    }

    assert eval_names == skill_names

    for skill_name in sorted(skill_names):
        eval_path = EVAL_CASES / skill_name / "evals.json"
        payload = json.loads(eval_path.read_text(encoding="utf-8-sig"))
        assert payload["skill"] == skill_name
