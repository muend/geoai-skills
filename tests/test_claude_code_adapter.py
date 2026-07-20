from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tools.adapters.claude_code import (
    AdapterError,
    capture_artifacts,
    execute_one,
    execution_command,
    judgment_schema,
    load_manifest,
    parse_json_result,
    parse_stream_trace,
    select_cases,
    stage_case_workspace,
    stage_blind_plugin,
    verify_staged_fixtures,
)


def test_parse_stream_trace_captures_skill_tool_and_usage() -> None:
    events = [
        {"type": "system", "subtype": "init"},
        {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "name": "Skill",
                        "input": {"skill": "geoai:terrain-hydrology"},
                    }
                ]
            },
        },
        {
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "duration_ms": 1234,
            "total_cost_usd": 0.0125,
            "usage": {"input_tokens": 100, "output_tokens": 50},
            "result": "Use a projected CRS before deriving slope.",
        },
    ]
    parsed = parse_stream_trace(
        "".join(json.dumps(event) + "\n" for event in events),
        known_skills={"terrain-hydrology", "geo-data-engineering"},
    )

    assert parsed["activated_skills"] == ["terrain-hydrology"]
    assert parsed["response"] == "Use a projected CRS before deriving slope."
    assert parsed["latency_ms"] == 1234
    assert parsed["usage"] == {"input_tokens": 100, "output_tokens": 50}
    assert parsed["cost_usd"] == 0.0125
    assert parsed["error"] is None


def test_execute_one_preserves_error_trace_cost_and_activation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events = [
        {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "name": "Skill",
                        "input": {"skill": "geoai:terrain-hydrology"},
                    }
                ]
            },
        },
        {
            "type": "result",
            "subtype": "error_max_budget_usd",
            "is_error": True,
            "duration_ms": 2000,
            "total_cost_usd": 0.11002,
            "usage": {"input_tokens": 2, "output_tokens": 175},
            "result": "",
        },
    ]
    trace = "".join(json.dumps(event) + "\n" for event in events)
    process = subprocess.CompletedProcess(
        args=["claude"], returncode=1, stdout=trace, stderr=""
    )
    monkeypatch.setattr(
        "tools.adapters.claude_code.run_process", lambda *args, **kwargs: process
    )

    response = execute_one(
        request={"prompt": "Compute slope"},
        case={
            "case_id": "terrain-hydrology/slope-4326-catch",
            "case_sha256": "a" * 64,
        },
        manifest={
            "runtime": "claude-code-2.1.214",
            "model": "claude-sonnet-5",
            "condition": "skills-enabled",
            "cases": [{"skill": "terrain-hydrology"}],
        },
        command=["claude"],
        workspace=tmp_path,
        trace_dir=tmp_path / "traces",
        timeout_seconds=30,
    )

    assert response["activated_skills"] == ["terrain-hydrology"]
    assert response["cost_usd"] == pytest.approx(0.11002)
    assert response["usage"] == {"input_tokens": 2, "output_tokens": 175}
    assert response["error"] == "error_max_budget_usd; Claude Code exited with 1"


def test_execute_one_classifies_success_subtype_api_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events = [
        {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "name": "Skill",
                        "input": {"skill": "geoai:arcgis-pro-automation"},
                    }
                ]
            },
        },
        {
            "type": "result",
            "subtype": "success",
            "is_error": True,
            "terminal_reason": "api_error",
            "api_error_status": 429,
            "duration_ms": 1200,
            "total_cost_usd": 0.0,
            "usage": {"input_tokens": 0, "output_tokens": 0},
            "result": "You've hit your session limit",
        },
    ]
    process = subprocess.CompletedProcess(
        args=["claude"],
        returncode=1,
        stdout="".join(json.dumps(event) + "\n" for event in events),
        stderr="",
    )
    monkeypatch.setattr(
        "tools.adapters.claude_code.run_process", lambda *args, **kwargs: process
    )

    response = execute_one(
        request={"prompt": "Inspect this geodatabase"},
        case={"case_id": "arcgis-pro-automation/preflight", "case_sha256": "b" * 64},
        manifest={
            "runtime": "claude-code-2.1.214",
            "model": "claude-sonnet-5",
            "condition": "skills-enabled",
            "cases": [{"skill": "arcgis-pro-automation"}],
        },
        command=["claude"],
        workspace=tmp_path,
        trace_dir=tmp_path / "traces",
        timeout_seconds=30,
    )

    assert response["activated_skills"] == ["arcgis-pro-automation"]
    assert response["response"] == "You've hit your session limit"
    assert response["error"] == "api_error_http_429; Claude Code exited with 1"


