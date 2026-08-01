"""Preflight and evaluate a frozen external run without making model calls."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from build_external_eval_freeze import (
    EXPECTED_CASE_IDS,
    EXPECTED_V1_SUITE_SHA256,
    FREEZE_ID,
    validate_freeze_manifest,
)

ROOT = Path(__file__).resolve().parent.parent
SUITE_ROOT = ROOT / "evals" / "external" / "geoanalystbench"
CASE_ROOT = SUITE_ROOT / "cases"
RUN_SCHEMA = SUITE_ROOT / "run-schema.json"
RESULT_SCHEMA = SUITE_ROOT / "result-schema.json"
OUTPUT_LIMIT = 20_000
CLAIM_BOUNDARY = (
    "GeoAnalystBench-derived external transfer results; not pooled with the "
    "native 158-case suite and not the upstream 50-task benchmark."
)
PLACEHOLDER_PREFIX = "replace-before-run"


class ProtocolError(ValueError):
    """Raised when a run cannot be evaluated without violating the protocol."""


def read_json(path: Path) -> Any:
    """Read a UTF-8 JSON document, accepting an optional BOM."""
    return json.loads(path.read_text(encoding="utf-8-sig"))


def canonical_bytes(payload: dict[str, Any]) -> bytes:
    """Serialize a result deterministically apart from its explicit timestamp."""
    return (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def sha256_file(path: Path) -> str:
    """Return the lowercase SHA-256 digest of one file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def schema_errors(payload: Any, schema_path: Path) -> list[str]:
    """Return readable JSON Schema violations."""
    schema = read_json(schema_path)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors: list[str] = []
    for error in sorted(validator.iter_errors(payload), key=lambda item: list(item.path)):
        location = ".".join(str(part) for part in error.path) or "<root>"
        errors.append(f"{location}: {error.message}")
    return errors


def resolve_relative(base: Path, value: str, label: str) -> Path:
    """Resolve a manifest path while rejecting escape from its directory."""
    candidate = (base / value).resolve()
    try:
        candidate.relative_to(base.resolve())
    except ValueError as exc:
        raise ProtocolError(f"{label} escapes the manifest directory: {value}") from exc
    return candidate


def validate_manifest(payload: Any, manifest_path: Path) -> list[str]:
    """Validate schema, freeze identity, case population, and safety gates."""
    errors = schema_errors(payload, RUN_SCHEMA)
    if not isinstance(payload, dict):
        return errors

    freeze_errors = validate_freeze_manifest(SUITE_ROOT)
    errors.extend(f"freeze-v1.json: {error}" for error in freeze_errors)
    if payload.get("freeze_id") != FREEZE_ID:
        errors.append(f"freeze_id must equal {FREEZE_ID}")
    if payload.get("suite_sha256") != EXPECTED_V1_SUITE_SHA256:
        errors.append("suite_sha256 does not match frozen v1")

    case_ids = [str(case.get("case_id")) for case in payload.get("cases", [])]
    if case_ids != EXPECTED_CASE_IDS:
        errors.append(
            "cases must exactly match the frozen five-case order: "
            + ", ".join(EXPECTED_CASE_IDS)
        )
    if len(set(case_ids)) != len(case_ids):
        errors.append("cases contain duplicate case_id values")

    runtime = payload.get("runtime", {})
    skill_package = payload.get("skill_package", {})
    authorization = payload.get("authorization", {})
    inspected_values = [
        payload.get("run_id"),
        runtime.get("provider"),
        runtime.get("product"),
        runtime.get("product_version"),
        runtime.get("model"),
        runtime.get("model_version"),
        skill_package.get("source"),
        skill_package.get("version"),
        skill_package.get("revision"),
        authorization.get("approved_by"),
    ]
    if any(
        isinstance(value, str) and value.startswith(PLACEHOLDER_PREFIX)
        for value in inspected_values
    ):
        errors.append("replace every replace-before-run placeholder")
    archive_sha = skill_package.get("archive_sha256")
    if archive_sha == "0" * 64:
        errors.append("skill_package.archive_sha256 must record the installed archive")

    base = manifest_path.resolve().parent
    response_paths: set[Path] = set()
    artifact_dirs: set[Path] = set()
    for case in payload.get("cases", []):
        if not isinstance(case, dict):
            continue
        case_id = str(case.get("case_id", "<unknown>"))
        for field, collection in (
            ("response_path", response_paths),
            ("artifact_dir", artifact_dirs),
        ):
            value = case.get(field)
            if not isinstance(value, str):
                continue
            try:
                resolved = resolve_relative(base, value, f"{case_id}.{field}")
            except ProtocolError as exc:
                errors.append(str(exc))
                continue
            if resolved in collection:
                errors.append(f"{field} must be unique across cases: {value}")
            collection.add(resolved)
    if response_paths & artifact_dirs:
        errors.append("a response_path may not also be an artifact_dir")
    return errors


