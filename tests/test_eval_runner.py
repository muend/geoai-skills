from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.eval_runner import EvalRunnerError, ingest_responses, load_suite, prepare_run, score_run


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def prepared_run(tmp_path: Path) -> tuple[Path, dict]:
    run_dir = prepare_run(
        runtime="test-runtime",
        model="test-model-v1",
        condition="skills-enabled",
        runs_dir=tmp_path / "runs",
    )
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    return run_dir, manifest


def perfect_responses(manifest: dict) -> list[dict]:
    rows = []
    for case in manifest["cases"]:
        activated = (
            case["expected_route"] or [case["skill"]]
            if case["should_trigger"]
            else case["expected_route"]
        )
        rows.append(
            {
                "schema_version": 1,
                "case_id": case["case_id"],
                "runtime": manifest["runtime"],
                "model": manifest["model"],
                "condition": manifest["condition"],
                "response": "A deterministic test response.",
                "activated_skills": activated,
                "latency_ms": 10,
                "usage": {"input_tokens": 20, "output_tokens": 30},
            }
        )
    return rows


def perfect_judgments(manifest: dict) -> dict:
    return {
        "schema_version": 1,
        "suite_sha256": manifest["suite_sha256"],
        "judge": {"kind": "rule", "name": "test-perfect-judge", "version": "1"},
        "judgments": [
            {
                "case_id": case["case_id"],
                "expected_behavior": [
                    {"criterion": criterion, "met": True, "evidence": "test"}
                    for criterion in case["expected_behavior"]
                ],
                "forbidden_behavior": [
                    {"criterion": criterion, "observed": False, "evidence": "test"}
                    for criterion in case["forbidden_behavior"]
                ],
                "critical_failure": False,
            }
            for case in manifest["cases"]
            if case.get("behavior_class", "advisory") != "routing-only"
        ],
    }


def test_prepare_is_stable_and_requests_are_blind(tmp_path: Path) -> None:
    run_dir, manifest = prepared_run(tmp_path)
    repeated = prepare_run(
        runtime="test-runtime",
        model="test-model-v1",
        condition="skills-enabled",
        runs_dir=tmp_path / "runs",
    )

    assert repeated == run_dir
    assert len(manifest["cases"]) == 120
    requests = [
        json.loads(line)
        for line in (run_dir / "requests.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert len(requests) == len(manifest["cases"])
    assert all(set(request) == {"schema_version", "case_id", "prompt"} for request in requests)
    assert [request["case_id"] for request in requests] == [
        case["case_id"] for case in manifest["cases"]
    ]


def test_prepare_routing_scope_needs_no_behavior_judgments(tmp_path: Path) -> None:
    run_dir = prepare_run(
        runtime="test-runtime",
        model="test-model-v1",
        condition="skills-enabled",
        evaluation_scope="routing",
        runs_dir=tmp_path / "runs",
    )
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    responses = perfect_responses(manifest)
    response_path = tmp_path / "routing-responses.jsonl"
    write_jsonl(response_path, responses)
    ingest_responses(run_dir=run_dir, input_path=response_path)
    judgments = {
        "schema_version": 1,
        "suite_sha256": manifest["suite_sha256"],
        "judge": {"kind": "rule", "name": "no-behavior-judge", "version": "1"},
        "judgments": [],
    }
    judgment_path = tmp_path / "routing-judgments.json"
    judgment_path.write_text(json.dumps(judgments), encoding="utf-8")

    metrics_path = score_run(run_dir=run_dir, judgments_path=judgment_path)
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))

    assert manifest["evaluation_scope"] == "routing"
    assert "--routing--" in run_dir.name
    assert metrics["behavior"]["judged_cases"] == 0
    assert metrics["behavior"]["pass_rate"] is None


