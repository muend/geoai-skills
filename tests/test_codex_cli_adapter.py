from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tools.adapters.codex_cli import (
    CodexAdapterError,
    auth_available,
    build_command,
    detect_cli_version,
    judge_namespace,
    judge_one,
    parse_jsonl_trace,
    resolve_codex_command,
    validate_args,
)


def sample_case() -> dict[str, Any]:
    return {
        "case_id": "sample-skill/safe-crs",
        "case_sha256": "a" * 64,
        "prompt": "Compute area from EPSG:4326 parcels.",
        "behavior_class": "advisory",
        "interaction_mode": "deliver",
        "critical": True,
        "expected_behavior": [
            "Rejects direct area computation in angular coordinates",
            "Selects a suitable projected or geodesic method",
        ],
        "forbidden_behavior": ["Must not report square degrees as area"],
        "fixtures": [],
        "expected_artifacts": [],
    }


def sample_response() -> dict[str, Any]:
    return {
        "case_id": "sample-skill/safe-crs",
        "response": "EPSG:4326 is angular. Reproject to a suitable equal-area CRS first.",
        "artifacts": [],
    }


def structured_judgment() -> dict[str, Any]:
    return {
        "expected_clauses": [
            {"met": True, "evidence": "Calls EPSG:4326 angular."},
            {"met": True, "evidence": "Requires an equal-area CRS."},
        ],
        "forbidden_clauses": [
            {"observed": False, "evidence": "No square-degree result."}
        ],
        "critical_failure": False,
        "notes": "",
    }


def successful_trace() -> str:
    events = [
        {"type": "thread.started", "thread_id": "thread-1"},
        {"type": "turn.started"},
        {
            "type": "item.completed",
            "item": {
                "id": "item-1",
                "type": "agent_message",
                "text": json.dumps(structured_judgment()),
            },
        },
        {
            "type": "turn.completed",
            "usage": {
                "input_tokens": 120,
                "cached_input_tokens": 20,
                "output_tokens": 40,
                "reasoning_output_tokens": 10,
            },
        },
    ]
    return "".join(json.dumps(event) + "\n" for event in events)


def test_build_command_is_ephemeral_read_only_and_keeps_prompt_off_argv(
    tmp_path: Path,
) -> None:
    command = build_command(
        codex_command="codex",
        model="gpt-5.6",
        reasoning_effort="low",
        workspace=tmp_path,
        schema_path=tmp_path / "schema.json",
        output_path=tmp_path / "output.json",
    )

    assert command[:2] == ["codex", "exec"]
    assert "--json" in command
    assert "--ephemeral" in command
    assert "--ignore-user-config" in command
    assert command[command.index("--sandbox") + 1] == "read-only"
    assert command[command.index("--model") + 1] == "gpt-5.6"
    assert 'model_reasoning_effort="low"' in command
    assert command[-1] == "-"
    assert sample_case()["prompt"] not in " ".join(command)


def test_judge_namespace_separates_runtime_model_effort_and_prompt() -> None:
    assert judge_namespace("gpt-5.6", "0.145.0", "low") == (
        "codex-cli-0-145-0--gpt-5-6--reasoning-low--"
        "geoai-behavior-judge-v6"
    )


def test_resolve_codex_command_prefers_npm_cmd_on_windows() -> None:
    paths = {
        "codex.cmd": r"C:\Users\tester\AppData\Roaming\npm\codex.cmd",
        "codex": r"C:\Program Files\WindowsApps\OpenAI.Codex\codex.exe",
    }

    resolved = resolve_codex_command(
        "codex",
        platform_name="nt",
        which=lambda candidate: paths.get(candidate),
    )

    assert resolved == paths["codex.cmd"]


def test_parse_jsonl_trace_preserves_usage_and_thread() -> None:
    parsed = parse_jsonl_trace(successful_trace())

    assert parsed["thread_id"] == "thread-1"
    assert parsed["usage"] == {
        "input_tokens": 120,
        "cached_input_tokens": 20,
        "output_tokens": 40,
        "reasoning_output_tokens": 10,
    }


