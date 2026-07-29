"""Security contract for the skill-archive release workflow."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "release-skill-archives.yml"


def workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_release_workflow_is_release_only_and_uses_exact_tag() -> None:
    text = workflow_text()

    assert "release:" in text
    assert "types: [published]" in text
    assert "workflow_dispatch:" not in text
    assert "ref: ${{ github.event.release.tag_name }}" in text
    assert 'TAG: "${{ github.event.release.tag_name }}"' in text


def test_release_workflow_has_narrow_write_scope() -> None:
    text = workflow_text()

    assert "permissions:\n  contents: read" in text
    assert "permissions:\n      contents: write" in text
    assert "persist-credentials: false" in text
    assert "GH_TOKEN: ${{ github.token }}" in text


def test_release_workflow_builds_checksums_without_overwrite() -> None:
    text = workflow_text()

    assert "tools/build_skill_archives.py" in text
    assert "--expected-version" in text
    assert "sha256sum --check SHA256SUMS" in text
    assert "dist/skills/*.zip" in text
    assert "dist/skills/SHA256SUMS" in text
    assert "--clobber" not in text
