"""Deterministic adapters and packages, with preview-first project installation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from .core import KIT, contained, digest, inventory, json_bytes, read_json, records, write_new
from .integrity import base_manifest, source_manifest, tree_digest, verify_base, verify_package

RUNTIME_ROOTS = ("runtime", "schemas", "adapters", "examples")
RUNTIME_FILES = ("geoai_agents.py", "package.json", "base.lock.json", "source.lock.json",
                 "roles.json", "bindings.json", "controls.json", "COMMON.md", "README.md",
                 "START.md", "requirements.txt")


def adapters() -> dict[str, bytes]:
    common = (KIT / "COMMON.md").read_text(encoding="utf-8")
    roles = read_json(KIT / "roles.json")
    generated = {}
    for role in roles:
        name = "geoai-" + role["id"]
        prompt = common + "\n\n" + role["instructions"] + "\n"
        # JSON string escapes are a subset of TOML basic-string escapes.
        codex = "\n".join(f"{key} = {json.dumps(value, ensure_ascii=False)}" for key, value in {
            "name": name, "description": role["description"],
            "developer_instructions": prompt,
        }.items()) + "\n"
        claude = (f"---\nname: {name}\ndescription: "
                  + json.dumps(role["description"], ensure_ascii=False)
                  + "\nmodel: inherit\nmaxTurns: 12\n---\n\n" + prompt)
        generated[f"adapters/codex/{name}.toml"] = codex.encode("utf-8")
        generated[f"adapters/claude/{name}.md"] = claude.encode("utf-8")
    return generated


def render(*, check: bool = False) -> list[str]:
    changed = []
    for relative, data in adapters().items():
        path = contained(KIT, relative)
        if not path.exists() or path.read_bytes() != data:
            changed.append(relative)
            if not check:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
    return changed


def payload() -> dict[str, bytes]:
    """Runtime allowlist: fixtures, tests, evaluation answers and logs cannot leak."""
    if (KIT / "manifest.json").exists() and verify_package(KIT)["exit_code"]:
        raise ValueError("installed package changed; refusing to redistribute changed bytes")
    names = list(RUNTIME_FILES)
    for prefix in RUNTIME_ROOTS:
        names.extend(f"{prefix}/{name}" for name in inventory(KIT / prefix))
    files = {name: contained(KIT, name).read_bytes() for name in names}
    # Validate both canonical and vendored sources against the unchanged base lock.
    source = KIT / "_vendor" if (KIT / "_vendor").exists() else KIT.parent
    for relative, record in legacy_files().items():
        raw = contained(source, relative).read_bytes()
        if digest(raw) not in {record["sha256"], record["source_sha256"]}:
            raise ValueError(f"legacy verification source changed: {relative}")
        files[f"_vendor/{relative}"] = raw
    if source == KIT.parent:
        files["LICENSE"] = contained(source, "LICENSE").read_bytes()
    if (KIT / "LICENSE").exists():
        files["LICENSE"] = (KIT / "LICENSE").read_bytes()
    return files


def legacy_files() -> dict[str, dict[str, Any]]:
    source = {r["path"]: r["sha256"] for r in source_manifest()["files"]}
    return {r["path"]: {**r, "source_sha256": source[r["path"]]} for r in base_manifest()["files"]
            if r["path"] == "tools/verify.py" or
            r["path"].startswith("tools/verification/") and r["path"].endswith(".py")}


def legacy_root() -> Path:
    root = KIT / "_vendor" if (KIT / "_vendor").exists() else KIT.parent
    for name, record in legacy_files().items():
        if digest(contained(root, name).read_bytes()) not in {
                record["sha256"], record["source_sha256"]}:
            raise ValueError(f"legacy verification source changed: {name}")
    return root


def package_manifest(files: dict[str, bytes]) -> dict[str, Any]:
    config = read_json(KIT / "package.json")
    entries = [{"path": name, "size": len(raw), "sha256": digest(raw)}
               for name, raw in sorted(files.items())]
    evaluation = (tree_digest(records(KIT / "evals", inventory(KIT / "evals")))
                  if (KIT / "evals").exists() else
                  read_json(KIT / "manifest.json")["evaluation_suite_sha256"])
    return {"kind": "geoai-agent-package", "schema_version": 1,
            "version": config["version"], "base": base_manifest()["base"],
            "base_manifest_sha256": config["base_manifest_sha256"],
            "source_manifest_sha256": config["source_manifest_sha256"],
            "agent_runtime_sha256": tree_digest(entries), "files": entries,
            "evaluation_suite_sha256": evaluation,
            "control_tools": {r["path"]: r["sha256"] for r in entries
                              if r["path"] == "runtime/geoai_agents/checks.py"
                              or r["path"].startswith("_vendor/")},
            "dependencies_sha256": digest(files["requirements.txt"])}


def build(output: Path) -> dict[str, Any]:
    if not (KIT / "_vendor").exists() and verify_base(KIT.parent)["exit_code"]:
        raise ValueError("frozen repository changed; refusing a compatible release")
    if render(check=True):
        raise ValueError("generated adapters are stale; run render before packaging")
    files = payload()
    manifest = package_manifest(files)
    files["manifest.json"] = json_bytes(manifest)
    if output.exists():
        raise FileExistsError(f"refusing to replace an existing archive: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "x", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for name, raw in sorted(files.items()):
            entry = ZipInfo("geoai-agent-kit/" + name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.compress_type = ZIP_DEFLATED
            entry.create_system = 3
            entry.external_attr = 0o100644 << 16
            archive.writestr(entry, raw)
    return manifest


def install(target: Path, skills_root: Path, runtime: str, *, apply: bool = False
            ) -> dict[str, Any]:
    compatibility = verify_base(skills_root, skills_only=True)
    if compatibility["exit_code"]:
        return {"exit_code": 1, "compatibility": compatibility, "writes": []}
    files = payload()
    manifest = package_manifest(files)
    files["manifest.json"] = json_bytes(manifest)
    targets = {f".geoai-agent-kit/{name}": raw for name, raw in files.items()}
    for name, raw in adapters().items():
        if name.startswith(f"adapters/{runtime}/"):
            targets[f".{runtime}/agents/{Path(name).name}"] = raw
    targets[".geoai-agent-kit/installation.json"] = json_bytes({
        "schema_version": 1, "runtime": runtime, "skills_root": str(skills_root.resolve()),
        "agent_runtime_sha256": manifest["agent_runtime_sha256"],
        "base": manifest["base"],
    })
    writes, conflicts = [], []
    for name, raw in targets.items():
        path = contained(target, name)
        if path.exists():
            if not path.is_file() or path.read_bytes() != raw:
                conflicts.append(name)
        else:
            writes.append(name)
    if conflicts:
        return {"exit_code": 1, "conflicts": sorted(conflicts), "writes": [], "applied": False}
    if apply:
        for name in sorted(writes):
            write_new(contained(target, name), targets[name])
    return {"exit_code": 0, "writes": sorted(writes), "applied": apply,
            "instruction": "Read .geoai-agent-kit/START.md in a new session to opt in."}
