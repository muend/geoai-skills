"""Validate isolated external evaluation-suite metadata and file boundaries."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from build_external_eval_freeze import MANIFEST_NAME, validate_freeze_manifest
from build_external_eval_freeze_v2 import (
    MANIFEST_NAME as CONTRACT_MANIFEST_NAME,
    validate_contracts_v2,
)
from build_external_eval_freeze_v3 import (
    MANIFEST_NAME as CONTRACT_V3_MANIFEST_NAME,
    validate_contract_v3,
)
from build_external_producer_interface import (
    MANIFEST_NAME as PRODUCER_MANIFEST_NAME,
    validate_producer_interface,
)
from build_external_producer_interface_v2 import (
    MANIFEST_NAME as PRODUCER_V2_MANIFEST_NAME,
    validate_producer_interface_v2,
)
from build_external_producer_interface_v3 import (
    EXPECTED_INTERFACE_SHA256 as EXPECTED_PRODUCER_V3_SHA256,
    INTERFACE_ID as PRODUCER_V3_ID,
    MANIFEST_NAME as PRODUCER_V3_MANIFEST_NAME,
    validate_producer_interface_v3,
)

ROOT = Path(__file__).resolve().parent.parent
SUITE_ROOT = ROOT / "evals" / "external" / "geoanalystbench"
CASE_ROOT = SUITE_ROOT / "cases"
EXPECTED_UPSTREAM_SHA = "b5d8c40a8d23639ec77e9acb11f79fd033c07338"
EXPECTED_FREEZE_ID = "geoanalystbench-derived-v1"
EXPECTED_SUITE_SHA256 = (
    "c99563100cacc1e03234edd82ec64f4f47dc9479ca2ca4f9aabe84a1d5373f12"
)


def read_json(path: Path) -> Any:
    """Read a UTF-8 JSON document, accepting an optional BOM."""
    return json.loads(path.read_text(encoding="utf-8-sig"))


def safe_relative_path(case_dir: Path, value: str) -> Path | None:
    """Resolve a declared relative path without allowing directory escape."""
    candidate = (case_dir / value).resolve()
    try:
        candidate.relative_to(case_dir.resolve())
    except ValueError:
        return None
    return candidate


def validate_case(
    case_path: Path,
    validator: Draft202012Validator,
    seen_ids: set[str],
    seen_upstream_ids: set[int],
) -> list[str]:
    """Validate one external case and return readable errors."""
    errors: list[str] = []
    try:
        payload = read_json(case_path)
    except (OSError, json.JSONDecodeError) as exc:
        return [f"{case_path}: cannot read valid JSON: {exc}"]

    for error in sorted(validator.iter_errors(payload), key=lambda item: list(item.path)):
        location = ".".join(str(part) for part in error.path) or "<root>"
        errors.append(f"{case_path}: {location}: {error.message}")
    if errors or not isinstance(payload, dict):
        return errors

    case_id = str(payload["case_id"])
    upstream_id = int(payload["upstream_task_id"])
    if case_id in seen_ids:
        errors.append(f"{case_path}: duplicate case_id {case_id}")
    if upstream_id in seen_upstream_ids:
        errors.append(f"{case_path}: duplicate upstream_task_id {upstream_id}")
    seen_ids.add(case_id)
    seen_upstream_ids.add(upstream_id)

    if case_path.parent.name != case_id:
        errors.append(f"{case_path}: directory name must equal case_id")

    case_dir = case_path.parent
    for field in ("fixture_generator", "reference", "validator"):
        declared = str(payload[field])
        resolved = safe_relative_path(case_dir, declared)
        if resolved is None or not resolved.is_file():
            errors.append(f"{case_path}: {field} does not resolve to a case-local file")

    prompt = str(payload["prompt"])
    for declared in [*payload["input_paths"], *payload["expected_artifacts"]]:
        if declared not in prompt:
            errors.append(f"{case_path}: prompt must name declared path {declared}")

    task_url = str(payload["provenance"]["upstream_task_url"])
    if EXPECTED_UPSTREAM_SHA not in task_url:
        errors.append(f"{case_path}: upstream_task_url must pin the registered commit")
    return errors


def validate_suite() -> tuple[int, list[str]]:
    """Validate provenance, schema, and every external case."""
    errors: list[str] = []
    required = [
        SUITE_ROOT / "README.md",
        SUITE_ROOT / "NOTICE",
        SUITE_ROOT / "LICENSE-APACHE-2.0",
        SUITE_ROOT / "provenance.json",
        SUITE_ROOT / "schema.json",
        SUITE_ROOT / MANIFEST_NAME,
        SUITE_ROOT / CONTRACT_MANIFEST_NAME,
        SUITE_ROOT / CONTRACT_V3_MANIFEST_NAME,
        SUITE_ROOT / PRODUCER_MANIFEST_NAME,
        SUITE_ROOT / PRODUCER_V2_MANIFEST_NAME,
        SUITE_ROOT / PRODUCER_V3_MANIFEST_NAME,
        SUITE_ROOT / "run-schema.json",
        SUITE_ROOT / "result-schema.json",
        SUITE_ROOT / "run-template.json",
        SUITE_ROOT / "run-template-v2.json",
        SUITE_ROOT / "run-template-v3.json",
        SUITE_ROOT / "RESULTS-TEMPLATE.md",
    ]
    for path in required:
        if not path.is_file():
            errors.append(f"missing required external-suite file: {path}")
    if errors:
        return 0, errors

    try:
        provenance = read_json(SUITE_ROOT / "provenance.json")
        schema = read_json(SUITE_ROOT / "schema.json")
        run_schema = read_json(SUITE_ROOT / "run-schema.json")
        result_schema = read_json(SUITE_ROOT / "result-schema.json")
        run_template = read_json(SUITE_ROOT / "run-template.json")
        run_template_v2 = read_json(SUITE_ROOT / "run-template-v2.json")
        run_template_v3 = read_json(SUITE_ROOT / "run-template-v3.json")
    except (OSError, json.JSONDecodeError) as exc:
        return 0, [f"external-suite metadata is invalid: {exc}"]

    if provenance.get("upstream", {}).get("commit_sha") != EXPECTED_UPSTREAM_SHA:
        errors.append("provenance.json: upstream commit SHA is not the registered ref")
    reuse = provenance.get("reuse", {})
    for field in (
        "upstream_datasets_included",
        "upstream_reference_code_included",
        "upstream_prompts_copied_verbatim",
    ):
        if reuse.get(field) is not False:
            errors.append(f"provenance.json: {field} must remain false")

    Draft202012Validator.check_schema(schema)
    Draft202012Validator.check_schema(run_schema)
    Draft202012Validator.check_schema(result_schema)
    validator = Draft202012Validator(schema)
    case_paths = sorted(CASE_ROOT.glob("*/case.json"))
    seen_ids: set[str] = set()
    seen_upstream_ids: set[int] = set()
    for case_path in case_paths:
        errors.extend(validate_case(case_path, validator, seen_ids, seen_upstream_ids))

    registered_ids = provenance.get("included_upstream_task_ids")
    if registered_ids != sorted(seen_upstream_ids):
        errors.append(
            "provenance.json: included_upstream_task_ids must exactly match case files"
        )
    errors.extend(
        f"{MANIFEST_NAME}: {error}"
        for error in validate_freeze_manifest(SUITE_ROOT)
    )
    errors.extend(
        f"{CONTRACT_MANIFEST_NAME}: {error}"
        for error in validate_contracts_v2(SUITE_ROOT)
    )
    errors.extend(
        f"{CONTRACT_V3_MANIFEST_NAME}: {error}"
        for error in validate_contract_v3(SUITE_ROOT)
    )
    errors.extend(
        f"{PRODUCER_MANIFEST_NAME}: {error}"
        for error in validate_producer_interface(SUITE_ROOT)
    )
    errors.extend(
        f"{PRODUCER_V2_MANIFEST_NAME}: {error}"
        for error in validate_producer_interface_v2(SUITE_ROOT)
    )
    errors.extend(
        f"{PRODUCER_V3_MANIFEST_NAME}: {error}"
        for error in validate_producer_interface_v3(SUITE_ROOT)
    )
    run_validator = Draft202012Validator(
        run_schema,
        format_checker=FormatChecker(),
    )
    for template_name, template in (
        ("run-template.json", run_template),
        ("run-template-v2.json", run_template_v2),
        ("run-template-v3.json", run_template_v3),
    ):
        for error in sorted(
            run_validator.iter_errors(template),
            key=lambda item: list(item.path),
        ):
            location = ".".join(str(part) for part in error.path) or "<root>"
            errors.append(f"{template_name}: {location}: {error.message}")
    if run_template.get("freeze_id") != EXPECTED_FREEZE_ID:
        errors.append("run-template.json: freeze_id must remain pinned to v1")
    if run_template.get("suite_sha256") != EXPECTED_SUITE_SHA256:
        errors.append("run-template.json: suite_sha256 must remain pinned to v1")
    if run_template.get("native_suite_included") is not False:
        errors.append("run-template.json: native suite pooling must remain false")
    if run_template.get("reporting_scope") != "external-transfer-only":
        errors.append("run-template.json: reporting scope must remain external-only")
    if run_template_v2.get("producer_interface_id") != (
        "geoanalystbench-producer-interface-v2"
    ):
        errors.append("run-template-v2.json: producer interface must remain pinned to v2")
    if run_template_v2.get("producer_interface_sha256") != (
        "7ebfc789c10e99e9b3ec012b6e1e5323dd374be2a961ae3a645c976c684a5647"
    ):
        errors.append("run-template-v2.json: producer interface hash must remain pinned")
    for field in ("freeze_id", "suite_sha256", "reporting_scope"):
        if run_template_v2.get(field) != run_template.get(field):
            errors.append(f"run-template-v2.json: {field} must match the v1 template")
    if run_template_v3.get("producer_interface_id") != PRODUCER_V3_ID:
        errors.append("run-template-v3.json: producer interface must remain pinned to v3")
    if run_template_v3.get("producer_interface_sha256") != (
        EXPECTED_PRODUCER_V3_SHA256
    ):
        errors.append("run-template-v3.json: producer interface hash must remain pinned")
    for field in ("freeze_id", "suite_sha256", "reporting_scope"):
        if run_template_v3.get(field) != run_template.get(field):
            errors.append(f"run-template-v3.json: {field} must match the v1 template")
    return len(case_paths), errors


def main() -> int:
    """Run external-suite validation."""
    try:
        case_count, errors = validate_suite()
    except Exception as exc:  # pragma: no cover - defensive CLI boundary
        print(f"ERROR: external suite validation crashed: {exc}", file=sys.stderr)
        return 1
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        print(
            f"{case_count} external cases checked — {len(errors)} errors",
            file=sys.stderr,
        )
        return 1
    print(f"{case_count} external cases checked — 0 errors")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
