"""Shared criterion-preserving contract for model-assisted behavior judges."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from tools.eval_runner import EvalRunnerError, load_json, pretty_json, validate_instance

PROMPT_VERSION = "geoai-behavior-judge-v6"
CLAUSE_SPEC_PATH = Path(__file__).resolve().parents[2] / "evals" / "judge-clauses.json"

INTERACTION_POLICIES = {
    "clarify": (
        "Material facts are missing, so a complete response may stop after asking the necessary "
        "questions or refusing unsafe action. Do not require downstream execution unless an exact "
        "criterion explicitly requires a bounded provisional step."
    ),
    "deliver": (
        "The response must provide the requested analysis, plan, code, or decision now. A promise "
        "to do substantive work later does not satisfy a delivery criterion."
    ),
    "clarify_then_provisional": (
        "The response must both ask for the material missing facts and provide a useful bounded "
        "provisional plan or conditional answer with assumptions labeled. Deferring all substantive "
        "work until a later response is insufficient."
    ),
}


CLAUSE_SPEC_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["schema_version", "criteria"],
    "properties": {
        "schema_version": {"const": 1},
        "criteria": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["criterion", "operator", "clauses"],
                "properties": {
                    "criterion": {"type": "string", "minLength": 10},
                    "operator": {"enum": ["all", "any"]},
                    "clauses": {
                        "type": "array",
                        "minItems": 1,
                        "uniqueItems": True,
                        "items": {"type": "string", "minLength": 3},
                    },
                },
            },
        },
    },
}


@lru_cache(maxsize=1)
def load_clause_specs() -> dict[str, dict[str, Any]]:
    """Load and index the exact-text atomic criterion registry."""
    payload = load_json(CLAUSE_SPEC_PATH)
    validate_instance(
        Draft202012Validator(CLAUSE_SPEC_SCHEMA),
        payload,
        label="judge clause specs",
    )
    indexed: dict[str, dict[str, Any]] = {}
    for spec in payload["criteria"]:
        criterion = spec["criterion"]
        if criterion in indexed:
            raise EvalRunnerError(f"Duplicate judge clause criterion: {criterion}")
        indexed[criterion] = {
            "operator": spec["operator"],
            "clauses": list(spec["clauses"]),
        }
    return indexed


def criterion_plan(
    criteria: list[str],
    *,
    clause_specs: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Return immutable parent criteria with explicit atomic clause plans."""
    registry = load_clause_specs() if clause_specs is None else clause_specs
    return [
        {
            "criterion": criterion,
            "operator": registry.get(criterion, {}).get("operator", "all"),
            "clauses": list(registry.get(criterion, {}).get("clauses", [criterion])),
        }
        for criterion in criteria
    ]


def _clause_count(plan: list[dict[str, Any]]) -> int:
    return sum(len(item["clauses"]) for item in plan)


