"""Build and verify the semantic GeoAnalystBench-derived v3 contract freeze."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from build_external_eval_freeze import EXPECTED_CASE_IDS, EXPECTED_V1_SUITE_SHA256
from build_external_eval_freeze_v2 import (
    EXPECTED_V2_SUITE_SHA256,
    FREEZE_ID as BASE_CONTRACT_FREEZE_ID,
)

ROOT = Path(__file__).resolve().parent.parent
SUITE_ROOT = ROOT / "evals" / "external" / "geoanalystbench"
VALIDATOR_PATH = Path("validators/v3/validate_artifacts.py")
MANIFEST_NAME = "freeze-v3.json"
MANIFEST_PATH = SUITE_ROOT / MANIFEST_NAME
FREEZE_ID = "geoanalystbench-derived-contracts-v3"
FROZEN_ON = "2026-08-01"
EXPECTED_V3_SUITE_SHA256 = (
    "e17b9ee3f6d69ba99aacc90cab998339bf0f679c76ce25645e09a70e882ad3f2"
)


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


def build_manifest(suite_root: Path = SUITE_ROOT) -> dict[str, Any]:
    """Build the canonical v3 semantic-contract manifest."""
    validator = suite_root / VALIDATOR_PATH
    file_entry = {
        "path": VALIDATOR_PATH.as_posix(),
        "sha256": sha256_file(validator),
    }
    hash_input = f"{file_entry['sha256']}  {file_entry['path']}\n".encode()
    return {
        "base_contract_freeze_id": BASE_CONTRACT_FREEZE_ID,
        "base_contract_suite_sha256": EXPECTED_V2_SUITE_SHA256,
        "base_suite_sha256": EXPECTED_V1_SUITE_SHA256,
        "case_ids": EXPECTED_CASE_IDS,
        "contract_axes": ["semantic", "evidence", "representation"],
        "files": [file_entry],
        "freeze_id": FREEZE_ID,
        "frozen_on": FROZEN_ON,
        "native_suite_included": False,
        "reporting_scope": "external-transfer-only",
        "results_included": False,
        "schema_version": 3,
        "status": "frozen",
        "strict_pass_rule": "all-required-semantic-criteria-and-exact-inventory",
        "suite_sha256": hashlib.sha256(hash_input).hexdigest(),
        "supersedes": BASE_CONTRACT_FREEZE_ID,
    }


def validate_contract_v3(suite_root: Path = SUITE_ROOT) -> list[str]:
    """Validate the v3 validator and immutable manifest."""
    errors: list[str] = []
    validator = suite_root / VALIDATOR_PATH
    if not validator.is_file():
        errors.append(f"missing v3 semantic validator: {VALIDATOR_PATH.as_posix()}")
        return errors
    if not MANIFEST_PATH.is_file():
        errors.append(f"missing v3 freeze manifest: {MANIFEST_PATH}")
        return errors
    try:
        committed = read_json(suite_root / MANIFEST_NAME)
        expected = build_manifest(suite_root)
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return [f"cannot verify v3 contract freeze: {exc}"]
    if expected["suite_sha256"] != EXPECTED_V3_SUITE_SHA256:
        errors.append("semantic validator no longer matches the pinned v3 SHA-256")
    if committed.get("suite_sha256") != EXPECTED_V3_SUITE_SHA256:
        errors.append("manifest no longer records the pinned v3 SHA-256")
    if committed != expected:
        errors.append("v3 freeze manifest differs from the canonical payload")
    if canonical_bytes(committed) != (suite_root / MANIFEST_NAME).read_bytes():
        errors.append("v3 freeze manifest is not canonical UTF-8 JSON")
    return errors


def write_manifest(path: Path = MANIFEST_PATH) -> None:
    """Create freeze-v3.json without rewriting another condition."""
    payload = build_manifest(path.parent)
    if payload["suite_sha256"] != EXPECTED_V3_SUITE_SHA256:
        raise RuntimeError("current semantic validator does not match pinned v3")
    rendered = canonical_bytes(payload)
    if path.exists() and path.read_bytes() != rendered:
        raise RuntimeError(f"{path} exists with different bytes; create a new version")
    path.write_bytes(rendered)


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true", help="create freeze-v3.json")
    mode.add_argument("--check", action="store_true", help="verify v3 (default)")
    return parser.parse_args()


def main() -> int:
    """Build or verify the v3 contract freeze."""
    args = parse_args()
    try:
        if args.write:
            write_manifest()
        errors = validate_contract_v3()
    except (OSError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"ERROR: external contract v3 freeze failed: {exc}", file=sys.stderr)
        return 1
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    payload = read_json(MANIFEST_PATH)
    print(
        "external contract v3: pass - "
        f"{len(payload['case_ids'])} cases, {len(payload['files'])} file, "
        f"{payload['suite_sha256'][:12]}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
