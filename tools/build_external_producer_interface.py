"""Build and verify answer-safe producer interfaces for external cases."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from build_external_eval_freeze import (
    EXPECTED_CASE_IDS,
    EXPECTED_V1_SUITE_SHA256,
    FREEZE_ID as BASE_FREEZE_ID,
)
from build_external_eval_freeze_v2 import (
    EXPECTED_V2_SUITE_SHA256,
    FREEZE_ID as CONTRACT_FREEZE_ID,
)

ROOT = Path(__file__).resolve().parent.parent
SUITE_ROOT = ROOT / "evals" / "external" / "geoanalystbench"
INTERFACE_ROOT = SUITE_ROOT / "producer-interfaces" / "v1"
SCHEMA_NAME = "schema.json"
MANIFEST_NAME = "producer-interface-v1.json"
MANIFEST_PATH = SUITE_ROOT / MANIFEST_NAME
INTERFACE_ID = "geoanalystbench-producer-interface-v1"
FROZEN_ON = "2026-08-01"
EXPECTED_INTERFACE_SHA256 = (
    "8596ddfeac83679c9a7c0b5007e5c009a44559823d8e70903bf5c66fd4274962"
)
FORBIDDEN_KEYS = {
    "answer",
    "expected",
    "ground_truth",
    "oracle",
    "reference",
    "validator",
}


def read_json(path: Path) -> Any:
    """Read a UTF-8 JSON document, accepting an optional BOM."""
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha256_file(path: Path) -> str:
    """Return the lowercase SHA-256 digest of one file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_bytes(payload: dict[str, Any]) -> bytes:
    """Serialize a manifest deterministically as UTF-8 JSON."""
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    return text.encode("utf-8")


def discover_interface_paths(suite_root: Path = SUITE_ROOT) -> list[Path]:
    """Return the exact schema and five producer interfaces."""
    root = suite_root / "producer-interfaces" / "v1"
    case_paths = [root / f"{case_id}.json" for case_id in EXPECTED_CASE_IDS]
    return [root / SCHEMA_NAME, *case_paths]


def build_manifest(suite_root: Path = SUITE_ROOT) -> dict[str, Any]:
    """Build the canonical producer-interface manifest."""
    files = [
        {
            "path": path.relative_to(suite_root).as_posix(),
            "sha256": sha256_file(path),
        }
        for path in discover_interface_paths(suite_root)
    ]
    files.sort(key=lambda item: str(item["path"]))
    hash_input = "".join(
        f"{entry['sha256']}  {entry['path']}\n" for entry in files
    ).encode("utf-8")
    return {
        "base_freeze_id": BASE_FREEZE_ID,
        "base_suite_sha256": EXPECTED_V1_SUITE_SHA256,
        "case_ids": EXPECTED_CASE_IDS,
        "contract_freeze_id": CONTRACT_FREEZE_ID,
        "contract_suite_sha256": EXPECTED_V2_SUITE_SHA256,
        "files": files,
        "frozen_on": FROZEN_ON,
        "interface_id": INTERFACE_ID,
        "native_suite_included": False,
        "reference_values_included": False,
        "reporting_scope": "external-transfer-only",
        "schema_version": 1,
        "status": "frozen",
        "suite_sha256": hashlib.sha256(hash_input).hexdigest(),
    }


def _find_forbidden_keys(value: Any, prefix: str = "") -> list[str]:
    """Return answer-bearing key names found anywhere in an interface."""
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            location = f"{prefix}.{key}" if prefix else str(key)
            if str(key).lower() in FORBIDDEN_KEYS:
                found.append(location)
            found.extend(_find_forbidden_keys(child, location))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(_find_forbidden_keys(child, f"{prefix}[{index}]"))
    return found


