#!/usr/bin/env python3
"""Prepare, ingest, and score reproducible GeoAI Skills evaluation runs."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "skills"
EVAL_SCHEMA_PATH = ROOT / "evals" / "schema.json"
RUN_SCHEMA_PATH = ROOT / "evals" / "run-schema.json"
DEFAULT_RUNS_DIR = ROOT / "evals" / "runs"


class EvalRunnerError(RuntimeError):
    """Raised when an evaluation run violates a deterministic contract."""


def canonical_json(value: Any) -> str:
    """Return the canonical JSON representation used for hashes and comparisons."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise EvalRunnerError(f"Missing file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise EvalRunnerError(f"Invalid JSON in {path}: {exc}") from exc


def load_jsonl(path: Path) -> list[Any]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError as exc:
        raise EvalRunnerError(f"Missing file: {path}") from exc

    rows: list[Any] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise EvalRunnerError(f"Invalid JSON in {path}:{line_number}: {exc}") from exc
    return rows


def pretty_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def jsonl_text(rows: Iterable[Any]) -> str:
    return "".join(canonical_json(row) + "\n" for row in rows)


def write_immutable(path: Path, content: str, *, force: bool = False) -> bool:
    """Write content atomically, refusing a different overwrite unless forced."""
    if path.exists():
        current = path.read_text(encoding="utf-8")
        if current == content:
            return False
        if not force:
            raise EvalRunnerError(
                f"Refusing to overwrite different content at {path}; use --force intentionally"
            )
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(content, encoding="utf-8", newline="\n")
    temporary.replace(path)
    return True


def contract_validator(run_schema: dict[str, Any], definition: str) -> Draft202012Validator:
    if definition not in run_schema.get("$defs", {}):
        raise EvalRunnerError(f"Unknown run contract: {definition}")
    schema = {
        "$schema": run_schema["$schema"],
        "$defs": run_schema["$defs"],
        "$ref": f"#/$defs/{definition}",
    }
    return Draft202012Validator(schema)


def validate_instance(
    validator: Draft202012Validator,
    value: Any,
    *,
    label: str,
) -> None:
    issues = sorted(validator.iter_errors(value), key=lambda issue: list(issue.absolute_path))
    if not issues:
        return
    rendered = []
    for issue in issues:
        location = "/".join(str(part) for part in issue.absolute_path) or "<root>"
        rendered.append(f"{label}:{location}: {issue.message}")
    raise EvalRunnerError("\n".join(rendered))


def validate_unique_exact_ids(
    rows: list[dict[str, Any]],
    expected_ids: list[str],
    *,
    label: str,
) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    duplicates: set[str] = set()
    for row in rows:
        case_id = row.get("case_id") if isinstance(row, dict) else None
        if case_id in indexed:
            duplicates.add(str(case_id))
        elif isinstance(case_id, str):
            indexed[case_id] = row
    if duplicates:
        raise EvalRunnerError(f"{label} contains duplicate case ids: {', '.join(sorted(duplicates))}")

    expected = set(expected_ids)
    actual = set(indexed)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    problems = []
    if missing:
        problems.append(f"missing: {', '.join(missing)}")
    if extra:
        problems.append(f"unexpected: {', '.join(extra)}")
    if problems:
        raise EvalRunnerError(f"{label} case coverage mismatch ({'; '.join(problems)})")
    return indexed


