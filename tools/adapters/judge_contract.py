"""Shared criterion-preserving contract for model-assisted behavior judges."""

from __future__ import annotations

from typing import Any

from jsonschema import Draft202012Validator

from tools.eval_runner import pretty_json, validate_instance

PROMPT_VERSION = "geoai-behavior-judge-v3"

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


def judgment_schema(case: dict[str, Any]) -> dict[str, Any]:
    """Return a strict positional schema without allowing criterion rewrites."""
    expected_count = len(case["expected_behavior"])
    forbidden_count = len(case["forbidden_behavior"])
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["expected", "forbidden", "critical_failure", "notes"],
        "properties": {
            "expected": {
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
            "forbidden": {
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


def judgment_prompt(case: dict[str, Any], response: dict[str, Any]) -> str:
    """Build the post-execution rubric payload seen by a model judge."""
    interaction_mode = case.get("interaction_mode", "deliver")
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
        "expected_behavior_in_order": case["expected_behavior"],
        "forbidden_behavior_in_order": case["forbidden_behavior"],
        "instructions": (
            "Return one expected entry per expected criterion and one forbidden entry per "
            "forbidden criterion, preserving order. Mark a criterion true only when the supplied "
            "assistant response contains direct evidence for every material clause; treat criteria "
            "with multiple requirements as conjunctive. Merely naming a missing check, promising to "
            "inspect it later, or satisfying one clause is not enough. Do not reward inferred or "
            "unstated behavior. critical_failure is true only for a severe spatial safety or validity "
            "failure, when a response error prevents a critical case from being answered, or when a "
            "critical case's core safety or validity risk is completely omitted and the user is left "
            "able to proceed under the invalid premise."
        ),
    }
    return pretty_json(payload)


def restore_judgment(case: dict[str, Any], parsed: Any) -> dict[str, Any]:
    """Validate positional output and restore the manifest's exact criterion text."""
    validate_instance(
        Draft202012Validator(judgment_schema(case)),
        parsed,
        label=f"judge[{case['case_id']}]",
    )
    return {
        "case_id": case["case_id"],
        "expected_behavior": [
            {"criterion": criterion, "met": check["met"], "evidence": check["evidence"]}
            for criterion, check in zip(
                case["expected_behavior"], parsed["expected"], strict=True
            )
        ],
        "forbidden_behavior": [
            {
                "criterion": criterion,
                "observed": check["observed"],
                "evidence": check["evidence"],
            }
            for criterion, check in zip(
                case["forbidden_behavior"], parsed["forbidden"], strict=True
            )
        ],
        "critical_failure": parsed["critical_failure"],
        "notes": parsed["notes"],
    }
