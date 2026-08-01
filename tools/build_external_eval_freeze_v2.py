"""Build and verify GeoAnalystBench-derived v2 artifact contracts."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parent.parent
SUITE_ROOT = ROOT / "evals" / "external" / "geoanalystbench"
CONTRACT_ROOT = SUITE_ROOT / "contracts" / "v2"
CONTRACT_SCHEMA_NAME = "schema.json"
MANIFEST_NAME = "freeze-v2.json"
MANIFEST_PATH = SUITE_ROOT / MANIFEST_NAME
FREEZE_ID = "geoanalystbench-derived-contracts-v2"
CONTRACT_ID_PREFIX = "geoanalystbench-derived-v2"
FROZEN_ON = "2026-08-01"
BASE_FREEZE_ID = "geoanalystbench-derived-v1"
BASE_SUITE_SHA256 = (
    "c99563100cacc1e03234edd82ec64f4f47dc9479ca2ca4f9aabe84a1d5373f12"
)
EXPECTED_V2_SUITE_SHA256 = (
    "86170ae144092f1ae0f34124d85505f0d3507a19f04f2b71f2081c89d10de418"
)
EXPECTED_CASE_IDS = [
    "gab-01-urban-heat",
    "gab-08-facility-coverage",
    "gab-36-vegetation-change",
    "gab-38-travel-time",
    "gab-39-spatial-regression",
]
AXES = ["semantic", "evidence", "representation"]


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


def discover_contract_paths(suite_root: Path = SUITE_ROOT) -> list[Path]:
    """Return the exact schema and case contracts governed by v2."""
    root = suite_root / "contracts" / "v2"
    case_paths = [root / f"{case_id}.json" for case_id in EXPECTED_CASE_IDS]
    return [root / CONTRACT_SCHEMA_NAME, *case_paths]


def build_manifest(suite_root: Path = SUITE_ROOT) -> dict[str, Any]:
    """Build the canonical v2 contract-freeze payload from current bytes."""
    files = [
        {
            "path": path.relative_to(suite_root).as_posix(),
            "sha256": sha256_file(path),
        }
        for path in discover_contract_paths(suite_root)
    ]
    files.sort(key=lambda item: str(item["path"]))
    hash_input = "".join(
        f"{entry['sha256']}  {entry['path']}\n" for entry in files
    ).encode("utf-8")
    return {
        "base_freeze_id": BASE_FREEZE_ID,
        "base_suite_sha256": BASE_SUITE_SHA256,
        "case_ids": EXPECTED_CASE_IDS,
        "contract_axes": AXES,
        "files": files,
        "freeze_id": FREEZE_ID,
        "frozen_on": FROZEN_ON,
        "native_suite_included": False,
        "reporting_scope": "external-transfer-only",
        "results_included": False,
        "schema_version": 2,
        "status": "frozen",
        "strict_pass_rule": "all-required-criteria-and-exact-inventory",
        "suite_sha256": hashlib.sha256(hash_input).hexdigest(),
    }


def _v1_file_hashes(suite_root: Path) -> dict[str, str]:
    payload = read_json(suite_root / "freeze-v1.json")
    return {
        str(entry["path"]): str(entry["sha256"])
        for entry in payload["files"]
    }


def validate_contract_sources(suite_root: Path = SUITE_ROOT) -> list[str]:
    """Validate contract schemas, cross-references, axes, and inventories."""
    errors: list[str] = []
    root = suite_root / "contracts" / "v2"
    expected_names = {
        CONTRACT_SCHEMA_NAME,
        *[f"{case_id}.json" for case_id in EXPECTED_CASE_IDS],
    }
    actual_names = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and path.suffix != ".pyc"
    }
    for name in sorted(expected_names - actual_names):
        errors.append(f"missing v2 contract file: contracts/v2/{name}")
    for name in sorted(actual_names - expected_names):
        errors.append(f"unregistered v2 contract file: contracts/v2/{name}")
    if errors:
        return errors

    try:
        schema = read_json(root / CONTRACT_SCHEMA_NAME)
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        v1_hashes = _v1_file_hashes(suite_root)
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return [f"cannot initialize v2 contract validation: {exc}"]

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
        if payload["contract_id"] != f"{CONTRACT_ID_PREFIX}/{case_id}":
            errors.append(f"{path}: contract_id must identify its v2 case")

        case_rel = f"cases/{case_id}/case.json"
        validator_rel = f"cases/{case_id}/validate_artifacts.py"
        if payload["base_case_sha256"] != v1_hashes.get(case_rel):
            errors.append(f"{path}: base_case_sha256 does not match frozen v1")
        strict_validator = payload["strict_validator"]
        if strict_validator["path"] != validator_rel:
            errors.append(f"{path}: strict validator path does not match the case")
        if strict_validator["sha256"] != v1_hashes.get(validator_rel):
            errors.append(f"{path}: strict validator hash does not match frozen v1")

        case_payload = read_json(suite_root / case_rel)
        declared_inventory = {
            str(item["path"]) for item in payload["artifact_inventory"]
        }
        frozen_inventory = {str(item) for item in case_payload["expected_artifacts"]}
        if declared_inventory != frozen_inventory:
            errors.append(f"{path}: artifact inventory must exactly match frozen v1")

        criteria = payload["criteria"]
        criterion_ids = [str(item["id"]) for item in criteria]
        if len(criterion_ids) != len(set(criterion_ids)):
            errors.append(f"{path}: criterion ids must be unique")
        criterion_axes = {str(item["axis"]) for item in criteria}
        if criterion_axes != set(AXES):
            errors.append(f"{path}: criteria must cover each contract axis")
        for criterion in criteria:
            undeclared = set(criterion["artifacts"]) - declared_inventory
            if undeclared:
                errors.append(
                    f"{path}: criterion {criterion['id']} references undeclared artifacts"
                )
    return errors


def validate_freeze_manifest_v2(
    suite_root: Path = SUITE_ROOT,
    manifest_path: Path | None = None,
) -> list[str]:
    """Return errors when the committed v2 freeze differs from contracts."""
    target = manifest_path or suite_root / MANIFEST_NAME
    if not target.is_file():
        return [f"missing v2 freeze manifest: {target}"]
    try:
        committed = read_json(target)
        expected = build_manifest(suite_root)
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return [f"cannot verify v2 freeze manifest: {exc}"]

    errors: list[str] = []
    if expected["suite_sha256"] != EXPECTED_V2_SUITE_SHA256:
        errors.append("governed contracts no longer match the pinned v2 suite SHA-256")
    if committed.get("suite_sha256") != EXPECTED_V2_SUITE_SHA256:
        errors.append("manifest no longer records the pinned v2 suite SHA-256")
    if committed != expected:
        errors.append("v2 freeze manifest differs from the canonical contract payload")
    if canonical_bytes(committed) != target.read_bytes():
        errors.append("v2 freeze manifest is not canonical UTF-8 JSON")
    return errors


def validate_contracts_v2(suite_root: Path = SUITE_ROOT) -> list[str]:
    """Validate v2 contract sources and their immutable manifest."""
    return [
        *validate_contract_sources(suite_root),
        *validate_freeze_manifest_v2(suite_root),
    ]


def write_manifest(path: Path = MANIFEST_PATH) -> None:
    """Create freeze-v2.json, refusing to rewrite a different payload."""
    payload = build_manifest(path.parent)
    if payload["suite_sha256"] != EXPECTED_V2_SUITE_SHA256:
        raise RuntimeError("current contracts do not match the pinned v2 suite SHA-256")
    rendered = canonical_bytes(payload)
    if path.exists() and path.read_bytes() != rendered:
        raise RuntimeError(
            f"{path} already exists with different bytes; create a new freeze version"
        )
    path.write_bytes(rendered)


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true", help="create freeze-v2.json")
    mode.add_argument("--check", action="store_true", help="verify v2 (default)")
    return parser.parse_args()


def main() -> int:
    """Build or verify the v2 contract freeze."""
    args = parse_args()
    try:
        if args.write:
            write_manifest()
        errors = validate_contracts_v2()
    except (OSError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"ERROR: external contract freeze failed: {exc}", file=sys.stderr)
        return 1
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    payload = read_json(MANIFEST_PATH)
    print(
        "external contract freeze: pass - "
        f"{len(payload['case_ids'])} cases, {len(payload['files'])} files, "
        f"{payload['suite_sha256'][:12]}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