def load_suite(
    *,
    skills_dir: Path = SKILLS,
    eval_schema_path: Path = EVAL_SCHEMA_PATH,
) -> tuple[list[dict[str, Any]], str, list[str]]:
    """Load, normalize, validate, and hash the complete evaluation suite."""
    eval_schema = load_json(eval_schema_path)
    Draft202012Validator.check_schema(eval_schema)
    validator = Draft202012Validator(eval_schema)
    cases: list[dict[str, Any]] = []
    skill_names: list[str] = []

    for skill_dir in sorted(path for path in skills_dir.iterdir() if path.is_dir()):
        skill_path = skill_dir / "SKILL.md"
        eval_path = skill_dir / "evals" / "evals.json"
        if not skill_path.exists() or not eval_path.exists():
            raise EvalRunnerError(f"{skill_dir.name}: SKILL.md and evals/evals.json are required")
        data = load_json(eval_path)
        issues = sorted(validator.iter_errors(data), key=lambda issue: list(issue.absolute_path))
        if issues:
            details = []
            for issue in issues:
                location = "/".join(str(part) for part in issue.absolute_path) or "<root>"
                details.append(f"{eval_path}:{location}: {issue.message}")
            raise EvalRunnerError("\n".join(details))
        if data["skill"] != skill_dir.name:
            raise EvalRunnerError(
                f"{eval_path}: skill '{data['skill']}' does not match folder '{skill_dir.name}'"
            )

        skill_names.append(skill_dir.name)
        skill_sha256 = sha256_bytes(skill_path.read_bytes())
        for raw_case in data["evals"]:
            normalized = {
                "case_id": f"{skill_dir.name}/{raw_case['id']}",
                "skill": skill_dir.name,
                "eval_id": raw_case["id"],
                "prompt": raw_case["prompt"],
                "case_types": raw_case["case_types"],
                "should_trigger": raw_case.get("should_trigger", True),
                "expected_route": sorted(raw_case.get("expected_route", [])),
                "expected_behavior": raw_case["expected_behavior"],
                "forbidden_behavior": raw_case.get("forbidden_behavior", []),
                "critical": raw_case.get("critical", False),
                "skill_sha256": skill_sha256,
            }
            normalized["case_sha256"] = sha256_json(normalized)
            cases.append(normalized)

    cases.sort(key=lambda case: case["case_id"])
    ids = [case["case_id"] for case in cases]
    if len(ids) != len(set(ids)):
        duplicates = sorted({case_id for case_id in ids if ids.count(case_id) > 1})
        raise EvalRunnerError(f"Duplicate global case ids: {', '.join(duplicates)}")
    suite_sha256 = sha256_json(cases)
    return cases, suite_sha256, sorted(skill_names)


def slug(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return normalized[:60] or "unknown"


def prepare_run(
    *,
    runtime: str,
    model: str,
    condition: str,
    runs_dir: Path = DEFAULT_RUNS_DIR,
    run_id: str | None = None,
    skills_dir: Path = SKILLS,
    eval_schema_path: Path = EVAL_SCHEMA_PATH,
    run_schema_path: Path = RUN_SCHEMA_PATH,
) -> Path:
    if condition not in {"skills-enabled", "skills-disabled"}:
        raise EvalRunnerError("condition must be skills-enabled or skills-disabled")
    cases, suite_sha256, skill_names = load_suite(
        skills_dir=skills_dir,
        eval_schema_path=eval_schema_path,
    )
    run_schema = load_json(run_schema_path)
    Draft202012Validator.check_schema(run_schema)
    manifest = {
        "kind": "geoai-eval-manifest",
        "schema_version": 1,
        "suite_sha256": suite_sha256,
        "runtime": runtime,
        "model": model,
        "condition": condition,
        "available_skills": skill_names if condition == "skills-enabled" else [],
        "cases": cases,
    }
    validate_instance(contract_validator(run_schema, "manifest"), manifest, label="manifest")

    selected_id = run_id or (
        f"{slug(runtime)}--{slug(model)}--{condition}--{suite_sha256[:12]}"
    )
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,199}", selected_id):
        raise EvalRunnerError("run-id must be 1-200 safe filename characters")
    run_dir = runs_dir / selected_id
    requests = [
        {"schema_version": 1, "case_id": case["case_id"], "prompt": case["prompt"]}
        for case in cases
    ]
    request_validator = contract_validator(run_schema, "request")
    for index, request in enumerate(requests, start=1):
        validate_instance(request_validator, request, label=f"request[{index}]")

    write_immutable(run_dir / "manifest.json", pretty_json(manifest))
    write_immutable(run_dir / "requests.jsonl", jsonl_text(requests))
    return run_dir


def load_manifest(run_dir: Path, run_schema: dict[str, Any]) -> dict[str, Any]:
    manifest = load_json(run_dir / "manifest.json")
    validate_instance(contract_validator(run_schema, "manifest"), manifest, label="manifest")
    return manifest


def validate_response_context(
    *,
    manifest: dict[str, Any],
    cases: list[dict[str, Any]],
    responses: dict[str, dict[str, Any]],
) -> None:
    """Ensure cached responses still belong to the declared run and suite."""
    known_skills = {case["skill"] for case in cases}
    for case in cases:
        row = responses[case["case_id"]]
        for field in ("runtime", "model", "condition"):
            if row[field] != manifest[field]:
                raise EvalRunnerError(
                    f"{case['case_id']}: response {field} '{row[field]}' "
                    f"does not match manifest '{manifest[field]}'"
                )
        unknown = sorted(set(row["activated_skills"]) - known_skills)
        if unknown:
            raise EvalRunnerError(
                f"{case['case_id']}: unknown activated skills: {', '.join(unknown)}"
            )


