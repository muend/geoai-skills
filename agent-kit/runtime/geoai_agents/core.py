"""Shared file, identity and outcome primitives."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

KIT = Path(__file__).resolve().parents[2]
IGNORED = {"__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache"}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True,
                       allow_nan=False) + "\n").encode("utf-8")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_hash(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def contained(root: Path, relative: str) -> Path:
    """Reject traversal and symlinks, including links that point back inside root."""
    root = root.resolve()
    if not isinstance(relative, str) or ":" in relative or "\x00" in relative:
        raise ValueError("invalid portable relative path")
    rel = Path(relative.replace("\\", "/"))
    if rel.is_absolute() or not rel.parts or ".." in rel.parts:
        raise ValueError(f"unsafe relative path: {relative}")
    current = root
    for part in rel.parts:
        current = current / part
        if current.is_symlink() or current.is_junction():
            raise ValueError(f"symlink is not an evidence file: {relative}")
    if not current.resolve().is_relative_to(root):
        raise ValueError(f"path escapes root: {relative}")
    return current


def records(root: Path, paths: list[str]) -> list[dict[str, Any]]:
    result = []
    for name in sorted(paths):
        path = contained(root, name)
        result.append({"path": name, "size": path.stat().st_size, "sha256": file_hash(path)})
    return result


def inventory(root: Path) -> list[str]:
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*")
                  if p.is_file() and not (set(p.relative_to(root).parts) & IGNORED))


def outcome(check: str, state: str, reason: str, **details: Any) -> dict[str, Any]:
    if state not in {"pass", "fail", "abstain"}:
        raise ValueError("unknown outcome")
    return {"check": check, "outcome": state, "reason": reason, "detail": details}


def report(results: list[dict[str, Any]]) -> dict[str, Any]:
    code = 1 if any(r["outcome"] == "fail" for r in results) else (
        2 if not results or any(r["outcome"] == "abstain" for r in results) else 0)
    return {"schema_version": 1, "results": results, "exit_code": code}


def finite(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, float | int) or not math.isfinite(value):
        raise ValueError("expected a finite number")
    return float(value)


def write_new(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(data)