def judgment_schema(
    case: dict[str, Any],
    *,
    clause_specs: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return a strict flattened atomic-clause schema."""
    expected_plan = criterion_plan(
        case["expected_behavior"], clause_specs=clause_specs
    )
    forbidden_plan = criterion_plan(
        case["forbidden_behavior"], clause_specs=clause_specs
    )
    expected_count = _clause_count(expected_plan)
    forbidden_count = _clause_count(forbidden_plan)
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "expected_clauses",
            "forbidden_clauses",
            "critical_failure",
            "notes",
        ],
        "properties": {
            "expected_clauses": {
                "type": "array",
                "minItems": expected_count,
                "maxItems": expected_count,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["met", "evidence"],
                    "properties": {
                        "met": {"type": "boolean"},
                        "evidence": {"type": "string"},
                    },
                },
            },
            "forbidden_clauses": {
                "type": "array",
                "minItems": forbidden_count,
                "maxItems": forbidden_count,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["observed", "evidence"],
                    "properties": {
                        "observed": {"type": "boolean"},
                        "evidence": {"type": "string"},
                    },
                },
            },
            "critical_failure": {"type": "boolean"},
            "notes": {"type": "string"},
        },
    }


def judgment_prompt(
    case: dict[str, Any],
    response: dict[str, Any],
    *,
    clause_specs: dict[str, dict[str, Any]] | None = None,
) -> str:
    """Build the post-execution rubric payload seen by a model judge."""
    interaction_mode = case.get("interaction_mode", "deliver")
    expected_plan = criterion_plan(
        case["expected_behavior"], clause_specs=clause_specs
    )
    forbidden_plan = criterion_plan(
        case["forbidden_behavior"], clause_specs=clause_specs
    )
    payload = {
        "prompt_version": PROMPT_VERSION,
        "user_prompt": case["prompt"],
        "assistant_response": response["response"],
        "response_error": response.get("error"),
        "behavior_class": case.get("behavior_class", "advisory"),
        "interaction_mode": interaction_mode,
        "interaction_policy": INTERACTION_POLICIES[interaction_mode],
        "declared_fixtures": case.get("fixtures", []),
        "expected_artifacts": case.get("expected_artifacts", []),
        "observed_artifacts": response.get("artifacts", []),
        "case_is_critical": case["critical"],
        "expected_clause_plan_in_order": expected_plan,
        "forbidden_clause_plan_in_order": forbidden_plan,
        "instructions": (
            "Flatten expected_clause_plan_in_order in criterion order and clause order. Return "
            "exactly one expected_clauses entry for each flattened clause. Do the same for "
            "forbidden_clause_plan_in_order and forbidden_clauses. Judge each atomic clause "
            "independently; do not return or infer a parent-criterion decision. The adapter computes "
            "each parent deterministically from its declared all/any operator. Mark an expected "
            "clause met only when the supplied response contains direct evidence for that entire "
            "clause. Merely naming a missing check, promising to inspect it later, or satisfying a "
            "neighboring clause is not enough. Do not reward inferred or unstated behavior. Exact "
            "quantities, units, multipliers, thresholds, CRS identifiers, file paths, named methods, "
            "and ordering constraints are material: a different but reasonable value does not "
            "satisfy the clause. Conflicting evidence requires met=false; never excuse it using "
            "domain judgment, dataset scale, or the response's rationale. A rate per 1,000 does not "
            "meet a per-100,000 clause. Evidence must quote or precisely identify the supplied "
            "response or artifact, including a conflict when a clause is not met. Treat bounded "
            "artifact previews as the complete available artifact evidence and do not infer unseen "
            "content. For forbidden clauses, set observed=true only when the response directly "
            "satisfies that clause as written. Do not broaden it by analogy or convert a different "
            "expected-clause failure into a forbidden violation. Wrong units are not omitted units. "
            "critical_failure is true only for a severe spatial safety or validity failure, when a "
            "response error prevents a critical case from being answered, or when a critical case's "
            "core safety or validity risk is completely omitted and the user is left able to proceed "
            "under the invalid premise."
        ),
    }
    return pretty_json(payload)


def _aggregate(value: list[bool], operator: str) -> bool:
    if operator == "all":
        return all(value)
    if operator == "any":
        return any(value)
    raise EvalRunnerError(f"Unknown judge clause operator: {operator}")


def _restore_checks(
    plan: list[dict[str, Any]],
    checks: list[dict[str, Any]],
    *,
    decision_key: str,
    output_key: str,
) -> list[dict[str, Any]]:
    restored = []
    offset = 0
    for parent in plan:
        count = len(parent["clauses"])
        clause_checks = checks[offset : offset + count]
        offset += count
        decisions = [check[decision_key] for check in clause_checks]
        evidence = " | ".join(
            f"[clause {index}: {clause}] {check['evidence']}"
            for index, (clause, check) in enumerate(
                zip(parent["clauses"], clause_checks, strict=True),
                start=1,
            )
        )
        restored.append(
            {
                "criterion": parent["criterion"],
                output_key: _aggregate(decisions, parent["operator"]),
                "evidence": evidence,
            }
        )
    if offset != len(checks):
        raise EvalRunnerError("Judge returned unused atomic clause checks")
    return restored


def restore_judgment(
    case: dict[str, Any],
    parsed: Any,
    *,
    clause_specs: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Validate atomic output and restore deterministic parent decisions."""
    validate_instance(
        Draft202012Validator(judgment_schema(case, clause_specs=clause_specs)),
        parsed,
        label=f"judge[{case['case_id']}]",
    )
    expected_plan = criterion_plan(
        case["expected_behavior"], clause_specs=clause_specs
    )
    forbidden_plan = criterion_plan(
        case["forbidden_behavior"], clause_specs=clause_specs
    )
    return {
        "case_id": case["case_id"],
        "expected_behavior": _restore_checks(
            expected_plan,
            parsed["expected_clauses"],
            decision_key="met",
            output_key="met",
        ),
        "forbidden_behavior": _restore_checks(
            forbidden_plan,
            parsed["forbidden_clauses"],
            decision_key="observed",
            output_key="observed",
        ),
        "critical_failure": parsed["critical_failure"],
        "notes": parsed["notes"],
    }