def validate_interface_sources(suite_root: Path = SUITE_ROOT) -> list[str]:
    """Validate interface schemas, inventories, and answer-safe boundaries."""
    errors: list[str] = []
    root = suite_root / "producer-interfaces" / "v1"
    expected_names = {SCHEMA_NAME, *[f"{case_id}.json" for case_id in EXPECTED_CASE_IDS]}
    actual_names = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and path.suffix != ".pyc"
    }
    for name in sorted(expected_names - actual_names):
        errors.append(f"missing producer-interface file: {name}")
    for name in sorted(actual_names - expected_names):
        errors.append(f"unregistered producer-interface file: {name}")
    if errors:
        return errors

    try:
        schema = read_json(root / SCHEMA_NAME)
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return [f"cannot initialize producer-interface validation: {exc}"]

    for case_id in EXPECTED_CASE_IDS:
        path = root / f"{case_id}.json"
        try:
            payload = read_json(path)
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{path}: cannot read valid JSON: {exc}")
            continue
        schema_errors = sorted(
            validator.iter_errors(payload), key=lambda item: list(item.path)
        )
        for error in schema_errors:
            location = ".".join(str(part) for part in error.path) or "<root>"
            errors.append(f"{path}: {location}: {error.message}")
        if schema_errors or not isinstance(payload, dict):
            continue
        if payload["case_id"] != case_id:
            errors.append(f"{path}: case_id must match the filename")
        if payload["interface_id"] != f"{INTERFACE_ID}/{case_id}":
            errors.append(f"{path}: interface_id must identify its case")

        case = read_json(suite_root / "cases" / case_id / "case.json")
        expected_inventory = {str(item) for item in case["expected_artifacts"]}
        interface_inventory = {str(item["path"]) for item in payload["artifacts"]}
        if interface_inventory != expected_inventory:
            errors.append(f"{path}: artifact inventory must exactly match frozen v1")
        forbidden = _find_forbidden_keys(payload)
        if forbidden:
            errors.append(f"{path}: answer-bearing keys are forbidden: {forbidden}")
    return errors


def validate_manifest(
    suite_root: Path = SUITE_ROOT,
    manifest_path: Path | None = None,
) -> list[str]:
    """Return errors when the committed manifest differs from interfaces."""
    target = manifest_path or suite_root / MANIFEST_NAME
    if not target.is_file():
        return [f"missing producer-interface manifest: {target}"]
    try:
        committed = read_json(target)
        expected = build_manifest(suite_root)
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return [f"cannot verify producer-interface manifest: {exc}"]

    errors: list[str] = []
    if expected["suite_sha256"] != EXPECTED_INTERFACE_SHA256:
        errors.append("producer interfaces no longer match the pinned SHA-256")
    if committed.get("suite_sha256") != EXPECTED_INTERFACE_SHA256:
        errors.append("manifest no longer records the pinned producer-interface SHA-256")
    if committed != expected:
        errors.append("producer-interface manifest differs from the canonical payload")
    if canonical_bytes(committed) != target.read_bytes():
        errors.append("producer-interface manifest is not canonical UTF-8 JSON")
    return errors


def validate_producer_interface(suite_root: Path = SUITE_ROOT) -> list[str]:
    """Validate interface sources and their immutable manifest."""
    return [*validate_interface_sources(suite_root), *validate_manifest(suite_root)]


def write_manifest(path: Path = MANIFEST_PATH) -> None:
    """Create the producer-interface manifest without rewriting another version."""
    payload = build_manifest(path.parent)
    if payload["suite_sha256"] != EXPECTED_INTERFACE_SHA256:
        raise RuntimeError("current interfaces do not match the pinned SHA-256")
    rendered = canonical_bytes(payload)
    if path.exists() and path.read_bytes() != rendered:
        raise RuntimeError(f"{path} exists with different bytes; create a new version")
    path.write_bytes(rendered)


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true", help="create the manifest")
    mode.add_argument("--check", action="store_true", help="verify it (default)")
    return parser.parse_args()


def main() -> int:
    """Build or verify the producer-interface freeze."""
    args = parse_args()
    try:
        if args.write:
            write_manifest()
        errors = validate_producer_interface()
    except (OSError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"ERROR: producer-interface freeze failed: {exc}", file=sys.stderr)
        return 1
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    payload = read_json(MANIFEST_PATH)
    print(
        "producer interface: pass - "
        f"{len(payload['case_ids'])} cases, {len(payload['files'])} files, "
        f"{payload['suite_sha256'][:12]}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
