#!/usr/bin/env python3
"""Run and judge GeoAI Skills evaluations through Claude Code."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.eval_runner import (  # noqa: E402
    EvalRunnerError,
    canonical_json,
    contract_validator,
    jsonl_text,
    load_json,
    load_jsonl,
    pretty_json,
    validate_instance,
)

RUN_SCHEMA_PATH = ROOT / "evals" / "run-schema.json"
ADAPTER_VERSION = "1"


class AdapterError(RuntimeError):
    """Raised when the runtime adapter cannot produce auditable output."""


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(content, encoding="utf-8", newline="\n")
    temporary.replace(path)


def load_manifest(run_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    run_schema = load_json(RUN_SCHEMA_PATH)
    manifest = load_json(run_dir / "manifest.json")
    validate_instance(contract_validator(run_schema, "manifest"), manifest, label="manifest")
    return manifest, run_schema


def normalize_skill_reference(value: Any, known_skills: set[str]) -> str | None:
    if not isinstance(value, str):
        return None
    candidate = value.strip().lstrip("/")
    for skill in known_skills:
        if candidate == skill or candidate.endswith(f":{skill}") or candidate.endswith(f"/{skill}"):
            return skill
    return None


def tool_skill_reference(block: dict[str, Any], known_skills: set[str]) -> str | None:
    if block.get("type") != "tool_use" or str(block.get("name", "")).lower() != "skill":
        return None
    tool_input = block.get("input", {})
    if not isinstance(tool_input, dict):
        return None
    for key in ("skill", "name", "command"):
        normalized = normalize_skill_reference(tool_input.get(key), known_skills)
        if normalized:
            return normalized
    return None


def iter_tool_blocks(value: Any) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    if isinstance(value, dict):
        if value.get("type") == "tool_use":
            blocks.append(value)
        for nested in value.values():
            blocks.extend(iter_tool_blocks(nested))
    elif isinstance(value, list):
        for nested in value:
            blocks.extend(iter_tool_blocks(nested))
    return blocks


def parse_usage(result: dict[str, Any]) -> dict[str, int]:
    usage = result.get("usage", {})
    if isinstance(usage, dict):
        input_tokens = usage.get("input_tokens", usage.get("inputTokens", 0))
        output_tokens = usage.get("output_tokens", usage.get("outputTokens", 0))
        if isinstance(input_tokens, int) and isinstance(output_tokens, int):
            return {"input_tokens": input_tokens, "output_tokens": output_tokens}

    model_usage = result.get("modelUsage", result.get("model_usage", {}))
    if isinstance(model_usage, dict):
        input_tokens = 0
        output_tokens = 0
        for entry in model_usage.values():
            if not isinstance(entry, dict):
                continue
            input_tokens += int(entry.get("inputTokens", entry.get("input_tokens", 0)))
            output_tokens += int(entry.get("outputTokens", entry.get("output_tokens", 0)))
        return {"input_tokens": input_tokens, "output_tokens": output_tokens}
    return {"input_tokens": 0, "output_tokens": 0}


def parse_stream_trace(
    trace: str,
    *,
    known_skills: set[str],
) -> dict[str, Any]:
    events = []
    for line_number, line in enumerate(trace.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise AdapterError(f"Invalid Claude stream JSON at line {line_number}: {exc}") from exc
        events.append(event)
    if not events:
        raise AdapterError("Claude Code returned an empty stream")

    activated = set()
    for event in events:
        for block in iter_tool_blocks(event):
            skill = tool_skill_reference(block, known_skills)
            if skill:
                activated.add(skill)

    result_events = [event for event in events if event.get("type") == "result"]
    if not result_events:
        raise AdapterError("Claude stream has no terminal result event")
    result = result_events[-1]
    response = result.get("result", "")
    if not isinstance(response, str):
        response = canonical_json(response)
    error = None
    if result.get("is_error") or result.get("subtype") not in (None, "success"):
        error = str(result.get("error") or result.get("subtype") or "Claude Code error")
    return {
        "response": response,
        "activated_skills": sorted(activated),
        "latency_ms": int(result.get("duration_ms", 0) or 0),
        "usage": parse_usage(result),
        "cost_usd": float(result.get("total_cost_usd", 0.0) or 0.0),
        "error": error,
    }


def parse_json_result(output: str) -> tuple[Any, dict[str, Any]]:
    try:
        outer = json.loads(output)
    except json.JSONDecodeError as exc:
        raise AdapterError(f"Claude Code returned invalid JSON: {exc}") from exc
    if outer.get("is_error") or outer.get("subtype") not in (None, "success"):
        raise AdapterError(str(outer.get("error") or outer.get("subtype") or "Claude Code error"))
    result = outer.get("result")
    if isinstance(result, str):
        try:
            parsed = json.loads(result)
        except json.JSONDecodeError as exc:
            raise AdapterError(f"Claude judge result is not JSON: {exc}") from exc
    else:
        parsed = result
    return parsed, outer


def stage_blind_plugin(source: Path, destination: Path) -> Path:
    """Copy only runtime skill assets, excluding all eval labels and repository context."""
    manifest_dir = source / ".claude-plugin"
    skills_dir = source / "skills"
    if not manifest_dir.is_dir() or not skills_dir.is_dir():
        raise AdapterError(f"Not a Claude plugin root: {source}")
    shutil.copytree(manifest_dir, destination / ".claude-plugin")
    shutil.copytree(
        skills_dir,
        destination / "skills",
        ignore=shutil.ignore_patterns("evals", "__pycache__", "*.pyc"),
    )
    return destination


def base_claude_command(
    *,
    claude_command: str,
    model: str,
    case_budget_usd: float,
    max_turns: int,
) -> list[str]:
    return [
        claude_command,
        "-p",
        "--model",
        model,
        "--no-session-persistence",
        "--permission-mode",
        "dontAsk",
        "--max-turns",
        str(max_turns),
        "--max-budget-usd",
        str(case_budget_usd),
    ]


def execution_command(
    *,
    claude_command: str,
    model: str,
    condition: str,
    plugin_dir: Path | None,
    case_budget_usd: float,
    max_turns: int,
) -> list[str]:
    command = base_claude_command(
        claude_command=claude_command,
        model=model,
        case_budget_usd=case_budget_usd,
        max_turns=max_turns,
    )
    command.extend(["--output-format", "stream-json", "--verbose"])
    if condition == "skills-enabled":
        if plugin_dir is None:
            raise AdapterError("skills-enabled execution requires a staged plugin")
        command.extend(
            [
                "--setting-sources",
                "project",
                "--strict-mcp-config",
                "--mcp-config",
                '{"mcpServers":{}}',
                "--tools",
                "Skill,Read",
                "--plugin-dir",
                str(plugin_dir),
            ]
        )
    else:
        command.extend(["--safe-mode", "--disable-slash-commands", "--tools", ""])
    return command


def judge_command(
    *,
    claude_command: str,
    model: str,
    schema: dict[str, Any],
    case_budget_usd: float,
) -> list[str]:
    command = base_claude_command(
        claude_command=claude_command,
        model=model,
        case_budget_usd=case_budget_usd,
        max_turns=1,
    )
    command.extend(
        [
            "--output-format",
            "json",
            "--json-schema",
            canonical_json(schema),
            "--safe-mode",
            "--disable-slash-commands",
            "--tools",
            "",
            "--system-prompt",
            (
                "You are a strict evaluation judge. Assess only the supplied response against "
                "the supplied criteria. Do not reward unstated behavior. Evidence must cite or "
                "briefly identify response content. Return only the requested JSON."
            ),
        ]
    )
    return command


def auth_available(claude_command: str) -> bool:
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        return True
    process = subprocess.run(
        [claude_command, "auth", "status"],
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    try:
        status = json.loads(process.stdout)
    except json.JSONDecodeError:
        return False
    return bool(status.get("loggedIn"))


def run_process(
    command: list[str],
    *,
    prompt: str,
    cwd: Path,
    timeout_seconds: int,
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["NO_COLOR"] = "1"
    try:
        return subprocess.run(
            command,
            input=prompt,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            cwd=cwd,
            env=environment,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise AdapterError(f"Claude Code timed out after {timeout_seconds}s") from exc


def response_from_failure(
    *,
    manifest: dict[str, Any],
    case_id: str,
    message: str,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "case_id": case_id,
        "runtime": manifest["runtime"],
        "model": manifest["model"],
        "condition": manifest["condition"],
        "response": "",
        "activated_skills": [],
        "usage": {"input_tokens": 0, "output_tokens": 0},
        "cost_usd": 0.0,
        "error": message[:2000] or "Unknown adapter error",
    }


def execute_one(
    *,
    request: dict[str, Any],
    case: dict[str, Any],
    manifest: dict[str, Any],
    command: list[str],
    workspace: Path,
    trace_dir: Path,
    timeout_seconds: int,
) -> dict[str, Any]:
    process = run_process(command, prompt=request["prompt"], cwd=workspace, timeout_seconds=timeout_seconds)
    trace = process.stdout
    trace_path = trace_dir / f"{case['case_sha256']}.jsonl"
    atomic_write(trace_path, trace)
    if process.returncode != 0:
        detail = process.stderr.strip() or f"Claude Code exited with {process.returncode}"
        return response_from_failure(manifest=manifest, case_id=case["case_id"], message=detail)
    try:
        parsed = parse_stream_trace(trace, known_skills={item["skill"] for item in manifest["cases"]})
    except AdapterError as exc:
        return response_from_failure(manifest=manifest, case_id=case["case_id"], message=str(exc))
    response = {
        "schema_version": 1,
        "case_id": case["case_id"],
        "runtime": manifest["runtime"],
        "model": manifest["model"],
        "condition": manifest["condition"],
        "response": parsed["response"],
        "activated_skills": parsed["activated_skills"],
        "latency_ms": parsed["latency_ms"],
        "usage": parsed["usage"],
        "cost_usd": parsed["cost_usd"],
        "trace_sha256": sha256_text(trace),
    }
    if parsed["error"]:
        response["error"] = parsed["error"]
    return response


def read_partial_rows(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    indexed = {}
    for row in load_jsonl(path):
        case_id = row.get("case_id") if isinstance(row, dict) else None
        if not isinstance(case_id, str) or case_id in indexed:
            raise AdapterError(f"Invalid or duplicate checkpoint case_id in {path}")
        indexed[case_id] = row
    return indexed


def run_in_batches(
    items: list[Any],
    *,
    workers: int,
    completed_cost: float,
    max_total_cost_usd: float,
    worker: Callable[[Any], dict[str, Any]],
    on_batch: Callable[[list[dict[str, Any]]], None],
) -> None:
    for start in range(0, len(items), workers):
        if completed_cost >= max_total_cost_usd:
            raise AdapterError(
                f"Stopped at total cost limit ${max_total_cost_usd:.4f}; resume with a higher limit"
            )
        batch = items[start : start + workers]
        results = []
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(worker, item): item for item in batch}
            for future in as_completed(futures):
                results.append(future.result())
        on_batch(results)
        completed_cost += sum(float(result.get("cost_usd", 0.0)) for result in results)


def execute_run(args: argparse.Namespace) -> Path:
    run_dir = args.run_dir.resolve()
    manifest, run_schema = load_manifest(run_dir)
    requests = load_jsonl(run_dir / "requests.jsonl")
    request_by_id = {request["case_id"]: request for request in requests}
    cases = manifest["cases"]
    if set(request_by_id) != {case["case_id"] for case in cases}:
        raise AdapterError("requests.jsonl does not exactly match the manifest")
    if args.dry_run:
        command = execution_command(
            claude_command=args.claude_command,
            model=manifest["model"],
            condition=manifest["condition"],
            plugin_dir=Path("<blind-plugin>") if manifest["condition"] == "skills-enabled" else None,
            case_budget_usd=args.max_case_cost_usd,
            max_turns=args.max_turns,
        )
        print(json.dumps(command, ensure_ascii=False))
        return run_dir / "adapter" / "claude-code.responses.jsonl"
    if not auth_available(args.claude_command):
        raise AdapterError("Claude Code is not authenticated; run `claude auth login` and retry")

    adapter_dir = run_dir / "adapter"
    checkpoint_path = adapter_dir / "claude-code.responses.jsonl"
    completed = read_partial_rows(checkpoint_path)
    known_ids = {case["case_id"] for case in cases}
    if set(completed) - known_ids:
        raise AdapterError("Checkpoint contains cases outside this manifest")
    validator = contract_validator(run_schema, "response")
    for case_id, response in completed.items():
        validate_instance(validator, response, label=f"checkpoint[{case_id}]")
        for field in ("runtime", "model", "condition"):
            if response[field] != manifest[field]:
                raise AdapterError(f"Checkpoint {case_id} has mismatched {field}")

    pending = [case for case in cases if case["case_id"] not in completed]
    completed_cost = sum(float(row.get("cost_usd", 0.0)) for row in completed.values())
    with tempfile.TemporaryDirectory(prefix="geoai-claude-adapter-") as temporary:
        temporary_root = Path(temporary)
        workspace = temporary_root / "workspace"
        workspace.mkdir()
        plugin_dir = None
        if manifest["condition"] == "skills-enabled":
            plugin_dir = stage_blind_plugin(args.plugin_dir.resolve(), temporary_root / "plugin")
        command = execution_command(
            claude_command=args.claude_command,
            model=manifest["model"],
            condition=manifest["condition"],
            plugin_dir=plugin_dir,
            case_budget_usd=args.max_case_cost_usd,
            max_turns=args.max_turns,
        )

        def worker(case: dict[str, Any]) -> dict[str, Any]:
            return execute_one(
                request=request_by_id[case["case_id"]],
                case=case,
                manifest=manifest,
                command=command,
                workspace=workspace,
                trace_dir=adapter_dir / "traces",
                timeout_seconds=args.timeout_seconds,
            )

        def save_batch(results: list[dict[str, Any]]) -> None:
            for response in results:
                validate_instance(validator, response, label=f"response[{response['case_id']}]")
                completed[response["case_id"]] = response
            ordered = [completed[case["case_id"]] for case in cases if case["case_id"] in completed]
            atomic_write(checkpoint_path, jsonl_text(ordered))
            print(f"responses {len(completed)}/{len(cases)}", file=sys.stderr)

        run_in_batches(
            pending,
            workers=args.workers,
            completed_cost=completed_cost,
            max_total_cost_usd=args.max_total_cost_usd,
            worker=worker,
            on_batch=save_batch,
        )
    if len(completed) != len(cases):
        raise AdapterError(f"Incomplete execution: {len(completed)}/{len(cases)} responses")
    return checkpoint_path


def judgment_schema(case: dict[str, Any]) -> dict[str, Any]:
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
                    "properties": {"met": {"type": "boolean"}, "evidence": {"type": "string"}},
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
    payload = {
        "user_prompt": case["prompt"],
        "assistant_response": response["response"],
        "response_error": response.get("error"),
        "case_is_critical": case["critical"],
        "expected_behavior_in_order": case["expected_behavior"],
        "forbidden_behavior_in_order": case["forbidden_behavior"],
        "instructions": (
            "Return one expected entry per expected criterion and one forbidden entry per forbidden "
            "criterion, preserving order. critical_failure is true only for a severe spatial safety or "
            "validity failure, or when a response error prevents a critical case from being answered."
        ),
    }
    return pretty_json(payload)


def judge_one(
    *,
    case: dict[str, Any],
    response: dict[str, Any],
    command: list[str],
    workspace: Path,
    trace_dir: Path,
    timeout_seconds: int,
) -> dict[str, Any]:
    process = run_process(
        command,
        prompt=judgment_prompt(case, response),
        cwd=workspace,
        timeout_seconds=timeout_seconds,
    )
    trace_path = trace_dir / f"{case['case_sha256']}.json"
    atomic_write(trace_path, process.stdout)
    if process.returncode != 0:
        raise AdapterError(process.stderr.strip() or f"Claude judge exited with {process.returncode}")
    parsed, outer = parse_json_result(process.stdout)
    expected = parsed.get("expected", [])
    forbidden = parsed.get("forbidden", [])
    if len(expected) != len(case["expected_behavior"]) or len(forbidden) != len(
        case["forbidden_behavior"]
    ):
        raise AdapterError(f"Judge returned wrong criterion count for {case['case_id']}")
    judgment = {
        "case_id": case["case_id"],
        "expected_behavior": [
            {"criterion": criterion, "met": check["met"], "evidence": check["evidence"]}
            for criterion, check in zip(case["expected_behavior"], expected, strict=True)
        ],
        "forbidden_behavior": [
            {
                "criterion": criterion,
                "observed": check["observed"],
                "evidence": check["evidence"],
            }
            for criterion, check in zip(case["forbidden_behavior"], forbidden, strict=True)
        ],
        "critical_failure": parsed["critical_failure"],
        "notes": parsed["notes"],
        "_cost_usd": float(outer.get("total_cost_usd", 0.0) or 0.0),
    }
    return judgment


def judge_run(args: argparse.Namespace) -> Path:
    run_dir = args.run_dir.resolve()
    manifest, run_schema = load_manifest(run_dir)
    responses = {row["case_id"]: row for row in load_jsonl(run_dir / "raw" / "responses.jsonl")}
    cases = manifest["cases"]
    if set(responses) != {case["case_id"] for case in cases}:
        raise AdapterError("Ingested raw responses do not exactly match the manifest")
    if args.dry_run:
        command = judge_command(
            claude_command=args.claude_command,
            model=args.judge_model,
            schema=judgment_schema(cases[0]),
            case_budget_usd=args.max_case_cost_usd,
        )
        print(json.dumps(command, ensure_ascii=False))
        return run_dir / "adapter" / "judgments.json"
    if not auth_available(args.claude_command):
        raise AdapterError("Claude Code is not authenticated; run `claude auth login` and retry")

    adapter_dir = run_dir / "adapter"
    partial_path = adapter_dir / "judgments.partial.jsonl"
    completed = read_partial_rows(partial_path)
    pending = [case for case in cases if case["case_id"] not in completed]
    completed_cost = sum(float(row.get("_cost_usd", 0.0)) for row in completed.values())
    with tempfile.TemporaryDirectory(prefix="geoai-claude-judge-") as temporary:
        workspace = Path(temporary)

        def worker(case: dict[str, Any]) -> dict[str, Any]:
            command = judge_command(
                claude_command=args.claude_command,
                model=args.judge_model,
                schema=judgment_schema(case),
                case_budget_usd=args.max_case_cost_usd,
            )
            return judge_one(
                case=case,
                response=responses[case["case_id"]],
                command=command,
                workspace=workspace,
                trace_dir=adapter_dir / "judge-traces",
                timeout_seconds=args.timeout_seconds,
            )

        def save_batch(results: list[dict[str, Any]]) -> None:
            for judgment in results:
                completed[judgment["case_id"]] = judgment
            ordered = [completed[case["case_id"]] for case in cases if case["case_id"] in completed]
            atomic_write(partial_path, jsonl_text(ordered))
            print(f"judgments {len(completed)}/{len(cases)}", file=sys.stderr)

        run_in_batches(
            pending,
            workers=args.workers,
            completed_cost=completed_cost,
            max_total_cost_usd=args.max_total_cost_usd,
            worker=worker,
            on_batch=save_batch,
        )
    if len(completed) != len(cases):
        raise AdapterError(f"Incomplete judging: {len(completed)}/{len(cases)} judgments")
    clean_judgments = []
    for case in cases:
        judgment = dict(completed[case["case_id"]])
        judgment.pop("_cost_usd", None)
        clean_judgments.append(judgment)
    judgment_set = {
        "schema_version": 1,
        "suite_sha256": manifest["suite_sha256"],
        "judge": {"kind": "model", "name": "claude-code", "version": args.judge_model},
        "judgments": clean_judgments,
    }
    validate_instance(
        contract_validator(run_schema, "judgmentSet"), judgment_set, label="judgments"
    )
    output_path = adapter_dir / "judgments.json"
    atomic_write(output_path, pretty_json(judgment_set))
    metrics = {
        "adapter_version": ADAPTER_VERSION,
        "judge_model": args.judge_model,
        "cases": len(cases),
        "total_cost_usd": sum(float(row.get("_cost_usd", 0.0)) for row in completed.values()),
    }
    atomic_write(adapter_dir / "judge-metrics.json", pretty_json(metrics))
    return output_path


def add_shared_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--claude-command", default="claude")
    parser.add_argument("--workers", type=int, default=1, choices=range(1, 9))
    parser.add_argument("--timeout-seconds", type=int, default=300)
    parser.add_argument("--max-case-cost-usd", type=float, required=True)
    parser.add_argument("--max-total-cost-usd", type=float, required=True)
    parser.add_argument("--dry-run", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    execute = subparsers.add_parser("execute", help="Run blind prompts and capture Skill traces")
    add_shared_arguments(execute)
    execute.add_argument("--plugin-dir", type=Path, default=ROOT)
    execute.add_argument("--max-turns", type=int, default=4)

    judge = subparsers.add_parser("judge", help="Judge cached responses criterion by criterion")
    add_shared_arguments(judge)
    judge.add_argument("--judge-model", required=True)
    return parser


def validate_args(args: argparse.Namespace) -> None:
    if args.max_case_cost_usd <= 0 or args.max_total_cost_usd <= 0:
        raise AdapterError("Cost limits must be positive")
    if args.max_case_cost_usd > args.max_total_cost_usd:
        raise AdapterError("Per-case cost limit cannot exceed total cost limit")
    if args.timeout_seconds < 1:
        raise AdapterError("timeout-seconds must be positive")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        validate_args(args)
        output = execute_run(args) if args.command == "execute" else judge_run(args)
    except (AdapterError, EvalRunnerError, OSError) as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