def test_score_routing_only_overrides_combined_run(tmp_path: Path) -> None:
    run_dir, manifest = prepared_run(tmp_path)
    response_path = tmp_path / "combined-responses.jsonl"
    write_jsonl(response_path, perfect_responses(manifest))
    ingest_responses(run_dir=run_dir, input_path=response_path)
    judgments = {
        "schema_version": 1,
        "suite_sha256": manifest["suite_sha256"],
        "judge": {"kind": "rule", "name": "no-behavior-judge", "version": "1"},
        "judgments": [],
    }
    judgment_path = tmp_path / "routing-only-judgments.json"
    judgment_path.write_text(json.dumps(judgments), encoding="utf-8")

    metrics_path = score_run(
        run_dir=run_dir,
        judgments_path=judgment_path,
        routing_only=True,
    )
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))

    assert manifest["evaluation_scope"] == "all"
    assert metrics["routing"]["recall"] == 1.0
    assert metrics["routing"]["route_accuracy"] == 1.0
    assert metrics["behavior"]["judged_cases"] == 0
    assert metrics["behavior"]["pass_rate"] is None


def test_prepare_behavior_scope_fails_closed_without_classified_cases(tmp_path: Path) -> None:
    skills_dir = tmp_path / "skills"
    skill = skills_dir / "sample-skill"
    eval_dir = skill / "evals"
    eval_dir.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\nname: sample-skill\ndescription: Test.\n---\n",
        encoding="utf-8",
    )
    (eval_dir / "evals.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "skill": "sample-skill",
                "evals": [
                    {
                        "id": f"route-{index}",
                        "prompt": f"Route sample request number {index} to the sample skill.",
                        "case_types": ["positive"],
                        "expected_behavior": ["Routes the request to the declared sample skill"],
                    }
                    for index in range(3)
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(EvalRunnerError, match="no explicitly behavior-evaluable cases"):
        prepare_run(
            runtime="test-runtime",
            model="test-model-v1",
            condition="skills-enabled",
            evaluation_scope="behavior",
            runs_dir=tmp_path / "runs",
            skills_dir=skills_dir,
        )


def test_ingest_requires_exact_coverage_and_caches_each_case(tmp_path: Path) -> None:
    run_dir, manifest = prepared_run(tmp_path)
    responses = perfect_responses(manifest)
    incomplete_path = tmp_path / "incomplete.jsonl"
    write_jsonl(incomplete_path, responses[:-1])

    with pytest.raises(EvalRunnerError, match="coverage mismatch"):
        ingest_responses(run_dir=run_dir, input_path=incomplete_path)

    mismatched_path = tmp_path / "mismatched.jsonl"
    mismatched = perfect_responses(manifest)
    mismatched[0]["runtime"] = "different-runtime"
    write_jsonl(mismatched_path, mismatched)
    with pytest.raises(EvalRunnerError, match="does not match manifest"):
        ingest_responses(run_dir=run_dir, input_path=mismatched_path)

    response_path = tmp_path / "responses.jsonl"
    write_jsonl(response_path, responses)
    raw_path = ingest_responses(run_dir=run_dir, input_path=response_path)
    repeated = ingest_responses(run_dir=run_dir, input_path=response_path)

    assert repeated == raw_path
    assert len(raw_path.read_text(encoding="utf-8").splitlines()) == len(manifest["cases"])
    assert len(list((run_dir / "cache").glob("*.json"))) == len(manifest["cases"])


def test_score_emits_perfect_machine_readable_metrics(tmp_path: Path) -> None:
    run_dir, manifest = prepared_run(tmp_path)
    response_path = tmp_path / "responses.jsonl"
    write_jsonl(response_path, perfect_responses(manifest))
    ingest_responses(run_dir=run_dir, input_path=response_path)
    judgment_path = tmp_path / "judgments.json"
    judgment_path.write_text(json.dumps(perfect_judgments(manifest)), encoding="utf-8")

    metrics_path = score_run(run_dir=run_dir, judgments_path=judgment_path)
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))

    negative_cases = sum(not case["should_trigger"] for case in manifest["cases"])
    positive_cases = len(manifest["cases"]) - negative_cases
    case_count = len(manifest["cases"])
    behavior_count = sum(
        case.get("behavior_class", "advisory") != "routing-only"
        for case in manifest["cases"]
    )
    assert metrics["coverage"] == {
        "cases": case_count,
        "responses": case_count,
        "judgments": behavior_count,
    }
    assert metrics["routing"]["tp"] == positive_cases
    assert metrics["routing"]["tn"] == negative_cases
    assert metrics["routing"]["fp"] == 0
    assert metrics["routing"]["fn"] == 0
    assert metrics["routing"]["precision"] == 1.0
    assert metrics["routing"]["recall"] == 1.0
    assert metrics["routing"]["route_accuracy"] == 1.0
    assert metrics["behavior"]["judged_cases"] == behavior_count
    assert metrics["behavior"]["pass_rate"] == 1.0
    assert metrics["usage"] == {
        "input_tokens": case_count * 20,
        "output_tokens": case_count * 30,
        "latency_ms": case_count * 10,
        "cost_usd": 0.0,
    }
    assert len((run_dir / "results" / "cases.jsonl").read_text().splitlines()) == case_count


