"""Freeze runtime skill bytes without rewriting earlier evidence identities."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    # Direct execution adds tools/, not the repository root, to sys.path.
    sys.path.insert(0, str(ROOT))

from tools.build_skill_archives import (  # noqa: E402
    archive_inputs,
    package_version,
    skill_roots,
)

FREEZE_ROOT = ROOT / "evals" / "runtime-hashes"
REGISTRY_PATH = FREEZE_ROOT / "registry.json"
SCHEMA_VERSION = 2
FREEZE_ID_PATTERN = re.compile(r"^runtime-v[1-9][0-9]*$")
PINNED_MANIFEST_SHA256 = {
    "runtime-v1": "1948103a38d3b360365249dab5126b74d5c0e733482e7f84aefad72f84810375",
    "runtime-v2": "3e4f8bb26bc0c131e1890e4b7baa28fda2c3dc090ebc82f3849ea3072c6ebfcc",
}


def read_json(path: Path) -> dict[str, Any]:
    """Read a UTF-8 JSON object."""
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def canonical_bytes(payload: dict[str, Any]) -> bytes:
    """Serialize a document as deterministic UTF-8 JSON."""
    return (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    """Return a lowercase SHA-256 digest."""
    return hashlib.sha256(value).hexdigest()


def file_record(root: Path, path: Path) -> dict[str, Any]:
    """Describe one repository file by path, size, and raw-byte digest."""
    content = path.read_bytes()
    return {
        "path": path.relative_to(root).as_posix(),
        "sha256": sha256_bytes(content),
        "size_bytes": len(content),
    }


def records_sha256(records: list[dict[str, Any]]) -> str:
    """Hash sorted checksum-manifest lines for a collection of file records."""
    ordered = sorted(records, key=lambda item: str(item["path"]))
    material = "".join(
        f"{item['sha256']}  {item['path']}\n" for item in ordered
    ).encode("utf-8")
    return sha256_bytes(material)


def build_runtime_inventory(
    root: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return per-skill runtime records and shared release inputs."""
    root = root.resolve()
    skills: list[dict[str, Any]] = []
    for skill_root in skill_roots(root):
        files = [
            file_record(root, root / path)
            for path in archive_inputs(root, skill_root)
        ]
        skills.append(
            {
                "files": files,
                "runtime_tree_sha256": records_sha256(files),
                "skill": skill_root.name,
            }
        )

    license_path = root / "LICENSE"
    if not license_path.is_file() or license_path.is_symlink():
        raise FileNotFoundError("a regular root LICENSE file is required")
    return skills, [file_record(root, license_path)]


