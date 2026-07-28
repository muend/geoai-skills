"""Contract tests for the Claude Code plugin marketplace package."""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLAUDE_ROOT = ROOT / ".claude-plugin"
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


def load_json(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def test_claude_plugin_manifest_is_distribution_ready() -> None:
    plugin = load_json(CLAUDE_ROOT / "plugin.json")

    assert plugin["name"] == "geoai"
    assert plugin["displayName"] == "GeoAI Skills"
    assert SEMVER.fullmatch(plugin["version"])
    assert plugin["description"]
    assert plugin["author"]["name"] == "Muhammed Enes Duran"
    assert plugin["homepage"] == "https://github.com/muend/geoai-skills"
    assert plugin["repository"] == plugin["homepage"]
    assert plugin["license"] == "MIT"
    assert plugin["skills"] == "./skills/"
    assert {"geoai", "geospatial", "remote-sensing"} <= set(plugin["keywords"])
    assert "mcpServers" not in plugin
    assert "hooks" not in plugin


def test_marketplace_has_one_local_versioned_plugin() -> None:
    marketplace = load_json(CLAUDE_ROOT / "marketplace.json")
    plugin = load_json(CLAUDE_ROOT / "plugin.json")

    assert marketplace["name"] == "geoai-skills"
    assert marketplace["description"]
    assert marketplace["owner"]["name"] == plugin["author"]["name"]
    assert len(marketplace["plugins"]) == 1

    entry = marketplace["plugins"][0]
    assert entry["name"] == plugin["name"]
    assert entry["displayName"] == plugin["displayName"]
    assert entry["source"] == "./"
    assert entry["version"] == plugin["version"]
    assert entry["description"]
    assert entry["category"] == "data-science"
    assert {"geoai", "gis", "remote-sensing"} <= set(entry["tags"])


def test_claude_package_discovers_all_eighteen_skills() -> None:
    plugin = load_json(CLAUDE_ROOT / "plugin.json")
    skills_root = ROOT / plugin["skills"].removeprefix("./")
    skill_files = sorted(skills_root.glob("*/SKILL.md"))

    assert len(skill_files) == 18
    assert skills_root / "geoai-orchestrator" / "SKILL.md" in skill_files
    assert skills_root / "arcgis-pro-automation" / "SKILL.md" in skill_files


def test_release_version_is_consistent_across_public_packages() -> None:
    claude = load_json(CLAUDE_ROOT / "plugin.json")
    marketplace = load_json(CLAUDE_ROOT / "marketplace.json")
    openai = load_json(ROOT / ".codex-plugin" / "plugin.json")
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

    version = claude["version"]
    assert marketplace["plugins"][0]["version"] == version
    assert openai["version"] == version
    assert pyproject["project"]["version"] == version
    assert f"## [{version}]" in changelog


def test_readme_documents_both_claude_install_surfaces() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "claude plugin marketplace add muend/geoai-skills" in readme
    assert "claude plugin install geoai@geoai-skills" in readme
    assert "/plugin marketplace add muend/geoai-skills" in readme
    assert "/plugin install geoai@geoai-skills" in readme
    assert "/geoai:remote-sensing-analysis" in readme
    assert "Until the public Plugin Directory listing is approved" not in readme