def test_score_rejects_judgment_criterion_drift(tmp_path: Path) -> None:
    run_dir, manifest = prepared_run(tmp_path)
    manifest["cases"][0]["behavior_class"] = "advisory"
    (run_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    response_path = tmp_path / "responses.jsonl"
    write_jsonl(response_path, perfect_responses(manifest))
    ingest_responses(run_dir=run_dir, input_path=response_path)
    judgments = perfect_judgments(manifest)
    judgments["judgments"][0]["expected_behavior"][0]["criterion"] = (
        "This replacement criterion is long enough but not the manifest criterion."
    )
    judgment_path = tmp_path / "drifted-judgments.json"
    judgment_path.write_text(json.dumps(judgments), encoding="utf-8")

    with pytest.raises(EvalRunnerError, match="criteria drift"):
        score_run(run_dir=run_dir, judgments_path=judgment_path)


def test_load_suite_hashes_declared_fixtures_and_behavior_contract(tmp_path: Path) -> None:
    skills_dir = tmp_path / "skills"
    skill = skills_dir / "sample-skill"
    eval_dir = skill / "evals"
    fixture = eval_dir / "fixtures" / "input.csv"
    fixture.parent.mkdir(parents=True)
    fixture.write_text("x,y\n1,2\n", encoding="utf-8")
    (skill / "SKILL.md").write_text("---\nname: sample-skill\ndescription: Test.\n---\n", encoding="utf-8")
    (eval_dir / "evals.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "skill": "sample-skill",
                "evals": [
                    {
                        "id": "fixture-case",
                        "prompt": "Read inputs/input.csv and explain the result.",
                        "case_types": ["positive", "artifact-correctness"],
                        "expected_behavior": ["Uses the staged input without asking for a missing file"],
                        "behavior_class": "fixture-backed",
                        "tool_profile": "read-only",
                        "fixtures": [
                            {"source": "fixtures/input.csv", "workspace_path": "inputs/input.csv"}
                        ],
                    },
                    {
                        "id": "route-a",
                        "prompt": "Route this sample request to the sample skill.",
                        "case_types": ["positive"],
                        "expected_behavior": ["Routes the request to the declared sample skill"],
                    },
                    {
                        "id": "route-b",
                        "prompt": "Handle another sample request with the sample skill.",
                        "case_types": ["positive"],
                        "expected_behavior": ["Routes the second request to the sample skill"],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    cases, suite_hash, _ = load_suite(skills_dir=skills_dir)

    declared = cases[0]
    assert declared["behavior_class"] == "fixture-backed"
    assert declared["fixtures"][0]["workspace_path"] == "inputs/input.csv"
    assert declared["fixtures"][0]["size_bytes"] == len(fixture.read_bytes())
    assert len(declared["fixtures"][0]["sha256"]) == 64
    assert len(suite_hash) == 64
    assert cases[1]["behavior_class"] == "routing-only"
