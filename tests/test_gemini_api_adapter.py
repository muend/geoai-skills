from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pytest

from tools.adapters.gemini_api import (
    GeminiAdapterError,
    build_request_body,
    judge_namespace,
    judge_one,
    parse_generate_response,
    post_generate_content,
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


def provider_payload() -> dict[str, Any]:
    result = {
        "expected": [
            {"met": True, "evidence": "Calls EPSG:4326 angular."},
            {"met": True, "evidence": "Requires an equal-area CRS."},
        ],
        "forbidden": [{"observed": False, "evidence": "No square-degree result."}],
        "critical_failure": False,
        "notes": "",
    }
    return {
        "candidates": [
            {
                "content": {"parts": [{"text": json.dumps(result)}]},
                "finishReason": "STOP",
            }
        ],
        "usageMetadata": {
            "promptTokenCount": 120,
            "candidatesTokenCount": 40,
            "thoughtsTokenCount": 10,
            "totalTokenCount": 170,
        },
        "modelVersion": "gemini-3.1-flash-lite",
        "responseId": "response-1",
    }


class FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def test_request_body_uses_strict_positional_json_schema() -> None:
    body = build_request_body(sample_case(), sample_response(), max_output_tokens=512)

    config = body["generationConfig"]
    assert config["responseMimeType"] == "application/json"
    assert config["temperature"] == 0
    assert config["responseJsonSchema"]["properties"]["expected"]["minItems"] == 2
    assert config["responseJsonSchema"]["properties"]["forbidden"]["maxItems"] == 1
    assert '"interaction_mode": "deliver"' in body["contents"][0]["parts"][0]["text"]
    assert "api" not in json.dumps(body).lower()


def test_judge_namespace_separates_model_and_prompt_versions() -> None:
    assert judge_namespace("gemini-3.1-flash-lite") == (
        "gemini-api--gemini-3-1-flash-lite--geoai-behavior-judge-v3"
    )


@pytest.mark.parametrize(
    ("mode", "policy_fragment"),
    [
        ("clarify", "may stop after asking the necessary questions"),
        ("deliver", "provide the requested analysis, plan, code, or decision now"),
        ("clarify_then_provisional", "provide a useful bounded provisional plan"),
    ],
)
def test_judge_request_encodes_frozen_interaction_policy(
    mode: str, policy_fragment: str
) -> None:
    case = sample_case()
    case["interaction_mode"] = mode

    body = build_request_body(case, sample_response(), max_output_tokens=512)
    judge_payload = body["contents"][0]["parts"][0]["text"]

    assert f'"interaction_mode": "{mode}"' in judge_payload
    assert policy_fragment in judge_payload


def test_parse_generate_response_preserves_usage_and_model_version() -> None:
    parsed, metadata = parse_generate_response(provider_payload())

    assert parsed["expected"][0]["met"] is True
    assert metadata["model_version"] == "gemini-3.1-flash-lite"
    assert metadata["usage"] == {
        "prompt_tokens": 120,
        "output_tokens": 40,
        "thought_tokens": 10,
        "total_tokens": 170,
    }


@pytest.mark.parametrize("finish_reason", ["MAX_TOKENS", "SAFETY", None])
def test_parse_generate_response_fails_closed_on_unclean_finish(
    finish_reason: str | None,
) -> None:
    payload = provider_payload()
    payload["candidates"][0]["finishReason"] = finish_reason

    with pytest.raises(GeminiAdapterError, match="did not finish cleanly"):
        parse_generate_response(payload)


def test_post_generate_content_keeps_key_out_of_url_and_body() -> None:
    captured: dict[str, Any] = {}

    def opener(request: Any, *, timeout: int) -> FakeResponse:
        captured["url"] = request.full_url
        captured["key"] = request.get_header("X-goog-api-key")
        captured["body"] = request.data.decode("utf-8")
        captured["timeout"] = timeout
        return FakeResponse(provider_payload())

    payload, _ = post_generate_content(
        model="gemini-3.1-flash-lite",
        api_key="secret-test-key",
        body={"contents": []},
        timeout_seconds=30,
        opener=opener,
    )

    assert payload["responseId"] == "response-1"
    assert captured["key"] == "secret-test-key"
    assert "secret-test-key" not in captured["url"]
    assert "secret-test-key" not in captured["body"]
    assert captured["timeout"] == 30


def test_judge_one_restores_exact_criteria_and_writes_local_trace(
    tmp_path: Path,
) -> None:
    def opener(request: Any, *, timeout: int) -> FakeResponse:
        assert request.get_header("X-goog-api-key") == "secret-test-key"
        assert timeout == 30
        return FakeResponse(provider_payload())

    judgment = judge_one(
        case=sample_case(),
        response=sample_response(),
        model="gemini-3.1-flash-lite",
        api_key="secret-test-key",
        max_output_tokens=512,
        timeout_seconds=30,
        trace_dir=tmp_path / "traces",
        opener=opener,
    )

    assert [
        item["criterion"] for item in judgment["expected_behavior"]
    ] == sample_case()["expected_behavior"]
    assert judgment["_model_version"] == "gemini-3.1-flash-lite"
    assert judgment["_usage"]["total_tokens"] == 170
    trace_files = list((tmp_path / "traces").glob("*/*.json"))
    assert len(trace_files) == 1
    assert "secret-test-key" not in trace_files[0].read_text(encoding="utf-8")


def test_judge_one_records_unclean_provider_attempt_before_failing(
    tmp_path: Path,
) -> None:
    payload = provider_payload()
    payload["candidates"][0]["finishReason"] = "MAX_TOKENS"

    def opener(request: Any, *, timeout: int) -> FakeResponse:
        return FakeResponse(payload)

    with pytest.raises(GeminiAdapterError, match="did not finish cleanly"):
        judge_one(
            case=sample_case(),
            response=sample_response(),
            model="gemini-3.1-flash-lite",
            api_key="secret-test-key",
            max_output_tokens=512,
            timeout_seconds=30,
            trace_dir=tmp_path / "traces",
            opener=opener,
        )

    trace_files = list((tmp_path / "traces").glob("*/*.json"))
    assert len(trace_files) == 1
    trace = json.loads(trace_files[0].read_text(encoding="utf-8"))
    assert trace["ok"] is False
    assert trace["provider_response"]["candidates"][0]["finishReason"] == "MAX_TOKENS"


def test_validate_args_rejects_unsafe_model_and_invalid_caps() -> None:
    args = argparse.Namespace(
        judge_model="../../unsafe",
        requests_per_minute=15.0,
        max_requests=5,
        timeout_seconds=180,
        max_output_tokens=2048,
        api_key_env="GEMINI_API_KEY",
    )
    with pytest.raises(GeminiAdapterError, match="unsafe characters"):
        validate_args(args)

    args.judge_model = "gemini-3.1-flash-lite"
    args.max_requests = 0
    with pytest.raises(GeminiAdapterError, match="max-requests"):
        validate_args(args)
