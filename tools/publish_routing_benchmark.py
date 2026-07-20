#!/usr/bin/env python3
"""Publish sanitized, independently aggregable routing benchmark evidence."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.eval_runner import EvalRunnerError, canonical_json, load_json, load_jsonl, ratio


def pretty_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def write_reproducible(path: Path, content: str, *, force: bool) -> None:
    if path.exists():
        existing = path.read_text(encoding="utf-8")
        if existing == content:
            return
        if not force:
            raise EvalRunnerError(f"Refusing to replace different benchmark content: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def index_exact(rows: list[dict[str, Any]], ids: list[str], *, label: str) -> dict[str, dict]:
    indexed: dict[str, dict] = {}
    for row in rows:
        case_id = row.get("case_id")
        if not isinstance(case_id, str) or case_id in indexed:
            raise EvalRunnerError(f"Invalid or duplicate case_id in {label}: {case_id!r}")
        indexed[case_id] = row
    if set(indexed) != set(ids):
        missing = sorted(set(ids) - set(indexed))
        extra = sorted(set(indexed) - set(ids))
        raise EvalRunnerError(f"{label} case mismatch; missing={missing}, extra={extra}")
    return indexed


def aggregate_routing(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(row["routing_outcome"] for row in rows)
    total = len(rows)
    return {
        "accuracy": ratio(counts["tp"] + counts["tn"], total),
        "fn": counts["fn"],
        "fp": counts["fp"],
        "precision": ratio(counts["tp"], counts["tp"] + counts["fp"]),
        "recall": ratio(counts["tp"], counts["tp"] + counts["fn"]),
        "route_accuracy": ratio(sum(bool(row["route_match"]) for row in rows), total),
        "tn": counts["tn"],
        "tp": counts["tp"],
    }


def public_run(run_dir: Path, *, expected_condition: str) -> dict[str, Any]:
    manifest = load_json(run_dir / "manifest.json")
    metrics = load_json(run_dir / "results" / "metrics.json")
    result_rows = load_jsonl(run_dir / "results" / "cases.jsonl")
    response_rows = load_jsonl(run_dir / "raw" / "responses.jsonl")
    cases = manifest["cases"]
    ids = [case["case_id"] for case in cases]

    if manifest["condition"] != expected_condition or metrics["condition"] != expected_condition:
        raise EvalRunnerError(f"Expected {expected_condition} run: {run_dir}")
    for key in ("runtime", "model", "suite_sha256"):
        if manifest[key] != metrics[key]:
            raise EvalRunnerError(f"Manifest/metrics {key} mismatch: {run_dir}")
    if metrics["coverage"] != {"cases": len(cases), "judgments": 0, "responses": len(cases)}:
        raise EvalRunnerError(f"Run is incomplete or includes behavior judgments: {run_dir}")
    if metrics["behavior"]["judged_cases"] != 0 or metrics["behavior"]["pass_rate"] is not None:
        raise EvalRunnerError(f"Benchmark publisher accepts routing-only results: {run_dir}")

    results = index_exact(result_rows, ids, label=f"{expected_condition} results")
    responses = index_exact(response_rows, ids, label=f"{expected_condition} responses")
    if aggregate_routing(result_rows) != metrics["routing"]:
        raise EvalRunnerError(f"Published routing metrics do not recompute: {run_dir}")

    public_cases = []
    for case in cases:
        case_id = case["case_id"]
        result = results[case_id]
        response = responses[case_id]
        if response["runtime"] != manifest["runtime"] or response["model"] != manifest["model"]:
            raise EvalRunnerError(f"Response runtime/model mismatch for {case_id}")
        if response["condition"] != expected_condition:
            raise EvalRunnerError(f"Response condition mismatch for {case_id}")
        error = response.get("error")
        public_cases.append(
            {
                "activated_skills": response["activated_skills"],
                "case_id": case_id,
                "case_types": case["case_types"],
                "condition": expected_condition,
                "cost_usd": response.get("cost_usd", 0.0),
                "error_code": error.split(";", 1)[0] if error else None,
                "expected_route": case["expected_route"],
                "latency_ms": response["latency_ms"],
                "response_error": result["response_error"],
                "route_match": result["route_match"],
                "routing_outcome": result["routing_outcome"],
                "schema_version": 1,
                "should_trigger": case["should_trigger"],
                "skill": case["skill"],
                "trace_sha256": response.get("trace_sha256"),
                "usage": response["usage"],
            }
        )
    return {"manifest": manifest, "metrics": metrics, "cases": public_cases}


def per_skill(cases: list[dict[str, Any]], skills: list[str]) -> list[dict[str, Any]]:
    rows = []
    for skill in skills:
        selected = [case for case in cases if case["skill"] == skill]
        rows.append(
            {
                "cases": len(selected),
                "errors": sum(case["response_error"] for case in selected),
                "negative_cases": sum(not case["should_trigger"] for case in selected),
                "positive_cases": sum(case["should_trigger"] for case in selected),
                "routing": aggregate_routing(selected),
                "skill": skill,
            }
        )
    return rows


def publish_routing_benchmark(
    *, enabled_run: Path, disabled_run: Path, output_dir: Path, force: bool = False
) -> Path:
    enabled = public_run(enabled_run, expected_condition="skills-enabled")
    disabled = public_run(disabled_run, expected_condition="skills-disabled")
    enabled_manifest = enabled["manifest"]
    disabled_manifest = disabled["manifest"]
    for key in ("runtime", "model", "suite_sha256"):
        if enabled_manifest[key] != disabled_manifest[key]:
            raise EvalRunnerError(f"Enabled/disabled {key} mismatch")
    if not enabled_manifest["available_skills"]:
        raise EvalRunnerError("Enabled run exposes no skills")
    if disabled_manifest["available_skills"]:
        raise EvalRunnerError("Disabled control unexpectedly exposes skills")
    enabled_case_contract = [
        {key: case[key] for key in ("case_id", "case_sha256", "skill")}
        for case in enabled_manifest["cases"]
    ]
    disabled_case_contract = [
        {key: case[key] for key in ("case_id", "case_sha256", "skill")}
        for case in disabled_manifest["cases"]
    ]
    if canonical_json(enabled_case_contract) != canonical_json(disabled_case_contract):
        raise EvalRunnerError("Enabled/disabled case contracts differ")

    skills = enabled_manifest["available_skills"]
    case_types = Counter(
        case_type for case in enabled_manifest["cases"] for case_type in case["case_types"]
    )
    summary = {
        "behavior": {
            "status": "not_evaluated",
            "reason": "This release publishes routing evidence only; no behavior judgments are included.",
        },
        "case_mix": {
            "case_types": dict(sorted(case_types.items())),
            "negative": sum(not case["should_trigger"] for case in enabled_manifest["cases"]),
            "positive": sum(case["should_trigger"] for case in enabled_manifest["cases"]),
            "total": len(enabled_manifest["cases"]),
        },
        "conditions": {},
        "kind": "routing",
        "model": enabled_manifest["model"],
        "runtime": enabled_manifest["runtime"],
        "schema_version": 1,
        "skills": len(skills),
        "suite_sha256": enabled_manifest["suite_sha256"],
    }
    per_skill_output: dict[str, Any] = {
        "model": enabled_manifest["model"],
        "runtime": enabled_manifest["runtime"],
        "schema_version": 1,
        "suite_sha256": enabled_manifest["suite_sha256"],
    }
    all_cases = []
    for condition, run in (("skills-enabled", enabled), ("skills-disabled", disabled)):
        cases = run["cases"]
        metrics = run["metrics"]
        summary["conditions"][condition] = {
            "any_activation_cases": sum(bool(case["activated_skills"]) for case in cases),
            "errors": sum(case["response_error"] for case in cases),
            "routing": metrics["routing"],
            "usage": metrics["usage"],
        }
        per_skill_output[condition] = per_skill(cases, skills)
        all_cases.extend(cases)

    write_reproducible(output_dir / "metrics.json", pretty_json(summary), force=force)
    write_reproducible(output_dir / "per-skill.json", pretty_json(per_skill_output), force=force)
    cases_text = "".join(
        json.dumps(case, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        for case in all_cases
    )
    write_reproducible(output_dir / "cases.jsonl", cases_text, force=force)
    return output_dir / "metrics.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--enabled-run", type=Path, required=True)
    parser.add_argument("--disabled-run", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--force", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        output = publish_routing_benchmark(
            enabled_run=args.enabled_run,
            disabled_run=args.disabled_run,
            output_dir=args.output_dir,
            force=args.force,
        )
    except (EvalRunnerError, OSError) as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
