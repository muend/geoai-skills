"""Task planning, schema validation and evidence-bound delivery decisions."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .core import KIT, outcome, read_json, report
from .integrity import verify_inventory


def validate_record(value: dict[str, Any]) -> None:
    from jsonschema import Draft202012Validator

    schema = read_json(KIT / "schemas" / "records.schema.json")
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(value), key=lambda e: str(e.path))
    if errors:
        raise ValueError("; ".join(f"{list(e.path)}: {e.message}" for e in errors))


def plan(task: dict[str, Any]) -> dict[str, Any]:
    validate_record(task)
    if task["kind"] != "task":
        raise ValueError("plan requires a task record")
    bindings = read_json(KIT / "bindings.json")
    unknown = set(task["skills"]) - set(bindings)
    if unknown or not task["skills"]:
        raise ValueError(f"missing or unsupported skills: {sorted(unknown)}")
    roles = ["coordinator", "specialist"]
    checks = set(task["required_checks"])
    if task["uses_data"] or task["physical_claim"]:
        roles.append("reality-reviewer")
    if task["task_type"] != "explanation":
        roles.append("method-reviewer")
    if task["user_facing_visual"] or task["task_type"] == "map":
        roles.append("presentation-reviewer")
    if task["task_type"] != "explanation" or task["uses_data"] or task["physical_claim"]:
        for name in task["skills"]:
            checks.update(bindings[name]["checks"])
    owners = read_json(KIT / "controls.json")
    assignments = {c: owners.get(c, "method-reviewer") for c in sorted(checks)}
    for role in dict.fromkeys(assignments.values()):
        if role not in roles:
            roles.append(role)
    return {"schema_version": 1, "task_id": task["task_id"], "roles": roles,
            "required_checks": sorted(checks), "max_repair_rounds": 2,
            "check_owners": assignments, "core_mutation": False, "learning": "local-record-only"}


def delivery(task: dict[str, Any], artifacts: dict[str, Any], reviews: list[dict[str, Any]],
             root: Path, repairs: int = 0) -> dict[str, Any]:
    routing = plan(task)
    if repairs not in range(3):
        raise ValueError("repair count must be between zero and two")
    validate_record(artifacts)
    if artifacts["kind"] != "artifacts" or artifacts["task_id"] != task["task_id"]:
        raise ValueError("artifact/task mismatch")
    checks = verify_inventory(root, artifacts["files"])["results"]
    reviewed = set()
    checked = set()
    hashes = {f["path"]: f["sha256"] for f in artifacts["files"]}
    identities = set()
    for review in reviews:
        validate_record(review)
        if review["kind"] != "review" or review["task_id"] != task["task_id"]:
            raise ValueError("review/task mismatch")
        role = review["role"]
        if role not in routing["roles"] or not role.endswith("reviewer"):
            raise ValueError("unexpected review role")
        if review["reviewer_id"] == artifacts["producer_id"]:
            checks.append(outcome("independent-review", "fail", "Producer reviewed own output"))
        if role in reviewed or review["reviewer_id"] in identities:
            checks.append(outcome("independent-review", "fail", "Duplicate role or identity"))
        identities.add(review["reviewer_id"])
        if review["artifact_hashes"] != hashes:
            checks.append(outcome("review-freshness", "fail", "Review refers to different bytes"))
        if review["status"] != "completed":
            checks.append(outcome("review-completion", "abstain", review["status"]))
            continue
        reviewed.add(role)
        if review["evidence_files"]:
            checks.extend(verify_inventory(root, review["evidence_files"])["results"])
        evidence_names = set(hashes) | {f["path"] for f in review["evidence_files"]}
        for result in review["checks"]:
            # Every cited path must resolve to an identity-checked local evidence file.
            state = result["outcome"]
            if state == "pass" and (not result["evidence"] or
                                    not set(result["evidence"]) <= evidence_names):
                state = "abstain"
            owner = routing["check_owners"].get(result["check"])
            if owner == role:
                checked.add(result["check"])
            checks.append(outcome(result["check"], state, result["reason"],
                                  evidence=result["evidence"], role=role))
    for role in set(routing["roles"]) - reviewed:
        if role.endswith("reviewer"):
            checks.append(outcome("required-review", "abstain", f"Missing {role}"))
    for check in set(routing["required_checks"]) - checked:
        checks.append(outcome(check, "abstain", "Required check was not reported"))
    for name in set(task["outputs"]) - set(hashes):
        checks.append(outcome("required-output", "abstain", name))
    result = report(checks)
    result["decision"] = "deliver" if result["exit_code"] == 0 else (
        "repair" if repairs < 2 else "deliver-with-unresolved-findings")
    result["verified_claim_allowed"] = result["exit_code"] == 0
    result["scope"] = "Recorded checks and byte identities; not a certificate of field truth"
    return result
