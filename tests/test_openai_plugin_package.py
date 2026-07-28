"""Contract tests for the skills-only OpenAI plugin package."""

from __future__ import annotations

import json
import re
from pathlib import Path
from zipfile import ZipFile

from tools import build_openai_plugin_bundle as bundle

ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = ROOT / ".codex-plugin" / "plugin.json"
SKILLS_ROOT = ROOT / "skills"
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


def manifest() -> dict:
    payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def test_manifest_declares_a_skills_only_plugin() -> None:
    data = manifest()

    assert data["name"] == "geoai-skills"
    assert SEMVER.fullmatch(data["version"])
    assert data["skills"] == "./skills/"
    assert data["license"] == "MIT"
    assert "apps" not in data
    assert "mcpServers" not in data


def test_manifest_and_claude_package_share_publisher_and_version() -> None:
    data = manifest()
    claude = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text("utf-8"))

    assert data["version"] == claude["version"]
    assert data["author"]["name"] == claude["author"]["name"]


def test_interface_is_submission_ready() -> None:
    interface = manifest()["interface"]
    required = {
        "displayName",
        "shortDescription",
        "longDescription",
        "developerName",
        "category",
        "capabilities",
        "websiteURL",
        "privacyPolicyURL",
        "termsOfServiceURL",
        "defaultPrompt",
    }

    assert required <= interface.keys()
    assert interface["developerName"] == manifest()["author"]["name"]
    assert interface["capabilities"]
    assert 1 <= len(interface["defaultPrompt"]) <= 3
    assert all(len(prompt) <= 128 for prompt in interface["defaultPrompt"])
    assert all(
        interface[field].startswith("https://")
        for field in ("websiteURL", "privacyPolicyURL", "termsOfServiceURL")
    )


def test_public_policy_documents_exist_and_name_support_routes() -> None:
    privacy = (ROOT / "PRIVACY.md").read_text(encoding="utf-8")
    terms = (ROOT / "TERMS.md").read_text(encoding="utf-8")

    assert "does not automatically collect" in privacy
    assert "GitHub Issues" in privacy
    assert "private vulnerability reporting" in privacy
    assert "MIT License" in terms
    assert "No benchmark or test result guarantees" in terms
    assert "GitHub Issues" in terms


def test_all_eighteen_skills_have_openai_metadata() -> None:
    skill_roots = sorted(path for path in SKILLS_ROOT.iterdir() if path.is_dir())

    assert len(skill_roots) == 18
    for skill_root in skill_roots:
        assert (skill_root / "SKILL.md").is_file()
        assert (skill_root / "agents" / "openai.yaml").is_file()


def test_bundle_contains_runtime_files_but_not_evaluation_material(tmp_path: Path) -> None:
    output, _ = bundle.build_bundle(ROOT, tmp_path / "plugin.zip")

    with ZipFile(output) as archive:
        names = set(archive.namelist())

    assert ".codex-plugin/plugin.json" in names
    assert "PRIVACY.md" in names
    assert "SECURITY.md" in names
    assert "TERMS.md" in names
    assert "skills/geoai-orchestrator/SKILL.md" in names
    assert "skills/geo-data-engineering/scripts/clean_vector.py" in names
    assert "skills/mcda-suitability-analysis/scripts/ahp_weights.py" in names
    assert sum(name.endswith("/SKILL.md") for name in names) == 18
    assert not any("/evals/" in name for name in names)
    assert not any("__pycache__" in name or name.endswith(".pyc") for name in names)
    forbidden_roots = (
        "private-planning/",
        ".github/",
        "benchmarks/",
        "evals/",
        "tests/",
        "tools/",
    )
    assert not any(name.startswith(forbidden_roots) for name in names)


def test_bundle_is_byte_deterministic(tmp_path: Path) -> None:
    first, first_digest = bundle.build_bundle(ROOT, tmp_path / "first.zip")
    second, second_digest = bundle.build_bundle(ROOT, tmp_path / "second.zip")

    assert first_digest == second_digest
    assert first.read_bytes() == second.read_bytes()