def truncate_output(value: str) -> tuple[str, bool]:
    """Bound validator output embedded in the durable result."""
    if len(value) <= OUTPUT_LIMIT:
        return value, False
    return value[:OUTPUT_LIMIT] + "\n[truncated]\n", True


def run_checked(command: list[str], *, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    """Run one repository-owned helper without a shell."""
    return subprocess.run(  # noqa: S603 - fixed interpreter and frozen scripts
        command,
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def case_contract(case_id: str) -> dict[str, Any]:
    """Read one frozen case contract."""
    payload = read_json(CASE_ROOT / case_id / "case.json")
    if not isinstance(payload, dict):
        raise ProtocolError(f"{case_id}: case.json must contain an object")
    return payload


def inventory_artifacts(output_dir: Path) -> list[dict[str, Any]]:
    """Hash every regular artifact below one case output directory."""
    if not output_dir.is_dir():
        return []
    inventory: list[dict[str, Any]] = []
    base = output_dir.resolve()
    for path in sorted(
        (item for item in output_dir.rglob("*") if item.is_file()),
        key=lambda item: item.relative_to(output_dir).as_posix(),
    ):
        resolved = path.resolve()
        try:
            resolved.relative_to(base)
        except ValueError as exc:
            raise ProtocolError(f"artifact path escapes output directory: {path}") from exc
        inventory.append(
            {
                "bytes": path.stat().st_size,
                "path": path.relative_to(output_dir).as_posix(),
                "sha256": sha256_file(path),
            }
        )
    return inventory


def evaluate_case(
    entry: dict[str, Any],
    manifest_dir: Path,
    fixture_root: Path,
) -> dict[str, Any]:
    """Generate the frozen fixture and validate one existing response."""
    case_id = str(entry["case_id"])
    contract = case_contract(case_id)
    case_dir = CASE_ROOT / case_id
    fixture_dir = fixture_root / case_id / "fixtures"
    generator = case_dir / str(contract["fixture_generator"])
    generated = run_checked(
        [sys.executable, str(generator), "--output-dir", str(fixture_dir)]
    )
    if generated.returncode != 0:
        raise ProtocolError(
            f"{case_id}: frozen fixture generator failed: {generated.stderr.strip()}"
        )

    input_paths = contract["input_paths"]
    if not isinstance(input_paths, list) or len(input_paths) != 1:
        raise ProtocolError(f"{case_id}: v1 runner requires exactly one input path")
    input_path = fixture_dir / Path(str(input_paths[0])).name
    if not input_path.is_file():
        raise ProtocolError(f"{case_id}: fixture generator did not create {input_path.name}")

    response_path = resolve_relative(
        manifest_dir, str(entry["response_path"]), f"{case_id}.response_path"
    )
    if not response_path.is_file():
        raise ProtocolError(f"{case_id}: response file is missing: {response_path}")
    output_dir = resolve_relative(
        manifest_dir, str(entry["artifact_dir"]), f"{case_id}.artifact_dir"
    )
    inventory = inventory_artifacts(output_dir)
    actual_names = {str(item["path"]) for item in inventory}
    expected_names = {
        Path(str(path)).relative_to("outputs").as_posix()
        for path in contract["expected_artifacts"]
    }
    missing = sorted(expected_names - actual_names)
    unexpected = sorted(actual_names - expected_names)

    status = str(entry["completion_status"])
    if status == "completed":
        validator_path = case_dir / str(contract["validator"])
        validated = run_checked(
            [
                sys.executable,
                str(validator_path),
                "--input",
                str(input_path),
                "--output-dir",
                str(output_dir),
            ]
        )
        stdout, stdout_truncated = truncate_output(validated.stdout)
        stderr, stderr_truncated = truncate_output(validated.stderr)
        validator = {
            "executed": True,
            "exit_code": validated.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "output_truncated": stdout_truncated or stderr_truncated,
        }
        passed = validated.returncode == 0 and not missing and not unexpected
    else:
        validator = {
            "executed": False,
            "exit_code": None,
            "stdout": "",
            "stderr": f"not executed because completion_status is {status}",
            "output_truncated": False,
        }
        passed = False

    return {
        "artifacts": inventory,
        "case_id": case_id,
        "completion_status": status,
        "fixture_sha256": sha256_file(input_path),
        "missing_artifacts": missing,
        "passed": passed,
        "response_sha256": sha256_file(response_path),
        "skill_activation": entry["skill_activation"],
        "unexpected_artifacts": unexpected,
        "validator": validator,
    }


def build_result(payload: dict[str, Any], manifest_path: Path) -> dict[str, Any]:
    """Evaluate every case and return a schema-valid result payload."""
    manifest_dir = manifest_path.resolve().parent
    with tempfile.TemporaryDirectory(prefix="geoai-external-eval-") as temp_dir:
        fixture_root = Path(temp_dir)
        cases = [
            evaluate_case(entry, manifest_dir, fixture_root)
            for entry in payload["cases"]
        ]
    passed = sum(1 for case in cases if case["passed"])
    result = {
        "cases": cases,
        "claim_boundary": CLAIM_BOUNDARY,
        "condition": payload["condition"],
        "evaluated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "execution_policy": payload["execution_policy"],
        "freeze_id": payload["freeze_id"],
        "manifest_sha256": sha256_file(manifest_path),
        "native_suite_included": False,
        "reporting_scope": "external-transfer-only",
        "run_id": payload["run_id"],
        "runtime": payload["runtime"],
        "schema_version": 1,
        "skill_package": payload["skill_package"],
        "suite": "geoanalystbench-derived",
        "suite_sha256": payload["suite_sha256"],
        "summary": {
            "failed_cases": len(cases) - passed,
            "pass_rate": passed / len(cases),
            "passed_cases": passed,
            "total_cases": len(cases),
        },
    }
    errors = schema_errors(result, RESULT_SCHEMA)
    if errors:
        raise ProtocolError("generated result violates result schema: " + "; ".join(errors))
    return result


def write_atomic(path: Path, payload: dict[str, Any]) -> None:
    """Write canonical JSON atomically without leaving a partial result."""
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = canonical_bytes(payload)
    with tempfile.NamedTemporaryFile(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
        handle.write(rendered)
    temporary.replace(path)


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="validate gates and print the plan; make no calls and read no outputs",
    )
    parser.add_argument(
        "--result",
        type=Path,
        help="write the artifact-validation result; required without --dry-run",
    )
    return parser.parse_args()


def main() -> int:
    """Validate a run plan or evaluate already-produced artifacts."""
    args = parse_args()
    if not args.dry_run and args.result is None:
        print("ERROR: --result is required without --dry-run", file=sys.stderr)
        return 2
    if args.dry_run and args.result is not None:
        print("ERROR: --result cannot be used with --dry-run", file=sys.stderr)
        return 2
    try:
        payload = read_json(args.manifest)
        errors = validate_manifest(payload, args.manifest)
        if errors:
            for error in errors:
                print(f"ERROR: {error}", file=sys.stderr)
            return 1
        if args.dry_run:
            policy = payload["execution_policy"]
            print(
                "external run preflight: pass - "
                f"{len(payload['cases'])} cases, {policy['max_calls']} calls max, "
                f"${policy['max_cost_usd']:.2f} max, "
                f"{policy['automatic_retries']} automatic retries"
            )
            print("no model, API, web, connector, or artifact validator was invoked")
            return 0
        if args.result.resolve() == args.manifest.resolve():
            raise ProtocolError("--result may not overwrite the run manifest")
        if args.result.exists():
            raise ProtocolError(f"result already exists; refusing to overwrite: {args.result}")
        result = build_result(payload, args.manifest)
        write_atomic(args.result, result)
    except (
        json.JSONDecodeError,
        OSError,
        ProtocolError,
        subprocess.SubprocessError,
    ) as exc:
        print(f"ERROR: external run evaluation failed: {exc}", file=sys.stderr)
        return 1

    summary = result["summary"]
    print(
        "external run evaluated: "
        f"{summary['passed_cases']}/{summary['total_cases']} artifact contracts passed"
    )
    print(f"result: {args.result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
