"""Contract tests for deterministic per-skill release archives."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from zipfile import ZipFile

import pytest

from tools import build_skill_archives as archives

ROOT = Path(__file__).resolve().parent.parent


def test_package_versions_match() -> None:
    """All four release manifests must declare one SemVer.

    This previously asserted a hard-coded version string, which broke on every
    release bump while protecting nothing: `package_version` already raises on
    drift between pyproject, the Codex manifest and the Claude manifest. The
    check now covers what the assertion could not — `marketplace.json`, which
    `package_version` does not read even though RELEASING.md's first invariant
    requires it to agree.
    """
    version = archives.package_version(ROOT)

    assert re.fullmatch(r"\d+\.\d+\.\d+", version), version

    marketplace = json.loads(
        (ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8")
    )
    declared = {plugin.get("version") for plugin in marketplace.get("plugins", [])}

    assert declared == {version}, (
        f"marketplace.json declares {declared}, the other manifests declare {version}"
    )


def test_builds_all_skills_with_uploadable_root_layout(tmp_path: Path) -> None:
    built = archives.build_archives(ROOT, tmp_path / "release")
    version = archives.package_version(ROOT)

    assert len(built) == 18
    for artifact in built:
        assert artifact.path.name.startswith("geoai-skills-")
        assert artifact.path.name.endswith(f"-{version}.zip")
        assert artifact.sha256 == hashlib.sha256(artifact.path.read_bytes()).hexdigest()

        with ZipFile(artifact.path) as archive:
            names = archive.namelist()

        skill_md = [name for name in names if name.endswith("/SKILL.md")]
        assert len(skill_md) == 1
        skill_root = skill_md[0].removesuffix("/SKILL.md")
        assert "/" not in skill_root
        assert all(name.startswith(f"{skill_root}/") for name in names)
        assert f"{skill_root}/LICENSE" in names
        assert not any(name.startswith("skills/") for name in names)
        assert not any("/evals/" in name for name in names)
        assert not any("__pycache__" in name or name.endswith(".pyc") for name in names)
        assert not any(name.startswith("private-planning/") for name in names)


def test_runtime_assets_are_preserved() -> None:
    geo_data = ROOT / "skills" / "geo-data-engineering"
    inputs = {
        path.as_posix()
        for path in archives.archive_inputs(ROOT, geo_data)
    }

    assert "skills/geo-data-engineering/SKILL.md" in inputs
    assert "skills/geo-data-engineering/agents/openai.yaml" in inputs
    assert "skills/geo-data-engineering/references/authoritative-sources.md" in inputs
    assert "skills/geo-data-engineering/scripts/clean_vector.py" in inputs
    assert not any("/evals/" in path for path in inputs)


def test_archives_and_checksum_manifest_are_byte_deterministic(tmp_path: Path) -> None:
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"

    first = archives.build_archives(ROOT, first_dir)
    second = archives.build_archives(ROOT, second_dir)

    assert [artifact.sha256 for artifact in first] == [
        artifact.sha256 for artifact in second
    ]
    assert [artifact.path.read_bytes() for artifact in first] == [
        artifact.path.read_bytes() for artifact in second
    ]
    assert (first_dir / "SHA256SUMS").read_bytes() == (
        second_dir / "SHA256SUMS"
    ).read_bytes()


def test_checksum_manifest_is_sorted_and_complete(tmp_path: Path) -> None:
    output_dir = tmp_path / "release"
    built = archives.build_archives(ROOT, output_dir)
    lines = (output_dir / "SHA256SUMS").read_text(encoding="utf-8").splitlines()

    assert len(lines) == 18
    assert lines == sorted(lines, key=lambda line: line.split("  ", 1)[1])
    assert lines == [
        f"{artifact.sha256}  {artifact.path.name}" for artifact in built
    ]


def test_output_cannot_enter_skill_source_tree() -> None:
    with pytest.raises(ValueError, match="outside the skills source tree"):
        archives.build_archives(ROOT, ROOT / "skills" / "generated")


def test_unclassified_skill_input_fails_closed(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    skill_root = root / "skills" / "example"
    skill_root.mkdir(parents=True)
    (skill_root / "SKILL.md").write_text("---\nname: example\n---\n", encoding="utf-8")
    (skill_root / "private-notes.txt").write_text("do not ship", encoding="utf-8")

    with pytest.raises(ValueError, match="unclassified package inputs"):
        archives.archive_inputs(root, skill_root)