def test_execution_commands_isolate_enabled_and_disabled_conditions(tmp_path: Path) -> None:
    enabled = execution_command(
        claude_command="claude",
        model="model-id",
        condition="skills-enabled",
        plugin_dir=tmp_path / "plugin",
        case_budget_usd=0.1,
        max_turns=4,
        tool_profile="read-only",
    )
    disabled = execution_command(
        claude_command="claude",
        model="model-id",
        condition="skills-disabled",
        plugin_dir=None,
        case_budget_usd=0.1,
        max_turns=4,
        tool_profile="read-only",
    )

    assert "--plugin-dir" in enabled
    assert "Skill,Read" in enabled
    assert "--setting-sources" in enabled
    assert "--safe-mode" not in enabled
    assert "Read" in disabled
    assert "Skill,Read" not in disabled
    assert "--setting-sources" in disabled
    assert "--safe-mode" not in disabled
    assert "--disable-slash-commands" not in disabled
    assert "--plugin-dir" not in disabled


def test_workspace_write_profile_preserves_non_skill_tool_parity(tmp_path: Path) -> None:
    enabled = execution_command(
        claude_command="claude",
        model="model-id",
        condition="skills-enabled",
        plugin_dir=tmp_path / "plugin",
        case_budget_usd=0.1,
        max_turns=4,
        tool_profile="workspace-write",
    )
    disabled = execution_command(
        claude_command="claude",
        model="model-id",
        condition="skills-disabled",
        plugin_dir=None,
        case_budget_usd=0.1,
        max_turns=4,
        tool_profile="workspace-write",
    )

    assert "Skill,Read,Write,Edit" in enabled
    assert "Read,Write,Edit" in disabled


def test_stage_workspace_verifies_fixture_and_captures_text_artifact(tmp_path: Path) -> None:
    fixture = tmp_path / "repo" / "skills" / "sample" / "evals" / "fixtures" / "input.txt"
    fixture.parent.mkdir(parents=True)
    fixture.write_text("fixture data", encoding="utf-8")
    import hashlib

    content = fixture.read_bytes()
    case = {
        "fixtures": [
            {
                "source_path": "skills/sample/evals/fixtures/input.txt",
                "workspace_path": "inputs/input.txt",
                "sha256": hashlib.sha256(content).hexdigest(),
                "size_bytes": len(content),
            }
        ],
        "expected_artifacts": [
            {"path": "outputs/result.json", "media_type": "application/json", "required": True}
        ],
    }
    workspace = tmp_path / "workspace"
    stage_case_workspace(case, workspace, repository_root=tmp_path / "repo")
    assert (workspace / "inputs" / "input.txt").read_text(encoding="utf-8") == "fixture data"

    output = workspace / "outputs" / "result.json"
    output.parent.mkdir(parents=True)
    output.write_text('{"ok":true}', encoding="utf-8")
    artifacts = capture_artifacts(case, workspace)

    assert artifacts[0]["path"] == "outputs/result.json"
    assert artifacts[0]["text_preview"] == '{"ok":true}'
    assert artifacts[0]["preview_truncated"] is False
    assert verify_staged_fixtures(case, workspace) == []

    (workspace / "inputs" / "input.txt").write_text("changed", encoding="utf-8")
    assert verify_staged_fixtures(case, workspace) == ["fixture modified: inputs/input.txt"]


