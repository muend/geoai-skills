#!/usr/bin/env python3
"""Judge cached GeoAI behavior responses through the OpenAI Codex CLI."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.adapters.judge_contract import (  # noqa: E402
    PROMPT_VERSION,
    judgment_prompt,
    judgment_schema,
    restore_judgment,
)
from tools.eval_runner import (  # noqa: E402
    EvalRunnerError,
    contract_validator,
    jsonl_text,
    load_json,
    load_jsonl,
    pretty_json,
    validate_instance,
)

RUN_SCHEMA_PATH = ROOT / "evals" / "run-schema.json"
ADAPTER_VERSION = "1"
MODEL_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")
CLI_VERSION_PATTERN = re.compile(r"\bcodex-cli\s+([0-9][0-9A-Za-z.+-]*)\b")
REASONING_EFFORTS = ("low", "medium", "high", "xhigh")
SYSTEM_INSTRUCTION = (
    "You are a strict independent evaluation judge. Assess only the supplied assistant response "
    "against the supplied criteria. Do not use shell commands, files, MCP servers, web search, or "
    "any other tool. Do not reward unstated behavior. Evidence must quote or closely identify "
    "content in the supplied response. Return only the JSON object required by the output schema."
)
DISALLOWED_ITEM_TYPES = {
    "command_execution",
    "file_change",
    "mcp_tool_call",
    "web_search",
}
USAGE_KEYS = (
    "input_tokens",
    "cached_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
)
ProcessRunner = Callable[..., subprocess.CompletedProcess[str]]
CommandFinder = Callable[[str], str | None]


class CodexAdapterError(RuntimeError):
    """Raised when Codex cannot produce auditable criterion judgments."""


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(content, encoding="utf-8", newline="\n")
    temporary.replace(path)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def load_manifest(run_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    run_schema = load_json(RUN_SCHEMA_PATH)
    manifest = load_json(run_dir / "manifest.json")
    validate_instance(
        contract_validator(run_schema, "manifest"), manifest, label="manifest"
    )
    return manifest, run_schema


def read_partial_rows(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    indexed: dict[str, dict[str, Any]] = {}
    for row in load_jsonl(path):
        case_id = row.get("case_id") if isinstance(row, dict) else None
        if not isinstance(case_id, str) or case_id in indexed:
            raise CodexAdapterError(
                f"Invalid or duplicate checkpoint case_id in {path}"
            )
        indexed[case_id] = row
    return indexed


def select_cases(
    cases: list[dict[str, Any]], requested_ids: list[str] | None
) -> list[dict[str, Any]]:
    if not requested_ids:
        return cases
    requested = set(requested_ids)
    known = {case["case_id"] for case in cases}
    unknown = sorted(requested - known)
    if unknown:
        raise CodexAdapterError(f"Unknown requested case ids: {', '.join(unknown)}")
    return [case for case in cases if case["case_id"] in requested]


def clean_judgment(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if not key.startswith("_")}


def judge_namespace(
    model: str, runtime_version: str, reasoning_effort: str
) -> str:
    """Isolate checkpoints by every input that can change judge behavior."""

    def slug(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")

    return (
        f"codex-cli-{slug(runtime_version)}--{slug(model)}--"
        f"reasoning-{slug(reasoning_effort)}--{PROMPT_VERSION}"
    )


def resolve_codex_command(
    command: str,
    *,
    platform_name: str | None = None,
    which: CommandFinder = shutil.which,
) -> str:
    """Prefer the npm command shim over a shadowing Windows Store alias."""
    platform = os.name if platform_name is None else platform_name
    if Path(command).parent != Path("."):
        return command
    candidates = [f"{command}.cmd", command] if platform == "nt" else [command]
    for candidate in candidates:
        resolved = which(candidate)
        if resolved:
            return resolved
    return command


def build_command(
    *,
    codex_command: str,
    model: str,
    reasoning_effort: str,
    workspace: Path,
    schema_path: Path,
    output_path: Path,
) -> list[str]:
    """Build an isolated non-interactive command; the private prompt uses stdin."""
    return [
        codex_command,
        "exec",
        "--json",
        "--ephemeral",
        "--ignore-user-config",
        "--sandbox",
        "read-only",
        "--cd",
        str(workspace),
        "--skip-git-repo-check",
        "--model",
        model,
        "--config",
        f'model_reasoning_effort="{reasoning_effort}"',
        "--output-schema",
        str(schema_path),
        "--output-last-message",
        str(output_path),
        "-",
    ]


def _usage_value(usage: dict[str, Any], key: str) -> int:
    value = usage.get(key, 0)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise CodexAdapterError(f"Codex trace has invalid usage.{key}")
    return value


def parse_jsonl_trace(trace: str) -> dict[str, Any]:
    """Parse the documented Codex JSONL stream and reject tool-assisted judging."""
    events: list[dict[str, Any]] = []
    for line_number, line in enumerate(trace.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise CodexAdapterError(
                f"Codex JSONL is invalid on line {line_number}: {exc}"
            ) from exc
        if not isinstance(event, dict):
            raise CodexAdapterError(
                f"Codex JSONL line {line_number} is not an object"
            )
        events.append(event)
    if not events:
        raise CodexAdapterError("Codex returned an empty JSONL stream")

    terminal = [event for event in events if event.get("type") == "turn.completed"]
    failures = [
        event
        for event in events
        if event.get("type") in {"turn.failed", "error"}
    ]
    if failures:
        raise CodexAdapterError("Codex trace contains a terminal failure event")
    if len(terminal) != 1:
        raise CodexAdapterError(
            f"Codex trace must contain one turn.completed event, found {len(terminal)}"
        )

    used_tools: list[str] = []
    for event in events:
        item = event.get("item")
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")
        if item_type in DISALLOWED_ITEM_TYPES:
            used_tools.append(str(item_type))
    if used_tools:
        raise CodexAdapterError(
            f"Codex judge used prohibited tools: {', '.join(sorted(set(used_tools)))}"
        )

    usage = terminal[0].get("usage")
    if not isinstance(usage, dict):
        raise CodexAdapterError("Codex turn.completed event omits usage")
    thread_ids = {
        event["thread_id"]
        for event in events
        if event.get("type") == "thread.started"
        and isinstance(event.get("thread_id"), str)
        and event["thread_id"]
    }
    if len(thread_ids) != 1:
        raise CodexAdapterError(
            f"Codex trace must identify one thread, found {len(thread_ids)}"
        )
    return {
        "events": events,
        "thread_id": next(iter(thread_ids)),
        "usage": {key: _usage_value(usage, key) for key in USAGE_KEYS},
    }


SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"(?i)((?:api[_-]?key|access[_-]?token|bearer|authorization)\s*[:=]\s*)\S+"
    ),
    re.compile(r"(?<![0-9A-Za-z_-])sk-[0-9A-Za-z_-]{20,}(?![0-9A-Za-z_-])"),
)


def redact_secrets(text: str) -> str:
    for pattern in SECRET_PATTERNS:
        text = pattern.sub(
            lambda match: (match.group(1) + "[REDACTED]")
            if match.groups()
            else "[REDACTED]",
            text,
        )
    return text


def write_attempt_trace(
    trace_dir: Path, case_sha256: str, envelope: dict[str, Any]
) -> tuple[Path, str]:
    case_dir = trace_dir / case_sha256
    case_dir.mkdir(parents=True, exist_ok=True)
    for attempt in range(1, 1000):
        path = case_dir / f"{attempt:03d}.json"
        if not path.exists():
            content = redact_secrets(pretty_json(envelope))
            atomic_write(path, content)
            return path, sha256_text(content)
    raise CodexAdapterError(f"Too many trace attempts for {case_sha256}")


def detect_cli_version(
    codex_command: str, *, runner: ProcessRunner = subprocess.run
) -> str:
    try:
        process = runner(  # noqa: S603 - argv list, shell=False
            [codex_command, "--version"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise CodexAdapterError(f"Cannot execute Codex CLI: {exc}") from exc
    detail = f"{process.stdout}\n{process.stderr}".strip()
    if process.returncode != 0:
        raise CodexAdapterError(f"`{codex_command} --version` failed: {detail[:500]}")
    match = CLI_VERSION_PATTERN.search(detail)
    if match is None:
        raise CodexAdapterError(f"Unrecognized Codex CLI version: {detail[:500]}")
    return match.group(1)


def auth_available(
    codex_command: str, *, runner: ProcessRunner = subprocess.run
) -> bool:
    try:
        process = runner(  # noqa: S603 - argv list, shell=False
            [codex_command, "login", "status"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return process.returncode == 0


def judge_one(
    *,
    case: dict[str, Any],
    response: dict[str, Any],
    model: str,
    runtime_version: str,
    reasoning_effort: str,
    codex_command: str,
    timeout_seconds: int,
    trace_dir: Path,
    runner: ProcessRunner = subprocess.run,
) -> dict[str, Any]:
    """Make one non-retrying Codex invocation and preserve its complete evidence."""
    prompt = f"{SYSTEM_INSTRUCTION}\n\n{judgment_prompt(case, response)}"
    latency_ms = 0
    raw_stdout = ""
    raw_stderr = ""
    with tempfile.TemporaryDirectory(prefix="geoai-codex-judge-") as temporary:
        workspace = Path(temporary)
        schema_path = workspace / "schema.json"
        output_path = workspace / "judgment.json"
        atomic_write(schema_path, pretty_json(judgment_schema(case)))
        command = build_command(
            codex_command=codex_command,
            model=model,
            reasoning_effort=reasoning_effort,
            workspace=workspace,
            schema_path=schema_path,
            output_path=output_path,
        )
        started = time.monotonic()
        try:
            process = runner(  # noqa: S603 - fixed flags, validated model, shell=False
                command,
                input=prompt,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            latency_ms = round((time.monotonic() - started) * 1000)
            raw_stdout = str(exc.stdout or "")
            raw_stderr = str(exc.stderr or "")
            write_attempt_trace(
                trace_dir,
                case["case_sha256"],
                {
                    "ok": False,
                    "latency_ms": latency_ms,
                    "runtime_version": runtime_version,
                    "requested_model": model,
                    "reasoning_effort": reasoning_effort,
                    "adapter_error": f"Codex timed out after {timeout_seconds}s",
                    "stdout": raw_stdout,
                    "stderr": raw_stderr,
                },
            )
            raise CodexAdapterError(
                f"Codex timed out after {timeout_seconds}s"
            ) from exc
        except FileNotFoundError as exc:
            raise CodexAdapterError(f"Cannot execute Codex CLI: {exc}") from exc

        latency_ms = round((time.monotonic() - started) * 1000)
        raw_stdout = process.stdout
        raw_stderr = process.stderr
        try:
            if process.returncode != 0:
                raise CodexAdapterError(
                    f"Codex CLI exited {process.returncode}: {raw_stderr[:500]}"
                )
            parsed_trace = parse_jsonl_trace(raw_stdout)
            if not output_path.exists():
                raise CodexAdapterError("Codex omitted --output-last-message file")
            try:
                parsed_output = json.loads(
                    output_path.read_text(encoding="utf-8-sig")
                )
            except json.JSONDecodeError as exc:
                raise CodexAdapterError(
                    f"Codex structured output is invalid JSON: {exc}"
                ) from exc
            judgment = restore_judgment(case, parsed_output)
            _, trace_sha256 = write_attempt_trace(
                trace_dir,
                case["case_sha256"],
                {
                    "ok": True,
                    "latency_ms": latency_ms,
                    "runtime_version": runtime_version,
                    "requested_model": model,
                    "reasoning_effort": reasoning_effort,
                    "thread_id": parsed_trace["thread_id"],
                    "usage": parsed_trace["usage"],
                    "events": parsed_trace["events"],
                    "stderr": raw_stderr,
                    "structured_output": parsed_output,
                },
            )
        except (CodexAdapterError, EvalRunnerError) as exc:
            write_attempt_trace(
                trace_dir,
                case["case_sha256"],
                {
                    "ok": False,
                    "latency_ms": latency_ms,
                    "runtime_version": runtime_version,
                    "requested_model": model,
                    "reasoning_effort": reasoning_effort,
                    "adapter_error": str(exc)[:2000],
                    "stdout": raw_stdout,
                    "stderr": raw_stderr,
                    "structured_output": (
                        output_path.read_text(encoding="utf-8-sig")
                        if output_path.exists()
                        else None
                    ),
                },
            )
            raise

    judgment.update(
        {
            "_requested_model": model,
            "_runtime_version": runtime_version,
            "_reasoning_effort": reasoning_effort,
            "_provider_reported_model": None,
            "_prompt_version": PROMPT_VERSION,
            "_latency_ms": latency_ms,
            "_usage": parsed_trace["usage"],
            "_thread_id": parsed_trace["thread_id"],
            "_trace_sha256": trace_sha256,
        }
    )
    return judgment


def validate_checkpoint(
    *,
    completed: dict[str, dict[str, Any]],
    cases: list[dict[str, Any]],
    run_schema: dict[str, Any],
    requested_model: str,
    runtime_version: str,
    reasoning_effort: str,
) -> None:
    case_by_id = {case["case_id"]: case for case in cases}
    unknown = set(completed) - set(case_by_id)
    if unknown:
        raise CodexAdapterError("Checkpoint contains cases outside this manifest")
    validator = contract_validator(run_schema, "judgment")
    for case_id, row in completed.items():
        validate_instance(
            validator, clean_judgment(row), label=f"checkpoint[{case_id}]"
        )
        expected_metadata = {
            "_requested_model": requested_model,
            "_runtime_version": runtime_version,
            "_reasoning_effort": reasoning_effort,
            "_prompt_version": PROMPT_VERSION,
        }
        for key, expected_value in expected_metadata.items():
            if row.get(key) != expected_value:
                raise CodexAdapterError(
                    f"Checkpoint {case_id} has different {key.removeprefix('_')}"
                )
        expected = [item["criterion"] for item in row["expected_behavior"]]
        forbidden = [item["criterion"] for item in row["forbidden_behavior"]]
        if expected != case_by_id[case_id]["expected_behavior"]:
            raise CodexAdapterError(f"Checkpoint {case_id} expected criteria drift")
        if forbidden != case_by_id[case_id]["forbidden_behavior"]:
            raise CodexAdapterError(f"Checkpoint {case_id} forbidden criteria drift")


def trace_counts(trace_dir: Path) -> tuple[int, int]:
    successes = 0
    failures = 0
    if not trace_dir.exists():
        return successes, failures
    for path in trace_dir.glob("*/*.json"):
        envelope = load_json(path)
        if envelope.get("ok") is True:
            successes += 1
        else:
            failures += 1
    return successes, failures


def judge_run(args: argparse.Namespace) -> Path:
    run_dir = args.run_dir.resolve()
    manifest, run_schema = load_manifest(run_dir)
    if manifest.get("evaluation_scope", "all") == "routing":
        raise CodexAdapterError(
            "Routing-only manifests do not require criterion judging"
        )
    cases = [
        case
        for case in manifest["cases"]
        if case.get("behavior_class", "advisory") != "routing-only"
    ]
    if not cases:
        raise CodexAdapterError("Manifest has no behavior-evaluable cases")
    responses = {
        row["case_id"]: row
        for row in load_jsonl(run_dir / "raw" / "responses.jsonl")
    }
    if set(responses) != {case["case_id"] for case in cases}:
        raise CodexAdapterError(
            "Ingested raw responses do not exactly match the manifest"
        )
    selected_cases = select_cases(cases, args.case_id)
    codex_command = resolve_codex_command(args.codex_command)
    runtime_version = detect_cli_version(codex_command)
    namespace = judge_namespace(
        args.judge_model, runtime_version, args.reasoning_effort
    )
    adapter_dir = run_dir / "adapter" / namespace
    partial_path = adapter_dir / "judgments.partial.jsonl"
    output_path = adapter_dir / "judgments.json"
    completed = read_partial_rows(partial_path)
    validate_checkpoint(
        completed=completed,
        cases=cases,
        run_schema=run_schema,
        requested_model=args.judge_model,
        runtime_version=runtime_version,
        reasoning_effort=args.reasoning_effort,
    )
    pending = [case for case in selected_cases if case["case_id"] not in completed]
    if args.dry_run:
        print(
            json.dumps(
                {
                    "provider": "openai-codex-cli",
                    "codex_command": codex_command,
                    "runtime_version": runtime_version,
                    "requested_model": args.judge_model,
                    "provider_reported_model": None,
                    "reasoning_effort": args.reasoning_effort,
                    "prompt_version": PROMPT_VERSION,
                    "max_requests": args.max_requests,
                    "automatic_retries": 0,
                    "sandbox": "read-only",
                    "ephemeral": True,
                    "pending_case_ids": [case["case_id"] for case in pending],
                },
                ensure_ascii=False,
            )
        )
        return output_path
    if not args.acknowledge_external_data_use:
        raise CodexAdapterError(
            "Refusing external model calls without --acknowledge-external-data-use; "
            "send only public or explicitly approved benchmark data"
        )
    if not auth_available(codex_command):
        raise CodexAdapterError(
            f"`{codex_command} login status` did not confirm authentication"
        )
    if len(pending) > args.max_requests:
        raise CodexAdapterError(
            f"Pending cases ({len(pending)}) exceed invocation request cap "
            f"({args.max_requests})"
        )

    trace_dir = adapter_dir / "traces"
    for case in pending:
        judgment = judge_one(
            case=case,
            response=responses[case["case_id"]],
            model=args.judge_model,
            runtime_version=runtime_version,
            reasoning_effort=args.reasoning_effort,
            codex_command=codex_command,
            timeout_seconds=args.timeout_seconds,
            trace_dir=trace_dir,
        )
        completed[case["case_id"]] = judgment
        ordered = [
            completed[item["case_id"]]
            for item in cases
            if item["case_id"] in completed
        ]
        atomic_write(partial_path, jsonl_text(ordered))
        print(f"judgments {len(completed)}/{len(cases)}", file=sys.stderr)

    if args.case_id:
        return partial_path
    if len(completed) != len(cases):
        raise CodexAdapterError(
            f"Incomplete judging: {len(completed)}/{len(cases)} judgments"
        )
    final_judgments = [clean_judgment(completed[case["case_id"]]) for case in cases]
    judgment_set = {
        "schema_version": 1,
        "suite_sha256": manifest["suite_sha256"],
        "judge": {
            "kind": "model",
            "name": "openai-codex-cli",
            "version": f"{args.judge_model} via codex-cli {runtime_version}",
        },
        "judgments": final_judgments,
    }
    validate_instance(
        contract_validator(run_schema, "judgmentSet"),
        judgment_set,
        label="judgments",
    )
    atomic_write(output_path, pretty_json(judgment_set))
    usage = {
        key: sum(int(row.get("_usage", {}).get(key, 0)) for row in completed.values())
        for key in USAGE_KEYS
    }
    successful_requests, failed_requests = trace_counts(trace_dir)
    metrics = {
        "adapter_version": ADAPTER_VERSION,
        "provider": "openai-codex-cli",
        "codex_command": codex_command,
        "runtime_version": runtime_version,
        "requested_model": args.judge_model,
        "provider_reported_model": None,
        "model_identity_basis": (
            "requested CLI model; the documented Codex JSONL stream does not "
            "report a resolved provider model version"
        ),
        "reasoning_effort": args.reasoning_effort,
        "prompt_version": PROMPT_VERSION,
        "cases": len(cases),
        "requests_recorded": successful_requests + failed_requests,
        "successful_requests": successful_requests,
        "failed_requests": failed_requests,
        "automatic_retries": 0,
        "billing_mode": "chatgpt-subscription",
        "provider_cost_usd": None,
        "usage": usage,
    }
    atomic_write(adapter_dir / "metrics.json", pretty_json(metrics))
    return output_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    judge = subparsers.add_parser(
        "judge", help="Judge cached responses criterion by criterion"
    )
    judge.add_argument("--run-dir", type=Path, required=True)
    judge.add_argument("--judge-model", required=True)
    judge.add_argument("--reasoning-effort", choices=REASONING_EFFORTS, default="low")
    judge.add_argument("--codex-command", default="codex")
    judge.add_argument("--max-requests", type=int, required=True)
    judge.add_argument("--timeout-seconds", type=int, default=300)
    judge.add_argument("--case-id", action="append")
    judge.add_argument("--dry-run", action="store_true")
    judge.add_argument("--acknowledge-external-data-use", action="store_true")
    return parser


def validate_args(args: argparse.Namespace) -> None:
    if not MODEL_PATTERN.fullmatch(args.judge_model):
        raise CodexAdapterError("judge-model contains unsafe characters")
    if args.reasoning_effort not in REASONING_EFFORTS:
        raise CodexAdapterError("reasoning-effort is unsupported")
    if args.max_requests < 1:
        raise CodexAdapterError("max-requests must be positive")
    if args.timeout_seconds < 1:
        raise CodexAdapterError("timeout-seconds must be positive")
    if not args.codex_command.strip():
        raise CodexAdapterError("codex-command must not be empty")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        validate_args(args)
        output = judge_run(args)
    except (CodexAdapterError, EvalRunnerError, OSError) as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
