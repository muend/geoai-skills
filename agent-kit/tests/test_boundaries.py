import shutil
import tomllib
from zipfile import ZipFile

import pytest
import yaml

from geoai_agents.core import KIT, contained, file_hash, read_json
from geoai_agents.distribution import adapters, build, install, render
from geoai_agents.integrity import base_manifest, source_manifest, verify_base, verify_inventory


@pytest.fixture(scope="module")
def core_copy(tmp_path_factory):
    root = tmp_path_factory.mktemp("frozen-core")
    for entry in base_manifest()["files"]:
        destination = root / entry["path"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(KIT.parent / entry["path"], destination)
    return root


def test_original_core_and_all_18_skills_are_unchanged():
    assert verify_base(KIT.parent)["exit_code"] == 0
    assert verify_base(KIT.parent / "skills", skills_only=True)["exit_code"] == 0
    assert len(read_json(KIT / "bindings.json")) == 18


def test_committed_checkout_and_captured_worktree_are_distinct_pinned_profiles(tmp_path):
    source = {r["path"]: r for r in source_manifest()["files"]}
    for entry in base_manifest()["files"]:
        raw = (KIT.parent / entry["path"]).read_bytes()
        if entry["sha256"] != source[entry["path"]]["sha256"]:
            assert not entry["path"].startswith("skills/")
            raw = raw.replace(b"\r\n", b"\n")
        path = tmp_path / entry["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    assert verify_base(tmp_path)["exit_code"] == 0
    (tmp_path / "tools/verify.py").write_bytes(b"changed")
    assert verify_base(tmp_path)["exit_code"] == 1


@pytest.mark.parametrize("name", [
    "skills/network-accessibility-analysis/SKILL.md",
    "skills/network-accessibility-analysis/agents/openai.yaml",
    "skills/network-accessibility-analysis/references/authoritative-sources.md",
    "evals/cases/network-accessibility-analysis/evals.json",
    "evals/schema.json", "tools/eval_runner.py", "evals/runtime-hashes/runtime-v2.json",
])
def test_changed_core_bytes_are_detected_without_changing_original(core_copy, name):
    path = core_copy / name
    original = path.read_bytes()
    try:
        path.write_bytes(original + b"\nchanged\n")
        result = verify_base(core_copy)
        assert result["exit_code"] == 1
        assert name in result["results"][0]["detail"]["changed"]
    finally:
        path.write_bytes(original)


def test_addon_outside_core_does_not_change_base_identity(core_copy):
    path = core_copy / "agent-kit" / "new-role.md"
    path.parent.mkdir()
    path.write_text("New role", encoding="utf-8")
    assert verify_base(core_copy)["exit_code"] == 0


def test_new_file_inside_frozen_skill_is_detected(core_copy):
    path = core_copy / "skills/network-accessibility-analysis/agents/new-agent.md"
    path.write_text("new agent", encoding="utf-8")
    try:
        assert verify_base(core_copy)["exit_code"] == 1
    finally:
        path.unlink()


def test_adapter_generation_is_current_and_parseable():
    assert render(check=True) == []
    generated = adapters()
    assert len(generated) == 12
    for name, raw in generated.items():
        if name.endswith(".toml"):
            value = tomllib.loads(raw.decode())
            assert value["name"].startswith("geoai-")
            assert "model" not in value
            assert "developer_instructions" in value
        else:
            frontmatter = raw.decode().split("---", 2)[1]
            value = yaml.safe_load(frontmatter)
            assert value["name"].startswith("geoai-")
            assert value["model"] == "inherit"
            assert value["maxTurns"] == 12


def test_preview_is_read_only_and_install_never_overwrites(tmp_path):
    target = tmp_path / "project"
    preview = install(target, KIT.parent / "skills", "codex")
    assert preview["exit_code"] == 0 and preview["writes"]
    assert not target.exists()
    installed = install(target, KIT.parent / "skills", "codex", apply=True)
    assert installed["applied"] is True
    assert len(list((target / ".codex/agents").glob("*.toml"))) == 6
    assert not (target / "AGENTS.md").exists()
    assert install(target, KIT.parent / "skills", "codex")["writes"] == []
    custom = target / ".codex/agents/geoai-specialist.toml"
    custom.write_text("user-owned", encoding="utf-8")
    result = install(target, KIT.parent / "skills", "codex", apply=True)
    assert result["exit_code"] == 1
    assert custom.read_text() == "user-owned"


def test_package_is_deterministic_and_excludes_evaluation_answers(tmp_path):
    first, second = tmp_path / "first.zip", tmp_path / "second.zip"
    manifest = build(first)
    build(second)
    assert file_hash(first) == file_hash(second)
    with ZipFile(first) as archive:
        names = archive.namelist()
        assert not any("/evals/" in n or "/tests/" in n or "/artifacts/" in n for n in names)
        assert "geoai-agent-kit/_vendor/tools/verify.py" in names
        archive.extractall(tmp_path / "extracted")
    extracted = tmp_path / "extracted/geoai-agent-kit"
    assert verify_inventory(extracted, manifest["files"], exact=True)["exit_code"] == 0
    (extracted / "roles.json").write_text("[]", encoding="utf-8")
    assert verify_inventory(extracted, manifest["files"])["exit_code"] == 1
    with pytest.raises(FileExistsError):
        build(first)


@pytest.mark.parametrize("name", ["../escape", "/absolute", "a/../../escape",
                                  "C:\\escape", "..\\escape", "file:stream"])
def test_untrusted_paths_cannot_escape(tmp_path, name):
    with pytest.raises(ValueError):
        contained(tmp_path, name)
