"""Build and verify the immutable GeoAnalystBench-derived v1 source manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
SUITE_ROOT = ROOT / "evals" / "external" / "geoanalystbench"
MANIFEST_NAME = "freeze-v1.json"
MANIFEST_PATH = SUITE_ROOT / MANIFEST_NAME
FREEZE_ID = "geoanalystbench-derived-v1"
FROZEN_ON = "2026-07-29"
EXPECTED_V1_SUITE_SHA256 = (
    "c99563100cacc1e03234edd82ec64f4f47dc9479ca2ca4f9aabe84a1d5373f12"
)
EXPECTED_CASE_IDS = [
    "gab-01-urban-heat",
    "gab-08-facility-coverage",
    "gab-36-vegetation-change",
    "gab-38-travel-time",
    "gab-39-spatial-regression",
]
SUITE_SOURCE_NAMES = [
    "LICENSE-APACHE-2.0",
    "NOTICE",
    "provenance.json",
    "schema.json",
]


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


def discover_source_paths(suite_root: Path) -> list[Path]:
    """Return every source file governed by the v1 freeze."""
    paths = [suite_root / name for name in SUITE_SOURCE_NAMES]
    case_root = suite_root / "cases"
    for case_id in EXPECTED_CASE_IDS:
        case_dir = case_root / case_id
        if case_dir.is_dir():
            paths.extend(
                path
                for path in case_dir.rglob("*")
                if path.is_file()
                and "__pycache__" not in path.parts
                and path.suffix != ".pyc"
            )
    return sorted(paths, key=lambda path: path.relative_to(suite_root).as_posix())


def build_manifest(suite_root: Path = SUITE_ROOT) -> dict[str, Any]:
    """Build the canonical v1 freeze payload from current source bytes."""
    provenance = read_json(suite_root / "provenance.json")
    case_root = suite_root / "cases"
    case_ids = sorted(
        path.parent.name for path in case_root.glob("*/case.json") if path.is_file()
    )
    upstream_task_ids = sorted(
        int(read_json(case_root / case_id / "case.json")["upstream_task_id"])
        for case_id in case_ids
    )

    files = [
        {
            "path": path.relative_to(suite_root).as_posix(),
            "sha256": sha256_file(path),
        }
        for path in discover_source_paths(suite_root)
    ]
    hash_input = "".join(
        f"{entry['sha256']}  {entry['path']}\n" for entry in files
    ).encode("utf-8")
    suite_sha256 = hashlib.sha256(hash_input).hexdigest()

    return {
        "case_ids": case_ids,
        "files": files,
        "freeze_id": FREEZE_ID,
        "frozen_on": FROZEN_ON,
        "native_suite_included": False,
        "reporting_scope": "external-transfer-only",
        "results_included": False,
        "schema_version": 1,
        "status": "frozen",
        "suite_sha256": suite_sha256,
        "upstream_commit_sha": provenance["upstream"]["commit_sha"],
        "upstream_task_ids": upstream_task_ids,
    }


def canonical_bytes(payload: dict[str, Any]) -> bytes:
    """Serialize a manifest deterministically as UTF-8 JSON."""
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    return text.encode("utf-8")


def validate_freeze_manifest(
    suite_root: Path = SUITE_ROOT,
    manifest_path: Path | None = None,
) -> list[str]:
    """Return errors when the committed freeze differs from current sources."""
    target = manifest_path or suite_root / MANIFEST_NAME
    if not target.is_file():
        return [f"missing freeze manifest: {target}"]
    try:
        committed = read_json(target)
        expected = build_manifest(suite_root)
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return [f"cannot verify freeze manifest: {exc}"]

    errors: list[str] = []
    if expected["suite_sha256"] != EXPECTED_V1_SUITE_SHA256:
        errors.append(
            "governed sources no longer match the pinned v1 suite SHA-256"
        )
    if committed.get("suite_sha256") != EXPECTED_V1_SUITE_SHA256:
        errors.append("manifest no longer records the pinned v1 suite SHA-256")
    if committed != expected:
        committed_files = {
            str(item.get("path")): str(item.get("sha256"))
            for item in committed.get("files", [])
            if isinstance(item, dict)
        }
        expected_files = {
            str(item["path"]): str(item["sha256"]) for item in expected["files"]
        }
        for path in sorted(committed_files.keys() | expected_files.keys()):
            if path not in committed_files:
                errors.append(f"unfrozen source file added: {path}")
            elif path not in expected_files:
                errors.append(f"frozen source file missing: {path}")
            elif committed_files[path] != expected_files[path]:
                errors.append(f"frozen source hash changed: {path}")
        for field in (
            "case_ids",
            "freeze_id",
            "frozen_on",
            "native_suite_included",
            "reporting_scope",
            "results_included",
            "schema_version",
            "status",
            "suite_sha256",
            "upstream_commit_sha",
            "upstream_task_ids",
        ):
            if committed.get(field) != expected.get(field):
                errors.append(f"freeze field changed: {field}")
    if canonical_bytes(committed) != target.read_bytes():
        errors.append("freeze manifest is not canonical UTF-8 JSON")
    return errors


def write_manifest(path: Path = MANIFEST_PATH) -> None:
    """Create the v1 manifest, refusing to rewrite a different frozen payload."""
    payload = build_manifest(path.parent)
    if payload["suite_sha256"] != EXPECTED_V1_SUITE_SHA256:
        raise RuntimeError(
            "current sources do not match the pinned v1 suite SHA-256; "
            "create a new freeze version"
        )
    rendered = canonical_bytes(payload)
    if path.exists() and path.read_bytes() != rendered:
        raise RuntimeError(
            f"{path} already exists with different bytes; create a new freeze "
            "version instead of rewriting v1"
        )
    path.write_bytes(rendered)


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--write",
        action="store_true",
        help="create freeze-v1.json; refuse to overwrite different bytes",
    )
    mode.add_argument(
        "--check",
        action="store_true",
        help="verify the committed manifest (default)",
    )
    return parser.parse_args()


def main() -> int:
    """Build or verify the external-suite freeze."""
    args = parse_args()
    try:
        if args.write:
            write_manifest()
            payload = read_json(MANIFEST_PATH)
            print(
                "external freeze: wrote "
                f"{payload['freeze_id']} - {len(payload['case_ids'])} cases, "
                f"{len(payload['files'])} files, {payload['suite_sha256'][:12]}"
            )
            return 0
        errors = validate_freeze_manifest()
    except (OSError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"ERROR: external freeze failed: {exc}", file=sys.stderr)
        return 1

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    payload = read_json(MANIFEST_PATH)
    print(
        "external freeze: pass - "
        f"{len(payload['case_ids'])} cases, {len(payload['files'])} files, "
        f"{payload['suite_sha256'][:12]}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