def flatten_records(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Index all runtime and shared records in a freeze by repository path."""
    records: dict[str, dict[str, Any]] = {}
    for skill in manifest.get("skills", []):
        for record in skill.get("files", []):
            records[str(record["path"])] = record
    for record in manifest.get("shared_release_inputs", []):
        records[str(record["path"])] = record
    return records


def lineage(
    parent: dict[str, Any],
    candidate_skills: list[dict[str, Any]],
    candidate_shared: list[dict[str, Any]],
    *,
    parent_manifest_sha256: str,
    candidate_package_version: str | None = None,
) -> dict[str, Any]:
    """Describe every byte-level change from a parent runtime freeze."""
    candidate = {
        "skills": candidate_skills,
        "shared_release_inputs": candidate_shared,
    }
    before = flatten_records(parent)
    after = flatten_records(candidate)
    changes: list[dict[str, Any]] = []
    for path in sorted(before.keys() | after.keys()):
        if path not in before:
            changes.append(
                {"after_sha256": after[path]["sha256"], "path": path, "status": "added"}
            )
        elif path not in after:
            changes.append(
                {"before_sha256": before[path]["sha256"], "path": path, "status": "removed"}
            )
        elif before[path]["sha256"] != after[path]["sha256"]:
            changes.append(
                {
                    "after_sha256": after[path]["sha256"],
                    "before_sha256": before[path]["sha256"],
                    "path": path,
                    "status": "modified",
                }
            )

    before_skills = {
        str(item["skill"]): str(item["runtime_tree_sha256"])
        for item in parent.get("skills", [])
    }
    after_skills = {
        str(item["skill"]): str(item["runtime_tree_sha256"])
        for item in candidate_skills
    }
    changed_skills = sorted(
        skill
        for skill in before_skills.keys() | after_skills.keys()
        if before_skills.get(skill) != after_skills.get(skill)
    )
    result: dict[str, Any] = {
        "changed_files": changes,
        "changed_skills": changed_skills,
        "parent_freeze_id": parent["freeze_id"],
        "parent_manifest_sha256": parent_manifest_sha256,
        "parent_runtime_tree_sha256": parent["runtime_tree_sha256"],
    }
    if candidate_package_version is not None:
        parent_version = str(parent.get("package_version", ""))
        if parent_version != candidate_package_version:
            result["package_version_change"] = {
                "after": candidate_package_version,
                "before": parent_version,
            }
    return result


def build_freeze(
    root: Path,
    freeze_id: str,
    *,
    parent: dict[str, Any] | None = None,
    parent_manifest_sha256: str | None = None,
) -> dict[str, Any]:
    """Build one deterministic runtime freeze from the current repository tree."""
    if FREEZE_ID_PATTERN.fullmatch(freeze_id) is None:
        raise ValueError(f"invalid runtime freeze id: {freeze_id}")
    root = root.resolve()
    runtime = current_runtime_fields(root)
    skills = runtime["skills"]
    shared = runtime["shared_release_inputs"]
    from tools.eval_runner import load_suite

    _cases, legacy_suite_sha256, _skill_names = load_suite(
        skills_dir=root / "skills",
        eval_cases_dir=root / "evals" / "cases",
        eval_schema_path=root / "evals" / "schema.json",
    )
    payload: dict[str, Any] = {
        "freeze_id": freeze_id,
        "hash_algorithm": "sha256",
        "hash_material": "sorted '<file-sha256>  <repository-path>\\n' UTF-8 lines",
        "kind": "geoai-runtime-tree-freeze",
        "legacy_native_suite_sha256": legacy_suite_sha256,
        "legacy_native_suite_schema_version": 1,
        "package_version": runtime["package_version"],
        "release_input_sha256": runtime["release_input_sha256"],
        "runtime_tree_sha256": runtime["runtime_tree_sha256"],
        "schema_version": SCHEMA_VERSION,
        "shared_release_inputs": shared,
        "skills": skills,
        "status": "frozen",
    }
    if parent is not None:
        if parent_manifest_sha256 is None:
            raise ValueError("parent manifest SHA-256 is required when parent is supplied")
        payload["lineage"] = lineage(
            parent,
            skills,
            shared,
            parent_manifest_sha256=parent_manifest_sha256,
            candidate_package_version=str(payload["package_version"]),
        )
    return payload


def current_runtime_fields(root: Path) -> dict[str, Any]:
    """Build source-derived fields without importing evaluation dependencies."""
    root = root.resolve()
    skills, shared = build_runtime_inventory(root)
    runtime_records = [record for skill in skills for record in skill["files"]]
    return {
        "package_version": package_version(root),
        "release_input_sha256": records_sha256(runtime_records + shared),
        "runtime_tree_sha256": records_sha256(runtime_records),
        "shared_release_inputs": shared,
        "skills": skills,
    }


def validate_internal_hashes(payload: dict[str, Any]) -> list[str]:
    """Check that a freeze's aggregate hashes follow from its recorded files."""
    errors: list[str] = []
    if payload.get("kind") != "geoai-runtime-tree-freeze":
        errors.append("invalid runtime freeze kind")
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append("invalid runtime freeze schema_version")

    runtime_records: list[dict[str, Any]] = []
    for skill in payload.get("skills", []):
        files = skill.get("files", [])
        runtime_records.extend(files)
        if skill.get("runtime_tree_sha256") != records_sha256(files):
            errors.append(f"skill runtime hash mismatch: {skill.get('skill')}")
    shared = payload.get("shared_release_inputs", [])
    if payload.get("runtime_tree_sha256") != records_sha256(runtime_records):
        errors.append("aggregate runtime_tree_sha256 mismatch")
    if payload.get("release_input_sha256") != records_sha256(runtime_records + shared):
        errors.append("aggregate release_input_sha256 mismatch")
    return errors


def registry_entry(
    freeze_id: str,
    path: Path,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Build the immutable registry record for one canonical manifest."""
    rendered = canonical_bytes(payload)
    return {
        "freeze_id": freeze_id,
        "legacy_native_suite_sha256": payload["legacy_native_suite_sha256"],
        "manifest_path": path.name,
        "manifest_sha256": sha256_bytes(rendered),
        "release_input_sha256": payload["release_input_sha256"],
        "runtime_tree_sha256": payload["runtime_tree_sha256"],
    }


def validate_registry(
    root: Path = ROOT,
    registry_path: Path = REGISTRY_PATH,
    *,
    compare_current_sources: bool = True,
    compare_legacy_suite: bool = True,
) -> list[str]:
    """Validate all immutable freezes and compare the current one with source bytes."""
    if not registry_path.is_file():
        return [f"missing runtime hash registry: {registry_path}"]
    try:
        registry = read_json(registry_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [f"cannot read runtime hash registry: {exc}"]

    errors: list[str] = []
    if canonical_bytes(registry) != registry_path.read_bytes():
        errors.append("runtime hash registry is not canonical UTF-8 JSON")
    if registry.get("kind") != "geoai-runtime-tree-registry":
        errors.append("invalid runtime hash registry kind")
    if registry.get("schema_version") != 1:
        errors.append("invalid runtime hash registry schema_version")

    entries = registry.get("freezes", [])
    ids = [entry.get("freeze_id") for entry in entries]
    if len(ids) != len(set(ids)):
        errors.append("runtime hash registry contains duplicate freeze ids")
    current_id = registry.get("current_freeze_id")
    entry_by_id = {entry.get("freeze_id"): entry for entry in entries}
    if current_id not in entry_by_id:
        errors.append("current runtime freeze is not registered")
        return errors
    registered_ids = {str(freeze_id) for freeze_id in ids}
    pinned_ids = set(PINNED_MANIFEST_SHA256)
    for freeze_id in sorted(registered_ids - pinned_ids):
        errors.append(f"runtime freeze is not pinned in code: {freeze_id}")
    for freeze_id in sorted(pinned_ids - registered_ids):
        errors.append(f"pinned runtime freeze is missing from registry: {freeze_id}")

    payload_by_id: dict[str, dict[str, Any]] = {}
    for entry in entries:
        freeze_id = str(entry.get("freeze_id", ""))
        expected_name = f"{freeze_id}.json"
        if FREEZE_ID_PATTERN.fullmatch(freeze_id) is None:
            errors.append(f"invalid registered runtime freeze id: {freeze_id}")
            continue
        if entry.get("manifest_path") != expected_name:
            errors.append(f"invalid runtime freeze manifest path: {freeze_id}")
            continue
        manifest_path = registry_path.parent / expected_name
        if not manifest_path.is_file():
            errors.append(f"missing runtime freeze: {manifest_path.name}")
            continue
        raw = manifest_path.read_bytes()
        if sha256_bytes(raw) != entry.get("manifest_sha256"):
            errors.append(f"immutable runtime freeze changed: {manifest_path.name}")
        if entry.get("manifest_sha256") != PINNED_MANIFEST_SHA256.get(freeze_id):
            errors.append(f"runtime freeze does not match its code pin: {freeze_id}")
        try:
            payload = read_json(manifest_path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"cannot read runtime freeze {manifest_path.name}: {exc}")
            continue
        payload_by_id[str(entry.get("freeze_id"))] = payload
        if canonical_bytes(payload) != raw:
            errors.append(f"runtime freeze is not canonical UTF-8 JSON: {manifest_path.name}")
        errors.extend(validate_internal_hashes(payload))
        for field in (
            "freeze_id",
            "legacy_native_suite_sha256",
            "release_input_sha256",
            "runtime_tree_sha256",
        ):
            if payload.get(field) != entry.get(field):
                errors.append(f"registry field mismatch for {manifest_path.name}: {field}")

    current = payload_by_id.get(str(current_id))
    current_entry = entry_by_id[current_id]
    if current is not None and compare_current_sources:
        parent = None
        parent_digest = None
        declared_lineage = current.get("lineage")
        if isinstance(declared_lineage, dict):
            parent_id = str(declared_lineage.get("parent_freeze_id", ""))
            parent = payload_by_id.get(parent_id)
            parent_entry = entry_by_id.get(parent_id)
            if parent is None or parent_entry is None:
                errors.append("current runtime freeze lineage parent is unavailable")
            else:
                parent_digest = str(parent_entry["manifest_sha256"])
        if not errors:
            try:
                if compare_legacy_suite:
                    expected = build_freeze(
                        root,
                        str(current_id),
                        parent=parent,
                        parent_manifest_sha256=parent_digest,
                    )
                    if expected != current:
                        errors.append(
                            "current runtime sources differ from the registered freeze"
                        )
                    expected_entry = registry_entry(
                        str(current_id),
                        registry_path.parent / str(current_entry["manifest_path"]),
                        expected,
                    )
                    if expected_entry != current_entry:
                        errors.append("current runtime registry entry is stale")
                else:
                    expected_runtime = current_runtime_fields(root)
                    for field, value in expected_runtime.items():
                        if current.get(field) != value:
                            errors.append(
                                "current runtime sources differ from the registered "
                                f"freeze: {field}"
                            )
            except (OSError, TypeError, ValueError) as exc:
                errors.append(f"cannot rebuild current runtime freeze: {exc}")
    return errors


def initialize_registry(root: Path = ROOT, freeze_id: str = "runtime-v1") -> None:
    """Create the first immutable runtime freeze and its registry."""
    freeze_root = root / "evals" / "runtime-hashes"
    registry_path = freeze_root / "registry.json"
    manifest_path = freeze_root / f"{freeze_id}.json"
    if freeze_root.exists() and any(freeze_root.iterdir()):
        raise FileExistsError("runtime hash registry already exists")
    payload = build_freeze(root, freeze_id)
    registry = {
        "current_freeze_id": freeze_id,
        "freezes": [registry_entry(freeze_id, manifest_path, payload)],
        "kind": "geoai-runtime-tree-registry",
        "schema_version": 1,
    }
    freeze_root.mkdir(parents=True, exist_ok=True)
    manifest_path.write_bytes(canonical_bytes(payload))
    registry_path.write_bytes(canonical_bytes(registry))


def write_next_freeze(root: Path, freeze_id: str) -> None:
    """Append a new current freeze while retaining every earlier manifest."""
    registry_path = root / "evals" / "runtime-hashes" / "registry.json"
    errors = validate_registry(
        root,
        registry_path,
        compare_current_sources=False,
    )
    if errors:
        raise RuntimeError("existing registry is invalid: " + "; ".join(errors))
    registry = read_json(registry_path)
    if any(entry["freeze_id"] == freeze_id for entry in registry["freezes"]):
        raise ValueError(f"runtime freeze already exists: {freeze_id}")
    parent_entry = next(
        entry
        for entry in registry["freezes"]
        if entry["freeze_id"] == registry["current_freeze_id"]
    )
    parent_path = registry_path.parent / parent_entry["manifest_path"]
    parent = read_json(parent_path)
    payload = build_freeze(
        root,
        freeze_id,
        parent=parent,
        parent_manifest_sha256=parent_entry["manifest_sha256"],
    )
    if (
        not payload["lineage"]["changed_files"]
        and "package_version_change" not in payload["lineage"]
    ):
        raise ValueError("runtime sources are unchanged; a new freeze would add no evidence")
    manifest_path = registry_path.parent / f"{freeze_id}.json"
    if manifest_path.exists():
        raise FileExistsError(f"refusing to overwrite runtime freeze: {manifest_path}")
    manifest_path.write_bytes(canonical_bytes(payload))
    registry["freezes"].append(registry_entry(freeze_id, manifest_path, payload))
    registry["current_freeze_id"] = freeze_id
    registry_path.write_bytes(canonical_bytes(registry))


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--initialize", action="store_true")
    mode.add_argument("--write-next", metavar="FREEZE_ID")
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--check-runtime-only", action="store_true")
    return parser.parse_args()


def main() -> int:
    """Create, extend, or verify the runtime hash registry."""
    args = parse_args()
    try:
        if args.initialize:
            initialize_registry()
            print("runtime hashes: initialized runtime-v1")
            return 0
        if args.write_next:
            write_next_freeze(ROOT, args.write_next)
            print(f"runtime hashes: wrote {args.write_next}")
            return 0
        errors = validate_registry(compare_legacy_suite=not args.check_runtime_only)
    except (OSError, RuntimeError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: runtime hash registry failed: {exc}", file=sys.stderr)
        return 1
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    registry = read_json(REGISTRY_PATH)
    current = next(
        item
        for item in registry["freezes"]
        if item["freeze_id"] == registry["current_freeze_id"]
    )
    print(
        "runtime hashes: pass - "
        f"{len(registry['freezes'])} freeze(s), current "
        f"{registry['current_freeze_id']} {current['runtime_tree_sha256'][:12]}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
