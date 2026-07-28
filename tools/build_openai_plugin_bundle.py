"""Build a deterministic, skills-only OpenAI plugin archive."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT_FILES = (
    Path(".codex-plugin/plugin.json"),
    Path("assets/geoai-skills-logo.png"),
    Path("LICENSE"),
    Path("PRIVACY.md"),
    Path("SECURITY.md"),
    Path("TERMS.md"),
)
RUNTIME_DIRECTORIES = frozenset({"agents", "assets", "references", "scripts"})
ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


def load_manifest(root: Path) -> dict:
    manifest_path = root / ".codex-plugin" / "plugin.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("plugin manifest must contain a JSON object")
    return payload


def bundle_files(root: Path) -> tuple[Path, ...]:
    """Return the complete, ordered runtime file set relative to ``root``."""
    missing = [path.as_posix() for path in ROOT_FILES if not (root / path).is_file()]
    if missing:
        raise FileNotFoundError(f"required bundle files are missing: {', '.join(missing)}")

    skills_root = root / "skills"
    if not skills_root.is_dir():
        raise FileNotFoundError("skills directory is missing")

    files = set(ROOT_FILES)
    for skill_root in sorted(path for path in skills_root.iterdir() if path.is_dir()):
        skill_md = skill_root / "SKILL.md"
        if not skill_md.is_file():
            raise FileNotFoundError(f"{skill_root.name} is missing SKILL.md")
        files.add(skill_md.relative_to(root))

        for directory_name in RUNTIME_DIRECTORIES:
            directory = skill_root / directory_name
            if not directory.exists():
                continue
            if directory.is_symlink():
                raise ValueError(f"bundle input may not be a symlink: {directory}")
            for candidate in directory.rglob("*"):
                if candidate.is_symlink():
                    raise ValueError(f"bundle input may not be a symlink: {candidate}")
                if candidate.is_file() and "__pycache__" not in candidate.parts:
                    files.add(candidate.relative_to(root))

    return tuple(sorted(files, key=lambda path: path.as_posix()))


def default_output(root: Path) -> Path:
    manifest = load_manifest(root)
    version = manifest.get("version")
    if not isinstance(version, str) or not version:
        raise ValueError("plugin manifest version must be a non-empty string")
    return root / "dist" / f"geoai-skills-openai-{version}.zip"


def _zip_info(path: Path) -> ZipInfo:
    info = ZipInfo(path.as_posix(), date_time=ZIP_TIMESTAMP)
    info.compress_type = ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = (0o100644 & 0xFFFF) << 16
    return info


def build_bundle(root: Path, output: Path) -> tuple[Path, str]:
    """Write the deterministic archive and return its path and SHA-256."""
    root = root.resolve()
    output = output.resolve()
    selected_files = bundle_files(root)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(f"{output.suffix}.tmp")

    try:
        with ZipFile(temporary, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
            for relative_path in selected_files:
                archive.writestr(_zip_info(relative_path), (root / relative_path).read_bytes())
        temporary.replace(output)
    finally:
        if temporary.exists():
            temporary.unlink()

    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    return output, digest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the deterministic GeoAI Skills OpenAI plugin archive."
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Archive path; defaults to dist/geoai-skills-openai-<version>.zip",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = Path(__file__).resolve().parent.parent
    output, digest = build_bundle(root, args.output or default_output(root))
    print(f"bundle: {output}")
    print(f"sha256: {digest}")


if __name__ == "__main__":
    main()
