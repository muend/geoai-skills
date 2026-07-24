"""Regression tests for the geoai-orchestrator routing gate.

Review of the `pipeline-plan-audit` case found a real product defect rather
than a rubric artefact: the orchestrator named a specialist for one of four
findings and closed with "say the word and I'll route each fix to the relevant
specialist skill". The routing gate added to SKILL.md must keep invocation
mandatory, must forbid conditional deferral, and must not be undercut by the
pipeline template telling the model to publish a plan and wait.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "geoai-orchestrator" / "SKILL.md"
EVALS = ROOT / "skills" / "geoai-orchestrator" / "evals" / "evals.json"


def _skill_text() -> str:
    return SKILL.read_text(encoding="utf-8")


def _normalized_skill_text() -> str:
    return " ".join(_skill_text().split())


def _case(case_id: str) -> dict:
    suite = json.loads(EVALS.read_text(encoding="utf-8"))
    return next(case for case in suite["evals"] if case["id"] == case_id)


def test_routing_gate_precedes_the_pipeline_template() -> None:
    """The gate must outrank the template, and must be stated before it."""
    text = _skill_text()

    gate_index = text.index("## Routing gate")
    template_index = text.index("## Pipeline design protocol")
    assert gate_index < template_index

    normalized = _normalized_skill_text()
    assert "overrides every other section of this document" in normalized
    assert "including the pipeline template" in normalized


def test_gate_requires_invocation_rather_than_naming() -> None:
    normalized = _normalized_skill_text()

    assert "routes by **invoking**, never by naming" in normalized
    assert "invoked with the `Skill` tool in the same response" in normalized
    assert (
        "Naming a skill in a table, plan, or prose sentence is not a handoff"
        in normalized
    )


def test_gate_forbids_conditional_deferral_of_routing() -> None:
    """The exact observed failure string must be named as a prohibition."""
    normalized = _normalized_skill_text()

    assert "Never make routing conditional on permission" in normalized
    for phrase in (
        '"say the word and I\'ll route"',
        '"I can hand this off if you want"',
    ):
        assert phrase in normalized
    assert "If you have identified the specialist, invoke it now." in normalized


def test_gate_requires_every_finding_to_be_routed() -> None:
    normalized = _normalized_skill_text()

    assert "Route every correction, not the first one" in normalized
    assert "the count of routed items must equal the count of items found" in normalized


def test_clarification_does_not_replace_routing() -> None:
    normalized = _normalized_skill_text()

    assert "Clarification is not a substitute for routing" in normalized
    assert "Ask the scope question and route in the same response" in normalized


def test_audit_requests_are_treated_as_deliver_requests() -> None:
    normalized = _normalized_skill_text()

    assert "Audit requests are `deliver` requests" in normalized
    assert "in one response" in normalized
    assert "Do not return findings and hold the corrections back" in normalized


def test_pipeline_template_is_not_a_proposal_awaiting_approval() -> None:
    """The old template said 'get confirmation'; that contradiction is gone."""
    normalized = _normalized_skill_text()

    assert "get confirmation only when scope is ambiguous" not in normalized
    assert (
        "The plan is a routing manifest, not a proposal awaiting approval."
        in normalized
    )
    assert "Do not wait for confirmation before routing" in normalized


def test_execution_contract_carries_the_gate() -> None:
    normalized = _normalized_skill_text()

    assert (
        "route each stage to the narrowest skill by invoking it with the `Skill` tool"
        in normalized
    )
    assert (
        "confirm that every specialist named in the response was actually invoked"
        in normalized
    )
    assert "Never substitute an offer to route for an invocation" in normalized


def test_pipeline_plan_audit_forbids_partial_and_deferred_routing() -> None:
    forbidden = _case("pipeline-plan-audit")["forbidden_behavior"]

    assert any("defer routed handoffs to a later turn" in item for item in forbidden)
    assert any("name a specialist without invoking it" in item for item in forbidden)
    assert any("only a subset of the findings" in item for item in forbidden)


def test_multi_stage_and_ambiguous_cases_forbid_plan_only_responses() -> None:
    multi_stage = _case("multi-stage-pipeline")["forbidden_behavior"]
    ambiguous = _case("ambiguous-project-scope")["forbidden_behavior"]

    assert any("proposal awaiting approval" in item for item in multi_stage)
    assert any("withhold the staged plan" in item for item in ambiguous)


def test_negative_collision_cases_keep_their_single_specialist_boundary() -> None:
    """Hardening the gate must not turn the orchestrator into a universal wrapper."""
    for case_id in (
        "single-stage-routing",
        "degree-buffer-catch",
        "single-kriging-surface",
        "single-devops-task",
    ):
        case = _case(case_id)
        assert case["should_trigger"] is False
        assert "negative" in case["case_types"]

    normalized = _normalized_skill_text()
    assert "not as a mandatory wrapper around every spatial task" in normalized
    assert "If you cannot satisfy the gate, do not activate this skill" in normalized
