"""Security contract for the skill-archive release workflow."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "release-skill-archives.yml"


def workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_workflow_has_non_publishing_rc_path_and_exact_tag_release() -> None:
    text = workflow_text()

    assert "release:" in text
    assert "types: [published]" in text
    assert "workflow_dispatch:" in text
    assert "verify-release-candidate:" in text
    assert "if: github.event_name == 'workflow_dispatch'" in text
    assert 'VERSION: "${{ inputs.version }}"' in text
    assert "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a" in text
    assert "retention-days: 7" in text
    assert "if: github.event_name == 'release'" in text
    assert "ref: ${{ github.event.release.tag_name }}" in text
    assert 'TAG: "${{ github.event.release.tag_name }}"' in text


def test_release_workflow_has_narrow_write_scope() -> None:
    text = workflow_text()
    candidate_job, publish_job = text.split("\n  publish:", maxsplit=1)

    assert "permissions:\n  contents: read" in text
    assert text.count("contents: write") == 1
    assert "contents: write" not in candidate_job
    assert "gh release upload" not in candidate_job
    assert "contents: write" in publish_job
    assert "gh release upload" in publish_job
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
