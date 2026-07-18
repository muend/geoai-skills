from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.eval_runner import EvalRunnerError, ingest_responses, prepare_run, score_run


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
        activated = [case["skill"]] if case["should_trigger"] else case["expected_route"]
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
    assert len(manifest["cases"]) == 51
    requests = [
        json.loads(line)
        for line in (run_dir / "requests.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert len(requests) == len(manifest["cases"])
    assert all(set(request) == {"schema_version", "case_id", "prompt"} for request in requests)
    assert [request["case_id"] for request in requests] == [
        case["case_id"] for case in manifest["cases"]
    ]


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
    assert metrics["coverage"] == {"cases": 51, "responses": 51, "judgments": 51}
    assert metrics["routing"]["tp"] == positive_cases
    assert metrics["routing"]["tn"] == negative_cases
    assert metrics["routing"]["fp"] == 0
    assert metrics["routing"]["fn"] == 0
    assert metrics["routing"]["precision"] == 1.0
    assert metrics["routing"]["recall"] == 1.0
    assert metrics["routing"]["route_accuracy"] == 1.0
    assert metrics["behavior"]["pass_rate"] == 1.0
    assert metrics["usage"] == {
        "input_tokens": 51 * 20,
        "output_tokens": 51 * 30,
        "latency_ms": 51 * 10,
    }
    assert len((run_dir / "results" / "cases.jsonl").read_text().splitlines()) == 51


def test_score_rejects_judgment_criterion_drift(tmp_path: Path) -> None:
    run_dir, manifest = prepared_run(tmp_path)
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