def ingest_responses(
    *,
    run_dir: Path,
    input_path: Path,
    force: bool = False,
    run_schema_path: Path = RUN_SCHEMA_PATH,
) -> Path:
    run_schema = load_json(run_schema_path)
    manifest = load_manifest(run_dir, run_schema)
    rows = load_jsonl(input_path)
    response_validator = contract_validator(run_schema, "response")
    for index, row in enumerate(rows, start=1):
        validate_instance(response_validator, row, label=f"response[{index}]")

    cases = manifest["cases"]
    expected_ids = [case["case_id"] for case in cases]
    indexed = validate_unique_exact_ids(rows, expected_ids, label="responses")
    validate_response_context(manifest=manifest, cases=cases, responses=indexed)
    normalized = []
    for case in cases:
        row = indexed[case["case_id"]]
        normalized.append(row)

    raw_path = run_dir / "raw" / "responses.jsonl"
    write_immutable(raw_path, jsonl_text(normalized), force=force)
    for case, row in zip(cases, normalized, strict=True):
        cache_path = run_dir / "cache" / f"{case['case_sha256']}.json"
        write_immutable(cache_path, pretty_json(row), force=force)
    return raw_path


def ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def score_run(
    *,
    run_dir: Path,
    judgments_path: Path,
    force: bool = False,
    run_schema_path: Path = RUN_SCHEMA_PATH,
) -> Path:
    run_schema = load_json(run_schema_path)
    manifest = load_manifest(run_dir, run_schema)
    response_rows = load_jsonl(run_dir / "raw" / "responses.jsonl")
    response_validator = contract_validator(run_schema, "response")
    for index, row in enumerate(response_rows, start=1):
        validate_instance(response_validator, row, label=f"cached response[{index}]")

    cases = manifest["cases"]
    expected_ids = [case["case_id"] for case in cases]
    responses = validate_unique_exact_ids(response_rows, expected_ids, label="cached responses")
    validate_response_context(manifest=manifest, cases=cases, responses=responses)

    judgment_set = load_json(judgments_path)
    validate_instance(
        contract_validator(run_schema, "judgmentSet"),
        judgment_set,
        label="judgments",
    )
    if judgment_set["suite_sha256"] != manifest["suite_sha256"]:
        raise EvalRunnerError("Judgment suite_sha256 does not match the manifest")
    judgments = validate_unique_exact_ids(
        judgment_set["judgments"], expected_ids, label="judgments"
    )

    case_results = []
    counts = {"tp": 0, "tn": 0, "fp": 0, "fn": 0}
    route_matches = 0
    behavior_passes = 0
    criteria_met = 0
    criteria_total = 0
    forbidden_violations = 0
    critical_evaluated = 0
    critical_failures = 0
    input_tokens = 0
    output_tokens = 0
    latency_ms = 0
    cost_usd = 0.0

    for case in cases:
        case_id = case["case_id"]
        response = responses[case_id]
        judgment = judgments[case_id]
        expected_criteria = [check["criterion"] for check in judgment["expected_behavior"]]
        forbidden_criteria = [check["criterion"] for check in judgment["forbidden_behavior"]]
        if expected_criteria != case["expected_behavior"]:
            raise EvalRunnerError(f"{case_id}: expected_behavior criteria drift from manifest")
        if forbidden_criteria != case["forbidden_behavior"]:
            raise EvalRunnerError(f"{case_id}: forbidden_behavior criteria drift from manifest")

        activated = set(response["activated_skills"])
        target_active = case["skill"] in activated
        if case["should_trigger"]:
            outcome = "tp" if target_active else "fn"
            expected_route = set(case["expected_route"] or [case["skill"]])
            route_match = target_active and expected_route.issubset(activated)
        else:
            outcome = "fp" if target_active else "tn"
            expected_route = set(case["expected_route"])
            route_match = not target_active and expected_route.issubset(activated)
        counts[outcome] += 1
        route_matches += int(route_match)

        met = sum(int(check["met"]) for check in judgment["expected_behavior"])
        violations = sum(int(check["observed"]) for check in judgment["forbidden_behavior"])
        response_error = bool(response.get("error"))
        behavior_pass = (
            met == len(judgment["expected_behavior"])
            and violations == 0
            and not judgment["critical_failure"]
            and not response_error
        )
        behavior_passes += int(behavior_pass)
        criteria_met += met
        criteria_total += len(judgment["expected_behavior"])
        forbidden_violations += violations
        if case["critical"]:
            critical_evaluated += 1
            critical_failures += int(judgment["critical_failure"] or response_error)

        usage = response.get("usage", {})
        input_tokens += usage.get("input_tokens", 0)
        output_tokens += usage.get("output_tokens", 0)
        latency_ms += response.get("latency_ms", 0)
        cost_usd += response.get("cost_usd", 0.0)
        result = {
            "case_id": case_id,
            "skill": case["skill"],
            "routing_outcome": outcome,
            "route_match": route_match,
            "behavior_pass": behavior_pass,
            "expected_met": met,
            "expected_total": len(judgment["expected_behavior"]),
            "forbidden_violations": violations,
            "critical_failure": judgment["critical_failure"],
            "response_error": response_error,
        }
        validate_instance(
            contract_validator(run_schema, "caseResult"), result, label=f"result[{case_id}]"
        )
        case_results.append(result)

    total = len(cases)
    metrics = {
        "schema_version": 1,
        "suite_sha256": manifest["suite_sha256"],
        "runtime": manifest["runtime"],
        "model": manifest["model"],
        "condition": manifest["condition"],
        "judge": judgment_set["judge"],
        "coverage": {"cases": total, "responses": len(responses), "judgments": len(judgments)},
        "routing": {
            **counts,
            "precision": ratio(counts["tp"], counts["tp"] + counts["fp"]),
            "recall": ratio(counts["tp"], counts["tp"] + counts["fn"]),
            "accuracy": ratio(counts["tp"] + counts["tn"], total),
            "route_accuracy": ratio(route_matches, total),
        },
        "behavior": {
            "passed_cases": behavior_passes,
            "judged_cases": total,
            "pass_rate": ratio(behavior_passes, total),
            "criteria_met": criteria_met,
            "criteria_total": criteria_total,
            "forbidden_violations": forbidden_violations,
        },
        "critical": {
            "evaluated_cases": critical_evaluated,
            "failures": critical_failures,
            "failure_rate": ratio(critical_failures, critical_evaluated),
        },
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "latency_ms": latency_ms,
            "cost_usd": cost_usd,
        },
    }
    validate_instance(contract_validator(run_schema, "results"), metrics, label="metrics")
    results_dir = run_dir / "results"
    write_immutable(results_dir / "cases.jsonl", jsonl_text(case_results), force=force)
    metrics_path = results_dir / "metrics.json"
    write_immutable(metrics_path, pretty_json(metrics), force=force)
    return metrics_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepare, ingest, and score deterministic GeoAI Skills evaluations."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare", help="Create a blind request manifest")
    prepare.add_argument("--runtime", required=True, help="Agent runtime name")
    prepare.add_argument("--model", required=True, help="Model identifier")
    prepare.add_argument(
        "--condition",
        required=True,
        choices=("skills-enabled", "skills-disabled"),
    )
    prepare.add_argument("--runs-dir", type=Path, default=DEFAULT_RUNS_DIR)
    prepare.add_argument("--run-id", help="Optional stable run directory name")

    ingest = subparsers.add_parser("ingest", help="Validate and cache raw runtime responses")
    ingest.add_argument("--run-dir", type=Path, required=True)
    ingest.add_argument("--input", type=Path, required=True, dest="input_path")
    ingest.add_argument("--force", action="store_true", help="Replace different cached content")

    score = subparsers.add_parser("score", help="Score cached responses from explicit judgments")
    score.add_argument("--run-dir", type=Path, required=True)
    score.add_argument("--judgments", type=Path, required=True, dest="judgments_path")
    score.add_argument("--force", action="store_true", help="Replace different result content")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "prepare":
            output = prepare_run(
                runtime=args.runtime,
                model=args.model,
                condition=args.condition,
                runs_dir=args.runs_dir,
                run_id=args.run_id,
            )
        elif args.command == "ingest":
            output = ingest_responses(
                run_dir=args.run_dir,
                input_path=args.input_path,
                force=args.force,
            )
        else:
            output = score_run(
                run_dir=args.run_dir,
                judgments_path=args.judgments_path,
                force=args.force,
            )
    except (EvalRunnerError, OSError) as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
