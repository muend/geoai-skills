#!/usr/bin/env python3
"""Judge cached GeoAI behavior responses through the Google Gemini REST API."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable

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
    canonical_json,
    contract_validator,
    jsonl_text,
    load_json,
    load_jsonl,
    pretty_json,
    validate_instance,
)

RUN_SCHEMA_PATH = ROOT / "evals" / "run-schema.json"
API_ROOT = "https://generativelanguage.googleapis.com/v1beta"
ADAPTER_VERSION = "1"
MODEL_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")
SYSTEM_INSTRUCTION = (
    "You are a strict independent evaluation judge. Assess only the supplied assistant response "
    "against the supplied criteria. Do not reward unstated behavior. Evidence must quote or "
    "closely identify content in the response. Return only the requested JSON object."
)


class GeminiAdapterError(RuntimeError):
    """Raised when Gemini cannot produce auditable criterion judgments."""


class GeminiHTTPError(GeminiAdapterError):
    """HTTP failure with a bounded provider response body for local audit."""

    def __init__(self, status: int, body: str) -> None:
        super().__init__(f"Gemini API HTTP {status}: {body[:500]}")
        self.status = status
        self.body = body[:2000]


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
            raise GeminiAdapterError(
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
        raise GeminiAdapterError(f"Unknown requested case ids: {', '.join(unknown)}")
    return [case for case in cases if case["case_id"] in requested]


def clean_judgment(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if not key.startswith("_")}


def judge_namespace(model: str) -> str:
    model_slug = re.sub(r"[^a-z0-9]+", "-", model.lower()).strip("-")
    return f"gemini-api--{model_slug}--{PROMPT_VERSION}"


def build_request_body(
    case: dict[str, Any], response: dict[str, Any], *, max_output_tokens: int
) -> dict[str, Any]:
    return {
        "systemInstruction": {"parts": [{"text": SYSTEM_INSTRUCTION}]},
        "contents": [
            {
                "role": "user",
                "parts": [{"text": judgment_prompt(case, response)}],
            }
        ],
        "generationConfig": {
            "temperature": 0,
            "candidateCount": 1,
            "maxOutputTokens": max_output_tokens,
            "responseMimeType": "application/json",
            "responseJsonSchema": judgment_schema(case),
        },
    }


def parse_generate_response(payload: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    if not isinstance(payload, dict):
        raise GeminiAdapterError("Gemini response is not a JSON object")
    prompt_feedback = payload.get("promptFeedback", {})
    if isinstance(prompt_feedback, dict) and prompt_feedback.get("blockReason"):
        raise GeminiAdapterError(
            f"Gemini blocked the prompt: {prompt_feedback['blockReason']}"
        )
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or len(candidates) != 1:
        raise GeminiAdapterError("Gemini response must contain exactly one candidate")
    candidate = candidates[0]
    finish_reason = candidate.get("finishReason")
    if finish_reason != "STOP":
        raise GeminiAdapterError(
            f"Gemini candidate did not finish cleanly: {finish_reason}"
        )
    parts = candidate.get("content", {}).get("parts", [])
    texts = [part.get("text") for part in parts if isinstance(part, dict)]
    if not texts or any(not isinstance(text, str) for text in texts):
        raise GeminiAdapterError("Gemini candidate contains no complete text response")
    try:
        parsed = json.loads("".join(texts))
    except json.JSONDecodeError as exc:
        raise GeminiAdapterError(
            f"Gemini structured output is invalid JSON: {exc}"
        ) from exc
    if not isinstance(parsed, dict):
        raise GeminiAdapterError("Gemini structured output must be a JSON object")
    model_version = payload.get("modelVersion")
    if not isinstance(model_version, str) or not model_version:
        raise GeminiAdapterError("Gemini response omits modelVersion")
    usage = payload.get("usageMetadata", {})
    if not isinstance(usage, dict):
        usage = {}
    metadata = {
        "model_version": model_version,
        "response_id": str(payload.get("responseId", "")),
        "finish_reason": finish_reason,
        "usage": {
            "prompt_tokens": int(usage.get("promptTokenCount", 0) or 0),
            "output_tokens": int(usage.get("candidatesTokenCount", 0) or 0),
            "thought_tokens": int(usage.get("thoughtsTokenCount", 0) or 0),
            "total_tokens": int(usage.get("totalTokenCount", 0) or 0),
        },
    }
    return parsed, metadata


def post_generate_content(
    *,
    model: str,
    api_key: str,
    body: dict[str, Any],
    timeout_seconds: int,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> tuple[dict[str, Any], int]:
    encoded_model = urllib.parse.quote(model, safe="-._")
    endpoint = f"{API_ROOT}/models/{encoded_model}:generateContent"
    request = urllib.request.Request(
        endpoint,
        data=canonical_json(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
        method="POST",
    )
    started = time.monotonic()
    try:
        with opener(request, timeout=timeout_seconds) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise GeminiHTTPError(exc.code, error_body) from exc
    except urllib.error.URLError as exc:
        raise GeminiAdapterError(f"Gemini API network error: {exc.reason}") from exc
    latency_ms = round((time.monotonic() - started) * 1000)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise GeminiAdapterError(f"Gemini API returned invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise GeminiAdapterError("Gemini API response is not a JSON object")
    return payload, latency_ms


def write_attempt_trace(
    trace_dir: Path, case_sha256: str, envelope: dict[str, Any]
) -> tuple[Path, str]:
    case_dir = trace_dir / case_sha256
    case_dir.mkdir(parents=True, exist_ok=True)
    for attempt in range(1, 1000):
        path = case_dir / f"{attempt:03d}.json"
        if not path.exists():
            content = pretty_json(envelope)
            atomic_write(path, content)
            return path, sha256_text(content)
    raise GeminiAdapterError(f"Too many trace attempts for {case_sha256}")


def judge_one(
    *,
    case: dict[str, Any],
    response: dict[str, Any],
    model: str,
    api_key: str,
    max_output_tokens: int,
    timeout_seconds: int,
    trace_dir: Path,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> dict[str, Any]:
    body = build_request_body(case, response, max_output_tokens=max_output_tokens)
    provider_payload: dict[str, Any] | None = None
    latency_ms = 0
    try:
        provider_payload, latency_ms = post_generate_content(
            model=model,
            api_key=api_key,
            body=body,
            timeout_seconds=timeout_seconds,
            opener=opener,
        )
        parsed, metadata = parse_generate_response(provider_payload)
        judgment = restore_judgment(case, parsed)
        _, trace_sha256 = write_attempt_trace(
            trace_dir,
            case["case_sha256"],
            {
                "ok": True,
                "latency_ms": latency_ms,
                "provider_response": provider_payload,
            },
        )
    except GeminiHTTPError as exc:
        write_attempt_trace(
            trace_dir,
            case["case_sha256"],
            {"ok": False, "http_status": exc.status, "provider_error": exc.body},
        )
        raise
    except (GeminiAdapterError, EvalRunnerError) as exc:
        write_attempt_trace(
            trace_dir,
            case["case_sha256"],
            {
                "ok": False,
                "latency_ms": latency_ms,
                "adapter_error": str(exc)[:2000],
                "provider_response": provider_payload,
            },
        )
        raise
    judgment.update(
        {
            "_requested_model": model,
            "_model_version": metadata["model_version"],
            "_response_id": metadata["response_id"],
            "_prompt_version": PROMPT_VERSION,
            "_latency_ms": latency_ms,
            "_usage": metadata["usage"],
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
) -> None:
    case_by_id = {case["case_id"]: case for case in cases}
    unknown = set(completed) - set(case_by_id)
    if unknown:
        raise GeminiAdapterError("Checkpoint contains cases outside this manifest")
    validator = contract_validator(run_schema, "judgment")
    for case_id, row in completed.items():
        validate_instance(
            validator, clean_judgment(row), label=f"checkpoint[{case_id}]"
        )
        if row.get("_requested_model") != requested_model:
            raise GeminiAdapterError(
                f"Checkpoint {case_id} has a different requested model"
            )
        if row.get("_prompt_version") != PROMPT_VERSION:
            raise GeminiAdapterError(
                f"Checkpoint {case_id} has a different prompt version"
            )
        expected = [item["criterion"] for item in row["expected_behavior"]]
        forbidden = [item["criterion"] for item in row["forbidden_behavior"]]
        if expected != case_by_id[case_id]["expected_behavior"]:
            raise GeminiAdapterError(f"Checkpoint {case_id} expected criteria drift")
        if forbidden != case_by_id[case_id]["forbidden_behavior"]:
            raise GeminiAdapterError(f"Checkpoint {case_id} forbidden criteria drift")


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
        raise GeminiAdapterError(
            "Routing-only manifests do not require criterion judging"
        )
    cases = [
        case
        for case in manifest["cases"]
        if case.get("behavior_class", "advisory") != "routing-only"
    ]
    if not cases:
        raise GeminiAdapterError("Manifest has no behavior-evaluable cases")
    responses = {
        row["case_id"]: row for row in load_jsonl(run_dir / "raw" / "responses.jsonl")
    }
    if set(responses) != {case["case_id"] for case in cases}:
        raise GeminiAdapterError(
            "Ingested raw responses do not exactly match the manifest"
        )
    selected_cases = select_cases(cases, args.case_id)
    adapter_dir = run_dir / "adapter" / judge_namespace(args.judge_model)
    partial_path = adapter_dir / "judgments.partial.jsonl"
    output_path = adapter_dir / "judgments.json"
    completed = read_partial_rows(partial_path)
    validate_checkpoint(
        completed=completed,
        cases=cases,
        run_schema=run_schema,
        requested_model=args.judge_model,
    )
    pending = [case for case in selected_cases if case["case_id"] not in completed]
    if args.dry_run:
        print(
            json.dumps(
                {
                    "provider": "google-gemini-api",
                    "model": args.judge_model,
                    "prompt_version": PROMPT_VERSION,
                    "requests_per_minute": args.requests_per_minute,
                    "max_requests": args.max_requests,
                    "automatic_retries": 0,
                    "pending_case_ids": [case["case_id"] for case in pending],
                },
                ensure_ascii=False,
            )
        )
        return output_path
    if not args.acknowledge_external_data_use:
        raise GeminiAdapterError(
            "Refusing external API calls without --acknowledge-external-data-use; send only "
            "public or sanitized benchmark data"
        )
    api_key = os.environ.get(args.api_key_env, "").strip()
    if not api_key:
        raise GeminiAdapterError(
            f"Missing API key in environment variable {args.api_key_env}"
        )
    if len(pending) > args.max_requests:
        raise GeminiAdapterError(
            f"Pending cases ({len(pending)}) exceed invocation request cap ({args.max_requests})"
        )

    trace_dir = adapter_dir / "traces"
    minimum_interval = 60.0 / args.requests_per_minute
    previous_start: float | None = None
    observed_versions = {
        row["_model_version"] for row in completed.values() if row.get("_model_version")
    }
    for case in pending:
        if previous_start is not None:
            remaining = minimum_interval - (time.monotonic() - previous_start)
            if remaining > 0:
                time.sleep(remaining)
        previous_start = time.monotonic()
        judgment = judge_one(
            case=case,
            response=responses[case["case_id"]],
            model=args.judge_model,
            api_key=api_key,
            max_output_tokens=args.max_output_tokens,
            timeout_seconds=args.timeout_seconds,
            trace_dir=trace_dir,
        )
        observed_versions.add(judgment["_model_version"])
        if len(observed_versions) != 1:
            raise GeminiAdapterError(
                f"Provider model version drift within run: {sorted(observed_versions)}"
            )
        completed[case["case_id"]] = judgment
        ordered = [
            completed[item["case_id"]] for item in cases if item["case_id"] in completed
        ]
        atomic_write(partial_path, jsonl_text(ordered))
        print(f"judgments {len(completed)}/{len(cases)}", file=sys.stderr)

    if args.case_id:
        return partial_path
    if len(completed) != len(cases):
        raise GeminiAdapterError(
            f"Incomplete judging: {len(completed)}/{len(cases)} judgments"
        )
    if len(observed_versions) != 1:
        raise GeminiAdapterError(
            "A complete judgment set requires one observed model version"
        )
    final_judgments = [clean_judgment(completed[case["case_id"]]) for case in cases]
    judgment_set = {
        "schema_version": 1,
        "suite_sha256": manifest["suite_sha256"],
        "judge": {
            "kind": "model",
            "name": "google-gemini-api",
            "version": next(iter(observed_versions)),
        },
        "judgments": final_judgments,
    }
    validate_instance(
        contract_validator(run_schema, "judgmentSet"), judgment_set, label="judgments"
    )
    atomic_write(output_path, pretty_json(judgment_set))
    usage_keys = ("prompt_tokens", "output_tokens", "thought_tokens", "total_tokens")
    usage = {
        key: sum(int(row.get("_usage", {}).get(key, 0)) for row in completed.values())
        for key in usage_keys
    }
    successful_requests, failed_requests = trace_counts(trace_dir)
    metrics = {
        "adapter_version": ADAPTER_VERSION,
        "provider": "google-gemini-api",
        "requested_model": args.judge_model,
        "observed_model_version": next(iter(observed_versions)),
        "prompt_version": PROMPT_VERSION,
        "cases": len(cases),
        "requests_recorded": successful_requests + failed_requests,
        "successful_requests": successful_requests,
        "failed_requests": failed_requests,
        "automatic_retries": 0,
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
    judge.add_argument("--api-key-env", default="GEMINI_API_KEY")
    judge.add_argument("--requests-per-minute", type=float, required=True)
    judge.add_argument("--max-requests", type=int, required=True)
    judge.add_argument("--timeout-seconds", type=int, default=180)
    judge.add_argument("--max-output-tokens", type=int, default=2048)
    judge.add_argument("--case-id", action="append")
    judge.add_argument("--dry-run", action="store_true")
    judge.add_argument("--acknowledge-external-data-use", action="store_true")
    return parser


def validate_args(args: argparse.Namespace) -> None:
    if not MODEL_PATTERN.fullmatch(args.judge_model):
        raise GeminiAdapterError("judge-model contains unsafe characters")
    if args.requests_per_minute <= 0:
        raise GeminiAdapterError("requests-per-minute must be positive")
    if args.max_requests < 1:
        raise GeminiAdapterError("max-requests must be positive")
    if args.timeout_seconds < 1:
        raise GeminiAdapterError("timeout-seconds must be positive")
    if not 64 <= args.max_output_tokens <= 8192:
        raise GeminiAdapterError("max-output-tokens must be between 64 and 8192")
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", args.api_key_env):
        raise GeminiAdapterError(
            "api-key-env must be a valid environment variable name"
        )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        validate_args(args)
        output = judge_run(args)
    except (GeminiAdapterError, EvalRunnerError, OSError) as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
