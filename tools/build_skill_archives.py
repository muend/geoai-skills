"""Build deterministic, individually installable GeoAI skill archives."""

from __future__ import annotations

import argparse
import hashlib
import json
import tomllib
from dataclasses import dataclass
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

RUNTIME_DIRECTORIES = frozenset({"agents", "assets", "references", "scripts"})
IGNORED_DIRECTORIES = frozenset({"__pycache__", "evals"})
ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


@dataclass(frozen=True)
class Archive:
    """A generated skill archive and its integrity digest."""

    path: Path
    sha256: str


def package_version(root: Path) -> str:
    """Return the shared package version, failing on manifest drift."""
    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    codex = json.loads(
        (root / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    claude = json.loads(
        (root / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    versions = {
        pyproject.get("project", {}).get("version"),
        codex.get("version"),
        claude.get("version"),
    }
    if None in versions or "" in versions or len(versions) != 1:
        raise ValueError("Python, OpenAI, and Claude package versions must match")
    version = versions.pop()
    if not isinstance(version, str):
        raise TypeError("package version must be a string")
    return version


def skill_roots(root: Path) -> tuple[Path, ...]:
    """Return every ordered skill directory after structural checks."""
    skills_root = root / "skills"
    if not skills_root.is_dir():
        raise FileNotFoundError("skills directory is missing")
    if skills_root.is_symlink():
        raise ValueError(f"archive input may not be a symlink: {skills_root}")

    roots = tuple(sorted(path for path in skills_root.iterdir() if path.is_dir()))
    if not roots:
        raise ValueError("no skill directories found")
    for skill_root in roots:
        if skill_root.is_symlink():
            raise ValueError(f"archive input may not be a symlink: {skill_root}")
        if not (skill_root / "SKILL.md").is_file():
            raise FileNotFoundError(f"{skill_root.name} is missing SKILL.md")
    return roots


def archive_inputs(root: Path, skill_root: Path) -> tuple[Path, ...]:
    """Return the ordered runtime inputs for one skill, relative to ``root``."""
    allowed_root_entries = RUNTIME_DIRECTORIES | IGNORED_DIRECTORIES | {"SKILL.md"}
    unexpected = sorted(
        entry.name for entry in skill_root.iterdir() if entry.name not in allowed_root_entries
    )
    if unexpected:
        names = ", ".join(unexpected)
        raise ValueError(f"{skill_root.name} has unclassified package inputs: {names}")

    files = {skill_root / "SKILL.md"}
    for directory_name in RUNTIME_DIRECTORIES:
        directory = skill_root / directory_name
        if not directory.exists():
            continue
        if directory.is_symlink():
            raise ValueError(f"archive input may not be a symlink: {directory}")
        if not directory.is_dir():
            raise ValueError(f"runtime package input must be a directory: {directory}")
        for candidate in directory.rglob("*"):
            if candidate.is_symlink():
                raise ValueError(f"archive input may not be a symlink: {candidate}")
            if candidate.is_file() and not any(
                part in IGNORED_DIRECTORIES for part in candidate.parts
            ):
                files.add(candidate)

    return tuple(
        sorted(
            (path.relative_to(root) for path in files),
            key=lambda path: path.as_posix(),
        )
    )


def _zip_info(path: Path) -> ZipInfo:
    info = ZipInfo(path.as_posix(), date_time=ZIP_TIMESTAMP)
    info.compress_type = ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = (0o100644 & 0xFFFF) << 16
    return info


def build_archive(root: Path, skill_root: Path, output: Path) -> Archive:
    """Build one deterministic archive and return its SHA-256 digest."""
    inputs = archive_inputs(root, skill_root)
    license_path = root / "LICENSE"
    if not license_path.is_file() or license_path.is_symlink():
        raise FileNotFoundError("a regular root LICENSE file is required")
    entries = [
        (relative_path.relative_to("skills"), root / relative_path)
        for relative_path in inputs
    ]
    entries.append((Path(skill_root.name) / "LICENSE", license_path))
    entries.sort(key=lambda entry: entry[0].as_posix())

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(f"{output.suffix}.tmp")

    try:
        with ZipFile(temporary, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
            for archive_path, source_path in entries:
                archive.writestr(
                    _zip_info(archive_path),
                    source_path.read_bytes(),
                )
        temporary.replace(output)
    finally:
        if temporary.exists():
            temporary.unlink()

    return Archive(
        path=output,
        sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
    )


def build_archives(root: Path, output_dir: Path) -> tuple[Archive, ...]:
    """Build every skill archive and the ordered ``SHA256SUMS`` file."""
    root = root.resolve()
    output_dir = output_dir.resolve()
    skills_root = (root / "skills").resolve()
    if output_dir == skills_root or output_dir.is_relative_to(skills_root):
        raise ValueError("output directory must be outside the skills source tree")

    version = package_version(root)
    artifacts = []
    for skill_root in skill_roots(root):
        filename = f"geoai-skills-{skill_root.name}-{version}.zip"
        artifacts.append(build_archive(root, skill_root, output_dir / filename))

    checksum_text = "".join(
        f"{artifact.sha256}  {artifact.path.name}\n" for artifact in artifacts
    )
    checksum_path = output_dir / "SHA256SUMS"
    temporary = checksum_path.with_suffix(".tmp")
    try:
        temporary.write_text(checksum_text, encoding="utf-8", newline="\n")
        temporary.replace(checksum_path)
    finally:
        if temporary.exists():
            temporary.unlink()

    return tuple(artifacts)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build deterministic, individually installable GeoAI skill ZIP files."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Output directory; defaults to dist/skills.",
    )
    parser.add_argument(
        "--expected-version",
        help="Fail unless the package manifests match this release version.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = Path(__file__).resolve().parent.parent
    version = package_version(root)
    if args.expected_version is not None and args.expected_version != version:
        raise ValueError(
            f"release version mismatch: expected {args.expected_version}, package is {version}"
        )

    output_dir = args.output_dir or root / "dist" / "skills"
    artifacts = build_archives(root, output_dir)
    print(f"archives: {len(artifacts)}")
    print(f"output: {output_dir.resolve()}")
    print(f"checksums: {(output_dir / 'SHA256SUMS').resolve()}")


if __name__ == "__main__":
    main()
