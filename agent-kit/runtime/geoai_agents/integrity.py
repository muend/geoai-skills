"""Protect the complete pre-addon repository and verify a standalone skill install."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .core import KIT, contained, digest, file_hash, inventory, outcome, read_json, report


def base_manifest() -> dict[str, Any]:
    config = read_json(KIT / "package.json")
    path = KIT / "base.lock.json"
    if file_hash(path) != config["base_manifest_sha256"]:
        raise ValueError("base lock changed; do not regenerate it to make a check pass")
    return read_json(path)


def source_manifest() -> dict[str, Any]:
    config = read_json(KIT / "package.json")
    path = KIT / "source.lock.json"
    if file_hash(path) != config["source_manifest_sha256"]:
        raise ValueError("committed source lock changed")
    return read_json(path)


def verify_base(root: Path, *, skills_only: bool = False) -> dict[str, Any]:
    """Read-only comparison. skills_only root is the directory containing 18 skills."""
    base = base_manifest()
    expected = base["files"]
    if skills_only:
        expected = [dict(r, path=r["path"][7:]) for r in expected
                    if r["path"].startswith("skills/")]
    failures = []
    observed = {}
    for record in expected:
        try:
            path = contained(root, record["path"])
            actual_hash = file_hash(path) if path.is_file() else None
            observed[record["path"]] = actual_hash
            if actual_hash != record["sha256"]:
                failures.append(record["path"])
        except (OSError, ValueError):
            failures.append(record["path"])
    actual = set(inventory(root)) if skills_only else set()
    if not skills_only:
        for prefix in base["closed_directories"]:
            directory = contained(root, prefix)
            if directory.exists():
                actual.update(f"{prefix}/{p}" for p in inventory(directory)
                              if not (prefix == "evals" and p.startswith("runs/")))
    known = {r["path"] for r in expected}
    additions = sorted(actual - known)
    profile = "captured-worktree"
    # Accept a complete, separately pinned Git checkout, never per-file normalization.
    # Skill files and the native freeze remain identical in both approved profiles.
    if failures and not skills_only:
        committed = source_manifest()["files"]
        source_failures = [r["path"] for r in committed
                           if observed.get(r["path"]) != r["sha256"]]
        if not source_failures:
            failures = []
            profile = "committed-source"
    return report([outcome("base-integrity", "fail" if failures or additions else "pass",
                           "Frozen inputs match" if not failures and not additions
                           else "Frozen inputs changed or expanded",
                           changed=failures, added=additions,
                           baseline_profile=profile,
                           runtime_tree_sha256=base["base"]["runtime_tree_sha256"])])


def verify_inventory(root: Path, entries: list[dict[str, Any]], *, exact: bool = False
                     ) -> dict[str, Any]:
    findings = []
    names = [e["path"] for e in entries]
    if len(names) != len(set(names)):
        findings.append(outcome("artifact-integrity", "fail", "Duplicate file records"))
    for entry in entries:
        try:
            path = contained(root, entry["path"])
            valid = (path.is_file() and file_hash(path) == entry["sha256"]
                     and path.stat().st_size == entry["size"])
            state = "pass" if valid else "fail"
            findings.append(outcome("artifact-integrity", state, entry["path"]))
        except (OSError, ValueError) as exc:
            findings.append(outcome("artifact-integrity", "fail", str(exc)))
    if exact:
        extra = set(inventory(root)) - set(names) - {"manifest.json", "installation.json"}
        if extra:
            findings.append(outcome("artifact-integrity", "fail", "Unexpected package files",
                                    paths=sorted(extra)))
    return report(findings)


def verify_package(root: Path) -> dict[str, Any]:
    manifest = read_json(root / "manifest.json")
    if tree_digest(manifest["files"]) != manifest["agent_runtime_sha256"]:
        raise ValueError("package manifest aggregate mismatch")
    return verify_inventory(root, manifest["files"], exact=True)


def tree_digest(entries: list[dict[str, Any]]) -> str:
    return digest("".join(f"{r['sha256']}  {r['path']}\n"
                          for r in sorted(entries, key=lambda e: e["path"])).encode())
