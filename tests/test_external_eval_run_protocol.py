"""Tests for the frozen external-suite run and result protocol."""

from __future__ import annotations

import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parent.parent
SUITE = ROOT / "evals" / "external" / "geoanalystbench"
CASES = SUITE / "cases"
TOOL = ROOT / "tools" / "evaluate_external_run.py"
TEMPLATE = SUITE / "run-template.json"
RUN_SCHEMA = SUITE / "run-schema.json"
RESULT_SCHEMA = SUITE / "result-schema.json"
MINIMAX_PROFILE = SUITE / "MINIMAX-CODE.md"
EXPECTED_CASE_IDS = [
    "gab-01-urban-heat",
    "gab-08-facility-coverage",
    "gab-36-vegetation-change",
    "gab-38-travel-time",
    "gab-39-spatial-regression",
]


def read_json(path: Path) -> Any:
    """Read one UTF-8 JSON document."""
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    """Write deterministic UTF-8 JSON for a test manifest."""
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def valid_manifest() -> dict[str, Any]:
    """Return the public template with every operator placeholder replaced."""
    payload = deepcopy(read_json(TEMPLATE))
    payload["run_id"] = "test-run-20260729"
    payload["runtime"] = {
        "provider": "example-provider",
        "product": "example-runtime",
        "product_version": "1.2.3",
        "model": "example-model",
        "model_version": "example-model-20260729",
    }
    payload["skill_package"] = {
        "source": "https://example.test/geoai-skills.zip",
        "version": "0.2.0",
        "revision": "471140b02e80459b45240b9f4c2039443054b8d2",
        "archive_sha256": "a" * 64,
    }
    payload["authorization"]["approved_by"] = "test-operator"
    return payload


def run_tool(*arguments: str) -> subprocess.CompletedProcess[str]:
    """Run the public protocol CLI."""
    return subprocess.run(  # noqa: S603 - repo-owned interpreter and script
        [sys.executable, str(TOOL), *arguments],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=180,
    )


def run_case_helper(script: Path, *arguments: str) -> None:
    """Run one frozen fixture or reference helper and require success."""
    result = subprocess.run(  # noqa: S603 - frozen repository script
        [sys.executable, str(script), *arguments],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
    )
    assert result.returncode == 0, result.stderr


def populate_reference_evidence(base: Path, payload: dict[str, Any]) -> None:
    """Create valid local evidence without making a model or network call."""
    for entry in payload["cases"]:
        case_id = entry["case_id"]
        case_dir = CASES / case_id
        contract = read_json(case_dir / "case.json")
        fixture_dir = base / ".fixtures" / case_id
        run_case_helper(
            case_dir / contract["fixture_generator"],
            "--output-dir",
            str(fixture_dir),
        )
        input_path = fixture_dir / Path(contract["input_paths"][0]).name
        output_dir = base / entry["artifact_dir"]
        run_case_helper(
            case_dir / contract["reference"],
            "--input",
            str(input_path),
            "--output-dir",
            str(output_dir),
        )
        response_path = base / entry["response_path"]
        response_path.parent.mkdir(parents=True, exist_ok=True)
        response_path.write_text(
            f"Offline protocol fixture for {case_id}.\n",
            encoding="utf-8",
            newline="\n",
        )


def test_public_schemas_and_template_are_valid() -> None:
    """Committed protocol documents must remain valid JSON Schema artifacts."""
    run_schema = read_json(RUN_SCHEMA)
    result_schema = read_json(RESULT_SCHEMA)
    Draft202012Validator.check_schema(run_schema)
    Draft202012Validator.check_schema(result_schema)
    errors = list(
        Draft202012Validator(
            run_schema,
            format_checker=FormatChecker(),
        ).iter_errors(read_json(TEMPLATE))
    )
    assert errors == []
    assert [case["case_id"] for case in read_json(TEMPLATE)["cases"]] == EXPECTED_CASE_IDS


def test_template_fails_closed_until_operator_metadata_is_replaced(
    tmp_path: Path,
) -> None:
    """A copied but unedited template must never pass the call preflight."""
    manifest = tmp_path / "run.json"
    manifest.write_bytes(TEMPLATE.read_bytes())
    result = run_tool("--manifest", str(manifest), "--dry-run")
    assert result.returncode == 1
    assert "replace every replace-before-run placeholder" in result.stderr
    assert "archive_sha256 must record the installed archive" in result.stderr


def test_dry_run_validates_budget_and_call_gates_without_outputs(
    tmp_path: Path,
) -> None:
    """Preflight succeeds before evidence exists and explicitly makes no calls."""
    manifest = tmp_path / "run.json"
    write_json(manifest, valid_manifest())
    result = run_tool("--manifest", str(manifest), "--dry-run")
    assert result.returncode == 0, result.stderr
    assert "5 cases, 5 calls max" in result.stdout
    assert "0 automatic retries" in result.stdout
    assert "no model, API, web, connector, or artifact validator was invoked" in (
        result.stdout
    )


