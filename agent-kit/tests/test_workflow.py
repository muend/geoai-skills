import copy

import pytest

from geoai_agents.core import KIT, file_hash, read_json
from geoai_agents.workflow import delivery, plan, validate_record


def task(**changes):
    return {"schema_version": 1, "kind": "task", "task_id": "example",
            "objective": "Explain a map", "audience": "non-specialists",
            "task_type": "explanation", "skills": ["cartography-geoviz"],
            "uses_data": False, "physical_claim": False, "user_facing_visual": False,
            "outputs": ["map.svg"], "required_checks": [], **changes}


def setup_review(tmp_path):
    path = tmp_path / "map.svg"
    path.write_text("<svg/>", encoding="utf-8")
    work = task(task_type="map", user_facing_visual=True)
    artifacts = {"schema_version": 1, "kind": "artifacts", "task_id": "example",
                 "producer_id": "producer", "files": [{"path": "map.svg", "size": 6,
                 "sha256": file_hash(path)}], "sources": [], "parameters": {}, "environment": {}}
    review = {"schema_version": 1, "kind": "review", "task_id": "example",
              "reviewer_id": "reviewer", "role": "method-reviewer", "status": "completed",
              "evidence_files": [],
              "artifact_hashes": {"map.svg": file_hash(path)}, "checks": [
                  {"check": c, "outcome": "pass", "reason": "source and rendering checked",
                   "severity": "info", "evidence": ["map.svg"], "remedy": ""}
                  for c in plan(work)["required_checks"]]}
    visual = {**copy.deepcopy(review), "role": "presentation-reviewer", "reviewer_id": "visual"}
    return work, artifacts, [review, visual]


def test_unresolved_or_changed_evidence_cannot_pass(tmp_path):
    work, artifacts, reviews = setup_review(tmp_path)
    reviews[1]["checks"][0]["evidence"] = ["nonexistent-report.json"]
    assert delivery(work, artifacts, reviews, tmp_path)["exit_code"] == 2
    evidence = tmp_path / "log.txt"
    evidence.write_bytes(b"original")
    reviews[1]["checks"][0]["evidence"] = ["log.txt"]
    reviews[1]["evidence_files"] = [{"path": "log.txt", "size": 8,
                                    "sha256": file_hash(evidence)}]
    assert delivery(work, artifacts, reviews, tmp_path)["exit_code"] == 0
    evidence.write_bytes(b"modified")
    assert delivery(work, artifacts, reviews, tmp_path)["exit_code"] == 1


def test_unrelated_check_does_not_satisfy_required_role(tmp_path):
    work, artifacts, reviews = setup_review(tmp_path)
    reviews[1]["checks"] = [{**reviews[1]["checks"][0], "check": "unrelated"}]
    assert delivery(work, artifacts, reviews, tmp_path)["exit_code"] == 2


def test_small_explanation_does_not_spawn_full_team():
    assert plan(task())["roles"] == ["coordinator", "specialist"]


def test_physical_claim_and_visual_delivery_get_relevant_reviewers():
    result = plan(task(task_type="analysis", physical_claim=True, user_facing_visual=True))
    assert set(result["roles"]) == {"coordinator", "specialist", "reality-reviewer",
                                    "method-reviewer", "presentation-reviewer"}
    assert result["max_repair_rounds"] == 2
    assert "skill-maintainer" not in result["roles"]


def test_good_delivery_and_stale_review(tmp_path):
    work, artifacts, reviews = setup_review(tmp_path)
    assert delivery(work, artifacts, reviews, tmp_path)["verified_claim_allowed"]
    (tmp_path / "map.svg").write_text("changed", encoding="utf-8")
    result = delivery(work, artifacts, reviews, tmp_path)
    assert not result["verified_claim_allowed"] and result["exit_code"] == 1


def test_new_hash_requires_new_review(tmp_path):
    work, artifacts, reviews = setup_review(tmp_path)
    (tmp_path / "map.svg").write_text("new output", encoding="utf-8")
    artifacts["files"][0]["sha256"] = file_hash(tmp_path / "map.svg")
    assert delivery(work, artifacts, reviews, tmp_path)["exit_code"] == 1


def test_producer_cannot_approve_own_artifact(tmp_path):
    work, artifacts, reviews = setup_review(tmp_path)
    reviews[0]["reviewer_id"] = "producer"
    assert delivery(work, artifacts, reviews, tmp_path)["exit_code"] == 1


@pytest.mark.parametrize("status", ["quota-exhausted", "interrupted", "error"])
def test_partial_review_is_not_completion(tmp_path, status):
    work, artifacts, reviews = setup_review(tmp_path)
    reviews[0]["status"] = status
    result = delivery(work, artifacts, reviews, tmp_path, repairs=2)
    assert result["exit_code"] == 2
    assert result["decision"] == "deliver-with-unresolved-findings"
    assert not result["verified_claim_allowed"]


def test_missing_review_or_evidence_abstains(tmp_path):
    work, artifacts, reviews = setup_review(tmp_path)
    assert delivery(work, artifacts, [], tmp_path)["exit_code"] == 2
    reviews[0]["checks"][0]["evidence"] = []
    assert delivery(work, artifacts, reviews, tmp_path)["exit_code"] == 2


def test_schema_rejects_unknown_record_fields():
    with pytest.raises(ValueError):
        validate_record(task(core_mutation=True))


@pytest.mark.parametrize("skill", sorted(read_json(KIT / "bindings.json")))
def test_each_skill_routes_required_checks_and_abstains_without_review(tmp_path, skill):
    work, artifacts, _ = setup_review(tmp_path)
    work.update(skills=[skill], uses_data=True)
    routing = plan(work)
    assert set(read_json(KIT / "bindings.json")[skill]["checks"]) <= set(
        routing["required_checks"])
    assert all(owner in routing["roles"] for owner in routing["check_owners"].values())
    assert delivery(work, artifacts, [], tmp_path)["exit_code"] == 2