@pytest.mark.parametrize(
    "event",
    [
        {
            "type": "item.completed",
            "item": {"id": "tool-1", "type": "command_execution"},
        },
        {"type": "turn.failed", "error": {"message": "provider error"}},
        {"type": "error", "message": "stream error"},
    ],
)
def test_parse_jsonl_trace_fails_closed_on_tools_or_failures(
    event: dict[str, Any],
) -> None:
    trace = successful_trace() + json.dumps(event) + "\n"

    match = "prohibited tools" if event["type"] == "item.completed" else "failure"
    with pytest.raises(CodexAdapterError, match=match):
        parse_jsonl_trace(trace)


def test_judge_one_restores_criteria_and_records_auditable_trace(
    tmp_path: Path,
) -> None:
    captured: dict[str, Any] = {}

    def runner(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured["command"] = command
        captured["input"] = kwargs["input"]
        output_path = Path(command[command.index("--output-last-message") + 1])
        output_path.write_text(
            json.dumps(structured_judgment()), encoding="utf-8"
        )
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout=successful_trace(),
            stderr="",
        )

    judgment = judge_one(
        case=sample_case(),
        response=sample_response(),
        model="gpt-5.6",
        runtime_version="0.145.0",
        reasoning_effort="low",
        codex_command="codex",
        timeout_seconds=30,
        trace_dir=tmp_path / "traces",
        runner=runner,
    )

    assert [
        item["criterion"] for item in judgment["expected_behavior"]
    ] == sample_case()["expected_behavior"]
    assert judgment["_runtime_version"] == "0.145.0"
    assert judgment["_provider_reported_model"] is None
    assert judgment["_usage"]["output_tokens"] == 40
    assert '"interaction_mode": "deliver"' in captured["input"]
    assert sample_case()["prompt"] not in " ".join(captured["command"])
    trace_files = list((tmp_path / "traces").glob("*/*.json"))
    assert len(trace_files) == 1
    trace = json.loads(trace_files[0].read_text(encoding="utf-8"))
    assert trace["ok"] is True
    assert trace["requested_model"] == "gpt-5.6"


def test_judge_one_records_failed_tool_using_attempt(tmp_path: Path) -> None:
    trace_events = [
        {"type": "thread.started", "thread_id": "thread-1"},
        {"type": "turn.started"},
        {
            "type": "item.completed",
            "item": {"id": "tool-1", "type": "web_search"},
        },
        {
            "type": "turn.completed",
            "usage": {
                "input_tokens": 10,
                "cached_input_tokens": 0,
                "output_tokens": 2,
                "reasoning_output_tokens": 0,
            },
        },
    ]

    def runner(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        output_path = Path(command[command.index("--output-last-message") + 1])
        output_path.write_text(
            json.dumps(structured_judgment()), encoding="utf-8"
        )
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout="".join(json.dumps(event) + "\n" for event in trace_events),
            stderr="",
        )

    with pytest.raises(CodexAdapterError, match="prohibited tools"):
        judge_one(
            case=sample_case(),
            response=sample_response(),
            model="gpt-5.6",
            runtime_version="0.145.0",
            reasoning_effort="low",
            codex_command="codex",
            timeout_seconds=30,
            trace_dir=tmp_path / "traces",
            runner=runner,
        )

    trace_files = list((tmp_path / "traces").glob("*/*.json"))
    assert len(trace_files) == 1
    trace = json.loads(trace_files[0].read_text(encoding="utf-8"))
    assert trace["ok"] is False
    assert "prohibited tools" in trace["adapter_error"]


def test_cli_version_and_auth_checks_use_non_model_commands() -> None:
    calls: list[list[str]] = []

    def runner(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        output = (
            "codex-cli 0.145.0"
            if command[-1] == "--version"
            else "Logged in using ChatGPT"
        )
        return subprocess.CompletedProcess(
            args=command, returncode=0, stdout=output, stderr=""
        )

    assert detect_cli_version("codex", runner=runner) == "0.145.0"
    assert auth_available("codex", runner=runner) is True
    assert calls == [["codex", "--version"], ["codex", "login", "status"]]


def test_validate_args_rejects_unsafe_model_and_invalid_caps() -> None:
    args = argparse.Namespace(
        judge_model="../../unsafe",
        reasoning_effort="low",
        max_requests=5,
        timeout_seconds=300,
        codex_command="codex",
    )
    with pytest.raises(CodexAdapterError, match="unsafe characters"):
        validate_args(args)

    args.judge_model = "gpt-5.6"
    args.max_requests = 0
    with pytest.raises(CodexAdapterError, match="max-requests"):
        validate_args(args)
