"""Contracts for the public release-candidate and clean-install runbook."""

from __future__ import annotations

from pathlib import Path

from tools import build_skill_archives as archives

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
RUNBOOK = ROOT / "RELEASING.md"


def test_runbook_tracks_the_current_package_version() -> None:
    text = RUNBOOK.read_text(encoding="utf-8")
    version = archives.package_version(ROOT)

    assert version == "0.2.0"
    assert f"`v{version}` does not already exist" in text
    assert f"after publication, use\n`v{version}`" in text


def test_runbook_covers_every_documented_installation_surface() -> None:
    text = RUNBOOK.read_text(encoding="utf-8")
    required_commands = (
        "npx skills add muend/geoai-skills --list",
        "-a claude-code --copy -y",
        "-a codex --copy -y",
        "claude plugin marketplace add muend/geoai-skills",
        "python tools/build_openai_plugin_bundle.py",
        "gh skill publish --dry-run",
        "gh skill preview muend/geoai-skills remote-sensing-analysis",
        "remote-sensing-analysis@<candidate-ref>",
        "-a github-copilot --copy -y",
    )

    assert all(command in text for command in required_commands)
    assert "Claude.ai / Claude desktop ZIP" in text
    assert "Generic Agent Skills runtime" in text
    assert "arcgis-mcp-bridge" in text
    assert "DISABLE_TELEMETRY=1" in text


def test_runbook_separates_candidate_verification_from_publication() -> None:
    text = RUNBOOK.read_text(encoding="utf-8")
    normalized = " ".join(text.split())

    assert "It cannot create a tag, GitHub Release, or release asset." in normalized
    assert "Publishing requires explicit maintainer approval" in text
    assert "do not move the tag or overwrite assets" in text
    assert "API keys" in text
    assert "private benchmark prompts" in text


def test_readme_exposes_copilot_and_release_guidance() -> None:
    text = README.read_text(encoding="utf-8")

    assert "### GitHub Copilot" in text
    assert "GitHub CLI 2.90.0 or later" in text
    assert "gh skill preview muend/geoai-skills remote-sensing-analysis" in text
    assert "-a github-copilot" in text
    assert "[RELEASING.md](RELEASING.md)" in text
