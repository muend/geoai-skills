from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "postgis-spatial-sql" / "SKILL.md"
EVALS = ROOT / "skills" / "postgis-spatial-sql" / "evals" / "evals.json"


def test_slow_join_guards_executable_sql_quality() -> None:
    skill_text = SKILL.read_text(encoding="utf-8")
    suite = json.loads(EVALS.read_text(encoding="utf-8"))
    slow_join = next(case for case in suite["evals"] if case["id"] == "slow-join")

    assert "every `sql` fence presented as runnable" in skill_text
    assert "incomplete alias" in skill_text
    assert any(
        "self-contained statement" in criterion
        for criterion in slow_join["expected_behavior"]
    )
    assert any(
        "incomplete aliases" in criterion
        for criterion in slow_join["forbidden_behavior"]
    )
