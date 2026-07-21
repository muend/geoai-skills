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


def test_measurement_guidance_rejects_web_mercator() -> None:
    skill_text = SKILL.read_text(encoding="utf-8")
    suite = json.loads(EVALS.read_text(encoding="utf-8"))
    area_case = next(case for case in suite["evals"] if case["id"] == "area-4326-catch")

    assert (
        "Never use EPSG:3857/Web Mercator for area or length measurement" in skill_text
    )
    assert "geometry(MultiPolygon, 3857)" not in skill_text
    assert any(
        "Must not present Web Mercator" in criterion
        for criterion in area_case["forbidden_behavior"]
    )


def test_backend_choice_requires_evidence_and_correctness_benchmark() -> None:
    skill_text = SKILL.read_text(encoding="utf-8")
    normalized_skill_text = " ".join(skill_text.split())
    suite = json.loads(EVALS.read_text(encoding="utf-8"))
    backend_case = next(
        case for case in suite["evals"] if case["id"] == "backend-choice-unclear"
    )

    for requirement in (
        "current and forecast data volume",
        "latency/SLA",
        "operational ownership",
        "join cardinality",
    ):
        assert requirement in normalized_skill_text
    assert any(
        "unconditional backend recommendation" in criterion
        for criterion in backend_case["forbidden_behavior"]
    )
