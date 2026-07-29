from __future__ import annotations

import json
from pathlib import Path

from tools.adapters.judge_contract import (
    PROMPT_VERSION,
    criterion_plan,
    judgment_prompt,
    judgment_schema,
    load_clause_specs,
    restore_judgment,
)


def test_prompt_requires_exact_constraint_matching() -> None:
    case = {
        "case_id": "sample/exact-units",
        "prompt": "Create the requested rate map.",
        "critical": True,
        "behavior_class": "artifact-producing",
        "interaction_mode": "deliver",
        "expected_behavior": ["Maps cases/population*100000 with per-100,000 units"],
        "forbidden_behavior": [],
        "fixtures": [],
        "expected_artifacts": [],
    }
    response = {
        "response": "Mapped cases/population*1000 with per-1,000 units.",
        "artifacts": [],
    }

    payload = json.loads(judgment_prompt(case, response))

    assert PROMPT_VERSION == "geoai-behavior-judge-v6"
    assert "a different but reasonable value does not satisfy" in payload["instructions"]
    assert "A rate per 1,000 does not meet a per-100,000 clause" in payload[
        "instructions"
    ]
    assert "Conflicting evidence requires met=false" in payload["instructions"]


def test_prompt_forbids_inference_beyond_bounded_artifact_preview() -> None:
    case = {
        "case_id": "sample/artifact-preview",
        "prompt": "Create an artifact.",
        "critical": False,
        "behavior_class": "artifact-producing",
        "interaction_mode": "deliver",
        "expected_behavior": ["Artifact records its units"],
        "forbidden_behavior": [],
        "fixtures": [],
        "expected_artifacts": [],
    }
    response = {
        "response": "Created the artifact.",
        "artifacts": [{"path": "outputs/map.html", "text_preview": "No units here."}],
    }

    payload = json.loads(judgment_prompt(case, response))

    assert "Treat bounded artifact previews as the complete available" in payload[
        "instructions"
    ]
    assert "do not infer unseen content" in payload["instructions"]


def test_prompt_does_not_broaden_forbidden_behavior() -> None:
    case = {
        "case_id": "sample/wrong-versus-omitted-units",
        "prompt": "Create a rate legend.",
        "critical": False,
        "behavior_class": "advisory",
        "interaction_mode": "deliver",
        "expected_behavior": ["Uses cases per 100,000"],
        "forbidden_behavior": ["Omits the rate units from the legend"],
        "fixtures": [],
        "expected_artifacts": [],
    }
    response = {
        "response": "The legend says cases per 1,000.",
        "artifacts": [],
    }

    payload = json.loads(judgment_prompt(case, response))

    assert "set observed=true only when the response directly satisfies" in payload[
        "instructions"
    ]
    assert "wrong units are not omitted units" in payload["instructions"].lower()


def test_atomic_registry_covers_calibration_failures() -> None:
    specs = load_clause_specs()

    classification = (
        "Uses and records a justified fixed classification, a colorblind-safe ramp, "
        "and neutral gray for the county with missing population"
    )
    exception_handling = (
        "Uses psycopg SQL composition for the allowlisted table identifier, value "
        "parameters for WKT/SRID, explicit MULTIPOLYGON/3857 validation or "
        "transformation, and specific exceptions with rollback"
    )

    assert specs[classification]["clauses"][0] == (
        "Uses and records a justified fixed classification"
    )
    assert "Uses specific exceptions" in specs[exception_handling]["clauses"]


def test_calibration_false_positives_cannot_pass_atomic_parent() -> None:
    criteria_and_decisions = [
        (
            "Uses and records a justified fixed classification, a colorblind-safe "
            "ramp, and neutral gray for the county with missing population",
            [False, True, True],
        ),
        (
            "Uses psycopg SQL composition for the allowlisted table identifier, "
            "value parameters for WKT/SRID, explicit MULTIPOLYGON/3857 validation "
            "or transformation, and specific exceptions with rollback",
            [True, True, True, True, False, True],
        ),
    ]

    for criterion, decisions in criteria_and_decisions:
        case = {
            "case_id": "sample/regression",
            "prompt": "Review the complete response.",
            "critical": False,
            "expected_behavior": [criterion],
            "forbidden_behavior": [],
        }
        parsed = {
            "expected_clauses": [
                {"met": decision, "evidence": f"decision={decision}"}
                for decision in decisions
            ],
            "forbidden_clauses": [],
            "critical_failure": False,
            "notes": "",
        }

        judgment = restore_judgment(case, parsed)

        assert judgment["expected_behavior"][0]["met"] is False


def test_atomic_registry_criteria_match_live_rubric_text() -> None:
    root = Path(__file__).resolve().parents[1]
    live_criteria = set()
    for path in (root / "evals" / "cases").glob("*/evals.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for case in payload["evals"]:
            live_criteria.update(case["expected_behavior"])
            live_criteria.update(case.get("forbidden_behavior", []))

    assert set(load_clause_specs()) <= live_criteria


def test_schema_flattens_one_check_per_material_clause() -> None:
    case = {
        "case_id": "sample/atomic",
        "prompt": "Review the implementation.",
        "critical": False,
        "expected_behavior": ["Does A and B"],
        "forbidden_behavior": ["Does C or D"],
    }
    specs = {
        "Does A and B": {"operator": "all", "clauses": ["Does A", "Does B"]},
        "Does C or D": {"operator": "any", "clauses": ["Does C", "Does D"]},
    }

    schema = judgment_schema(case, clause_specs=specs)

    assert schema["properties"]["expected_clauses"]["minItems"] == 2
    assert schema["properties"]["expected_clauses"]["maxItems"] == 2
    assert schema["properties"]["forbidden_clauses"]["minItems"] == 2
    assert schema["properties"]["forbidden_clauses"]["maxItems"] == 2


def test_restore_aggregates_parent_decisions_deterministically() -> None:
    case = {
        "case_id": "sample/atomic",
        "prompt": "Review the implementation.",
        "critical": False,
        "expected_behavior": ["Does A and B"],
        "forbidden_behavior": ["Does C or D"],
    }
    specs = {
        "Does A and B": {"operator": "all", "clauses": ["Does A", "Does B"]},
        "Does C or D": {"operator": "any", "clauses": ["Does C", "Does D"]},
    }
    parsed = {
        "expected_clauses": [
            {"met": True, "evidence": "A is present."},
            {"met": False, "evidence": "B is absent."},
        ],
        "forbidden_clauses": [
            {"observed": False, "evidence": "C is absent."},
            {"observed": True, "evidence": "D is present."},
        ],
        "critical_failure": False,
        "notes": "",
    }

    judgment = restore_judgment(case, parsed, clause_specs=specs)

    assert judgment["expected_behavior"][0]["met"] is False
    assert judgment["forbidden_behavior"][0]["observed"] is True
    assert "[clause 2: Does B] B is absent." in judgment["expected_behavior"][0][
        "evidence"
    ]


def test_unregistered_criterion_remains_one_atomic_clause() -> None:
    plan = criterion_plan(["A complete unregistered criterion"], clause_specs={})

    assert plan == [
        {
            "criterion": "A complete unregistered criterion",
            "operator": "all",
            "clauses": ["A complete unregistered criterion"],
        }
    ]