def test_preflight_rejects_wrong_case_population_and_native_pooling(
    tmp_path: Path,
) -> None:
    """The five-case denominator and external-only boundary are fail-closed."""
    payload = valid_manifest()
    payload["cases"] = payload["cases"][:-1]
    payload["native_suite_included"] = True
    manifest = tmp_path / "run.json"
    write_json(manifest, payload)
    result = run_tool("--manifest", str(manifest), "--dry-run")
    assert result.returncode == 1
    assert "native_suite_included" in result.stderr
    assert "cases must exactly match the frozen five-case order" in result.stderr


def test_preflight_rejects_retry_or_call_budget_expansion(tmp_path: Path) -> None:
    """A run cannot silently exceed the declared one-call, zero-retry design."""
    payload = valid_manifest()
    payload["execution_policy"]["max_calls"] = 6
    payload["execution_policy"]["automatic_retries"] = 1
    manifest = tmp_path / "run.json"
    write_json(manifest, payload)
    result = run_tool("--manifest", str(manifest), "--dry-run")
    assert result.returncode == 1
    assert "max_calls" in result.stderr
    assert "automatic_retries" in result.stderr


def test_preflight_rejects_manifest_path_escape(tmp_path: Path) -> None:
    """Evidence paths may not leave the run manifest directory."""
    payload = valid_manifest()
    payload["cases"][0]["response_path"] = "../outside.md"
    manifest = tmp_path / "run.json"
    write_json(manifest, payload)
    result = run_tool("--manifest", str(manifest), "--dry-run")
    assert result.returncode == 1
    assert "response_path" in result.stderr


def test_offline_evaluator_records_passes_failures_and_hashes(
    tmp_path: Path,
) -> None:
    """Artifact failures are results, remain in the denominator, and stay separate."""
    payload = valid_manifest()
    populate_reference_evidence(tmp_path, payload)
    manifest = tmp_path / "run.json"
    result_path = tmp_path / "result.json"
    write_json(manifest, payload)

    completed = run_tool(
        "--manifest",
        str(manifest),
        "--result",
        str(result_path),
    )
    assert completed.returncode == 0, completed.stderr
    result = read_json(result_path)
    assert result["summary"] == {
        "failed_cases": 0,
        "pass_rate": 1.0,
        "passed_cases": 5,
        "total_cases": 5,
    }
    assert all(case["passed"] for case in result["cases"])
    assert all(case["response_sha256"] for case in result["cases"])
    assert result["native_suite_included"] is False
    assert "not pooled with the native 158-case suite" in result["claim_boundary"]
    assert (
        list(
            Draft202012Validator(
                read_json(RESULT_SCHEMA),
                format_checker=FormatChecker(),
            ).iter_errors(result)
        )
        == []
    )
    overwrite = run_tool(
        "--manifest",
        str(manifest),
        "--result",
        str(result_path),
    )
    assert overwrite.returncode == 1
    assert "refusing to overwrite" in overwrite.stderr

    missing = (
        tmp_path
        / payload["cases"][0]["artifact_dir"]
        / "temperature-surface.json"
    )
    missing.unlink()
    failed_result_path = tmp_path / "result-with-failure.json"
    measured = run_tool(
        "--manifest",
        str(manifest),
        "--result",
        str(failed_result_path),
    )
    assert measured.returncode == 0, measured.stderr
    failed_result = read_json(failed_result_path)
    assert failed_result["summary"]["passed_cases"] == 4
    assert failed_result["summary"]["failed_cases"] == 1
    first = failed_result["cases"][0]
    assert first["passed"] is False
    assert first["missing_artifacts"] == ["temperature-surface.json"]


def test_protocol_tool_contains_no_model_or_network_client() -> None:
    """The evaluator is an offline collector, not a hidden invocation adapter."""
    source = TOOL.read_text(encoding="utf-8")
    for forbidden in (
        "anthropic",
        "openai",
        "requests.",
        "urllib.request",
        "httpx",
        "reference.py",
    ):
        assert forbidden not in source.lower()


def test_minimax_profile_preserves_manual_and_external_boundaries() -> None:
    """MiniMax M3 is documented as a manual surface, not an inferred API adapter."""
    profile = MINIMAX_PROFILE.read_text(encoding="utf-8")
    required = (
        "manual evidence-producing surface",
        "automated API adapter",
        "MiniMax-M3",
        "product_version",
        "model_version",
        "revision",
        "archive_sha256",
        "platform-internal-not-observable",
        "automatic_retries: 0",
        "regenerate or retry",
        "native 158-case suite",
    )
    for phrase in required:
        assert phrase in profile
