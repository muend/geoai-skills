"""Tests for immutable, full-runtime skill hash lineage."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from tools.build_runtime_hash_registry import (
    PINNED_MANIFEST_SHA256,
    REGISTRY_PATH,
    ROOT,
    build_runtime_inventory,
    canonical_bytes,
    lineage,
    records_sha256,
    sha256_bytes,
    validate_internal_hashes,
    validate_registry,
)
from tools.build_skill_archives import archive_inputs, skill_roots
from tools.eval_runner import load_suite


def read_json(path: Path) -> dict:
    """Read one test JSON object."""
    return json.loads(path.read_text(encoding="utf-8"))


def test_committed_registry_matches_the_complete_runtime_tree() -> None:
    """The current freeze must be byte-canonical and match current source files."""
    assert validate_registry() == []


def test_runtime_hash_documents_are_lf_normalized_on_every_checkout() -> None:
    """Pinned manifest bytes must not vary between Windows and POSIX checkouts."""
    attributes = (ROOT / ".gitattributes").read_text(encoding="utf-8")

    assert "LICENSE text eol=lf" in attributes.splitlines()
    assert "evals/runtime-hashes/*.json text eol=lf" in attributes.splitlines()


def test_release_runtime_check_needs_no_site_packages() -> None:
    """The release job can verify package inputs before installing dependencies."""
    completed = subprocess.run(  # noqa: S603 - executable and arguments are fixed.
        [
            sys.executable,
            "-S",
            str(ROOT / "tools" / "build_runtime_hash_registry.py"),
            "--check-runtime-only",
        ],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert "runtime hashes: pass" in completed.stdout


def test_inventory_uses_exactly_the_archive_runtime_inputs() -> None:
    """Benchmark provenance and release packaging must cover the same skill files."""
    skills, shared = build_runtime_inventory(ROOT)
    actual = {
        record["path"]
        for skill in skills
        for record in skill["files"]
    }
    expected = {
        path.as_posix()
        for skill_root in skill_roots(ROOT)
        for path in archive_inputs(ROOT, skill_root)
    }
    assert actual == expected
    assert [record["path"] for record in shared] == ["LICENSE"]
    assert not any("/evals/" in path or "private-planning" in path for path in actual)


def test_reference_change_alters_runtime_hash_without_rewriting_legacy_identity(
    tmp_path: Path,
) -> None:
    """A previously invisible reference edit is visible to schema v2."""
    root = tmp_path / "repo"
    skill = root / "skills" / "demo"
    reference = skill / "references" / "guide.md"
    reference.parent.mkdir(parents=True)
    (skill / "SKILL.md").write_text("---\nname: demo\n---\n", encoding="utf-8")
    reference.write_text("first\n", encoding="utf-8")
    (root / "LICENSE").write_text("MIT\n", encoding="utf-8")

    before, _shared = build_runtime_inventory(root)
    legacy_skill_sha = sha256_bytes((skill / "SKILL.md").read_bytes())
    reference.write_text("second\n", encoding="utf-8")
    after, _shared = build_runtime_inventory(root)

    assert before[0]["runtime_tree_sha256"] != after[0]["runtime_tree_sha256"]
    assert sha256_bytes((skill / "SKILL.md").read_bytes()) == legacy_skill_sha


def test_internal_validation_detects_a_rewritten_frozen_file_record() -> None:
    """Changing a recorded file digest without rebuilding aggregates must fail."""
    registry = read_json(REGISTRY_PATH)
    current = next(
        entry
        for entry in registry["freezes"]
        if entry["freeze_id"] == registry["current_freeze_id"]
    )
    payload = read_json(REGISTRY_PATH.parent / current["manifest_path"])
    payload["skills"][0]["files"][0]["sha256"] = "0" * 64

    errors = validate_internal_hashes(payload)

    assert any("skill runtime hash mismatch" in error for error in errors)
    assert "aggregate runtime_tree_sha256 mismatch" in errors


def test_lineage_names_changed_skill_and_file_without_mutating_parent() -> None:
    """A candidate records an auditable delta while preserving its parent bytes."""
    registry = read_json(REGISTRY_PATH)
    current = next(
        entry
        for entry in registry["freezes"]
        if entry["freeze_id"] == registry["current_freeze_id"]
    )
    parent_path = REGISTRY_PATH.parent / current["manifest_path"]
    parent_bytes = parent_path.read_bytes()
    parent = read_json(parent_path)
    candidate_skills = json.loads(json.dumps(parent["skills"]))
    changed = candidate_skills[0]
    changed["files"][0]["sha256"] = "0" * 64
    changed["runtime_tree_sha256"] = records_sha256(changed["files"])

    delta = lineage(
        parent,
        candidate_skills,
        parent["shared_release_inputs"],
        parent_manifest_sha256=current["manifest_sha256"],
    )

    assert delta["changed_skills"] == [changed["skill"]]
    assert delta["changed_files"] == [
        {
            "after_sha256": "0" * 64,
            "before_sha256": parent["skills"][0]["files"][0]["sha256"],
            "path": parent["skills"][0]["files"][0]["path"],
            "status": "modified",
        }
    ]
    assert parent_path.read_bytes() == parent_bytes


def test_version_only_release_is_recorded_as_a_freeze_not_a_deadlock() -> None:
    """An evidence-only release changes no skill byte and must still be freezable.

    The release preflight compares the package version, so a version bump makes
    the current freeze stale; if a new freeze also refused an unchanged tree, no
    release could ever be cut without editing a skill. The freeze records the
    version delta and the identical tree hash instead.
    """
    registry = read_json(REGISTRY_PATH)
    current = next(
        entry
        for entry in registry["freezes"]
        if entry["freeze_id"] == registry["current_freeze_id"]
    )
    parent_path = REGISTRY_PATH.parent / current["manifest_path"]
    parent = read_json(parent_path)

    delta = lineage(
        parent,
        parent["skills"],
        parent["shared_release_inputs"],
        parent_manifest_sha256=current["manifest_sha256"],
        candidate_package_version="99.99.99",
    )

    assert delta["changed_files"] == []
    assert delta["changed_skills"] == []
    assert delta["package_version_change"] == {
        "after": "99.99.99",
        "before": parent["package_version"],
    }

    unchanged = lineage(
        parent,
        parent["skills"],
        parent["shared_release_inputs"],
        parent_manifest_sha256=current["manifest_sha256"],
        candidate_package_version=str(parent["package_version"]),
    )

    assert "package_version_change" not in unchanged


def test_registry_records_the_existing_native_suite_hash_unchanged() -> None:
    """Adding runtime provenance must not redefine the legacy native suite SHA."""
    registry = read_json(REGISTRY_PATH)
    current = next(
        entry
        for entry in registry["freezes"]
        if entry["freeze_id"] == registry["current_freeze_id"]
    )
    _cases, suite_sha256, _skills = load_suite()

    assert current["legacy_native_suite_sha256"] == suite_sha256


def test_registry_and_freeze_are_canonical_and_self_consistent() -> None:
    """Every registered manifest digest must match its immutable bytes."""
    registry = read_json(REGISTRY_PATH)
    assert REGISTRY_PATH.read_bytes() == canonical_bytes(registry)
    assert {entry["freeze_id"] for entry in registry["freezes"]} == set(
        PINNED_MANIFEST_SHA256
    )
    for entry in registry["freezes"]:
        path = REGISTRY_PATH.parent / entry["manifest_path"]
        payload = read_json(path)
        assert path.read_bytes() == canonical_bytes(payload)
        assert sha256_bytes(path.read_bytes()) == entry["manifest_sha256"]
        assert entry["manifest_sha256"] == PINNED_MANIFEST_SHA256[entry["freeze_id"]]
        records = [record for skill in payload["skills"] for record in skill["files"]]
        assert records_sha256(records) == entry["runtime_tree_sha256"]