def test_stage_workspace_rejects_hash_mismatch_and_path_escape(tmp_path: Path) -> None:
    fixture = tmp_path / "repo" / "fixture.txt"
    fixture.parent.mkdir()
    fixture.write_text("data", encoding="utf-8")
    bad_hash = {
        "fixtures": [
            {
                "source_path": "fixture.txt",
                "workspace_path": "input.txt",
                "sha256": "0" * 64,
                "size_bytes": 4,
            }
        ]
    }
    with pytest.raises(AdapterError, match="hash mismatch"):
        stage_case_workspace(bad_hash, tmp_path / "bad-hash", repository_root=tmp_path / "repo")

    escaping = {
        "fixtures": [
            {
                "source_path": "fixture.txt",
                "workspace_path": "../escape.txt",
                "sha256": __import__("hashlib").sha256(b"data").hexdigest(),
                "size_bytes": 4,
            }
        ]
    }
    with pytest.raises(AdapterError, match="escapes case root"):
        stage_case_workspace(escaping, tmp_path / "escape", repository_root=tmp_path / "repo")


def test_blind_plugin_excludes_eval_labels(tmp_path: Path) -> None:
    source = tmp_path / "source"
    (source / ".claude-plugin").mkdir(parents=True)
    (source / ".claude-plugin" / "plugin.json").write_text("{}", encoding="utf-8")
    skill = source / "skills" / "sample-skill"
    (skill / "evals").mkdir(parents=True)
    (skill / "SKILL.md").write_text("skill instructions", encoding="utf-8")
    (skill / "evals" / "evals.json").write_text("secret rubric", encoding="utf-8")

    destination = stage_blind_plugin(source, tmp_path / "blind")

    assert (destination / "skills" / "sample-skill" / "SKILL.md").exists()
    assert not (destination / "skills" / "sample-skill" / "evals").exists()


def test_judgment_schema_locks_criterion_counts() -> None:
    schema = judgment_schema(
        {
            "expected_behavior": ["criterion one", "criterion two"],
            "forbidden_behavior": ["forbidden one"],
        }
    )

    assert schema["properties"]["expected"]["minItems"] == 2
    assert schema["properties"]["expected"]["maxItems"] == 2
    assert schema["properties"]["forbidden"]["minItems"] == 1
    assert schema["properties"]["forbidden"]["maxItems"] == 1


def test_parse_json_result_accepts_structured_result_string() -> None:
    output = json.dumps(
        {
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "total_cost_usd": 0.02,
            "result": json.dumps(
                {
                    "expected": [{"met": True, "evidence": "present"}],
                    "forbidden": [],
                    "critical_failure": False,
                    "notes": "",
                }
            ),
        }
    )

    parsed, metadata = parse_json_result(output)

    assert parsed["expected"][0]["met"] is True
    assert metadata["total_cost_usd"] == 0.02


def test_select_cases_preserves_manifest_order_and_rejects_unknown() -> None:
    cases = [{"case_id": "skill/a"}, {"case_id": "skill/b"}, {"case_id": "skill/c"}]

    assert select_cases(cases, ["skill/c", "skill/a"]) == [cases[0], cases[2]]

    with pytest.raises(AdapterError, match="Unknown requested case ids"):
        select_cases(cases, ["skill/missing"])


def test_old_manifest_without_behavior_fields_remains_valid(tmp_path: Path) -> None:
    from tools.eval_runner import prepare_run

    run_dir = prepare_run(
        runtime="test-runtime",
        model="test-model",
        condition="skills-enabled",
        runs_dir=tmp_path / "runs",
    )
    manifest_path = run_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for case in manifest["cases"]:
        for field in ("behavior_class", "tool_profile", "fixtures", "expected_artifacts"):
            case.pop(field)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    loaded, _ = load_manifest(run_dir)

    assert "behavior_class" not in loaded["cases"][0]
