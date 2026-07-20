from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.eval_runner import EvalRunnerError, ingest_responses, prepare_run, score_run
from tools.publish_routing_benchmark import publish_routing_benchmark


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


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


def scored_run(tmp_path: Path, condition: str) -> Path:
    run_dir = prepare_run(
        runtime="test-runtime",
        model="test-model-v1",
        condition=condition,
        evaluation_scope="routing",
        runs_dir=tmp_path / "runs",
    )
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    responses = perfect_responses(manifest)
    if condition == "skills-disabled":
        for response in responses:
            response["activated_skills"] = []
    response_path = tmp_path / f"{condition}.jsonl"
    write_jsonl(response_path, responses)
    ingest_responses(run_dir=run_dir, input_path=response_path)
    judgments = {
        "schema_version": 1,
        "suite_sha256": manifest["suite_sha256"],
        "judge": {"kind": "rule", "name": "routing-only", "version": "1"},
        "judgments": [],
    }
    judgment_path = tmp_path / f"{condition}-judgments.json"
    judgment_path.write_text(json.dumps(judgments), encoding="utf-8")
    score_run(run_dir=run_dir, judgments_path=judgment_path)
    return run_dir


def test_publish_routing_benchmark_is_sanitized_and_reproducible(tmp_path: Path) -> None:
    enabled = scored_run(tmp_path, "skills-enabled")
    disabled = scored_run(tmp_path, "skills-disabled")
    output_dir = tmp_path / "published"

    metrics_path = publish_routing_benchmark(
        enabled_run=enabled,
        disabled_run=disabled,
        output_dir=output_dir,
    )
    first_bytes = {path.name: path.read_bytes() for path in output_dir.iterdir()}
    publish_routing_benchmark(
        enabled_run=enabled,
        disabled_run=disabled,
        output_dir=output_dir,
    )

    summary = json.loads(metrics_path.read_text(encoding="utf-8"))
    cases_text = (output_dir / "cases.jsonl").read_text(encoding="utf-8")
    assert summary["behavior"]["status"] == "not_evaluated"
    assert summary["conditions"]["skills-enabled"]["routing"]["recall"] == 1.0
    assert summary["conditions"]["skills-disabled"]["any_activation_cases"] == 0
    assert '"response"' not in cases_text
    assert "A deterministic test response." not in cases_text
    assert first_bytes == {path.name: path.read_bytes() for path in output_dir.iterdir()}


def test_publish_rejects_behavior_scored_run(tmp_path: Path) -> None:
    enabled = scored_run(tmp_path, "skills-enabled")
    disabled = scored_run(tmp_path, "skills-disabled")
    metrics_path = enabled / "results" / "metrics.json"
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    metrics["behavior"]["judged_cases"] = 1
    metrics_path.write_text(json.dumps(metrics), encoding="utf-8")

    with pytest.raises(EvalRunnerError, match="routing-only"):
        publish_routing_benchmark(
            enabled_run=enabled,
            disabled_run=disabled,
            output_dir=tmp_path / "published",
        )
